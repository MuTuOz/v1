"""Bounded pre-Pi experiment orchestration. Protected tests are never opened."""
import argparse
from collections import Counter
import datetime as dt
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/pre_pi_research_v1"
sys.path.insert(0, str(ROOT / "pre_pi_app"))

import numpy as np
import pandas as pd
import torch
from researchfl.common import CLASSES, FEATURES, FAMILY_OF, MLP, class_weights, dump, labels, prepare, save_checkpoint, sha, train_epochs, train_path
from researchfl.evaluation import evaluate_checkpoint, evaluate_predictions, unseen_analysis


def config(experiment_id, phase, mode, seed=42, partition="original", loss="unweighted", client_id=None, **overrides):
    c = {"experiment_id":experiment_id,"phase":phase,"mode":mode,"seed":seed,
         "partition":partition,"loss":loss,"client_id":client_id,"features":FEATURES,
         "batch_size":128,"learning_rate":.001,"epochs":15,"rounds":15,"local_epochs":1,
         "num_clients":5,"clients_per_round":5,"root":str(ROOT),
         "class_counts":json.loads((OUT/"audit/training_class_counts.json").read_text()),
         "optimizer":"Adam","optimizer_state":"persistent for centralized/local; reset per federated round",
         "checkpoint_policy":"final only; no validation selection", "train_threads":1}
    c.update(overrides)
    return c


def audit():
    if (OUT/"audit/data_audit.json").exists():raise FileExistsError("Audit already exists")
    t = pd.read_csv(ROOT/"data/validation_v1/train.csv")
    v = pd.read_csv(ROOT/"data/validation_v1/validation.csv")
    clients = [pd.read_csv(ROOT/f"data/validation_v1/client_{i}_train.csv") for i in range(1,6)]
    assert len(t)==22450 and len(v)==6486 and v.label4.nunique()==28
    keys = list(t.columns[:8]); joined=pd.concat(clients,ignore_index=True)
    a=t.sort_values(keys).reset_index(drop=True);b=joined.sort_values(keys).reset_index(drop=True)
    assert not t.duplicated(keys).any() and a[keys].equals(b[keys])
    torch.testing.assert_close(prepare(a),prepare(b),rtol=0,atol=0)
    assert [c for c in t if c.startswith(('network_','log_'))]==FEATURES
    assert t.groupby('label4').label2.nunique().max()==1
    assert t.drop_duplicates('label4').set_index('label4').label2.to_dict()==FAMILY_OF
    assert ['benign']+sorted(set(t.label4)-{'benign'})==CLASSES
    assert not(set(t.loc[t.label2!='benign','episode_id'])&set(v.loc[v.label2!='benign','episode_id']))
    counts=[int((t.label4==s).sum()) for s in CLASSES]
    dump(OUT/"audit/training_class_counts.json",counts)
    support=[]
    for i,d in enumerate(clients,1):
        for s in CLASSES:support.append({'client_id':i,'subtype':s,'family':FAMILY_OF[s],
                                         'training_support':int((d.label4==s).sum()),'validation_support':int((v.label4==s).sum())})
    pd.DataFrame(support).to_csv(OUT/"audit/original_client_class_support.csv",index=False)
    paths=[ROOT/"data/validation_v1"/n for n in ['train.csv','validation.csv']+[f'client_{i}_train.csv' for i in range(1,6)]]
    dump(OUT/"audit/data_audit.json",{'training_rows':22450,'validation_rows':6486,
          'client_sizes':[len(d) for d in clients],'validation_attack_rows':int((v.label2!='benign').sum()),
          'validation_benign_rows':int((v.label2=='benign').sum()),'observed_subtypes':28,'absent_subtypes':56,
          'class_schema_valid':True,'client_union_metadata_and_model_tensors_equal':True,
          'attack_candidate_episode_overlap':0,'protected_tests_accessed':False,
          'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in paths}})
    weight_rows=[]
    for method in ['unweighted','inverse_frequency','effective_number']:
        w=class_weights(counts,method)
        for i,s in enumerate(CLASSES):weight_rows.append({'method':method,'subtype':s,'train_count':counts[i],'weight':1. if w is None else float(w[i])})
    pd.DataFrame(weight_rows).to_csv(OUT/"audit/class_weights.csv",index=False)
    # Additional partitions only reallocate immutable training rows.
    allocations={};rng=np.random.default_rng(2026)
    balanced=[[] for _ in range(5)]
    for s in CLASSES:
        indices=rng.permutation(t.index[t.label4==s].to_numpy())
        offset=int(rng.integers(0,5))
        for k,j in enumerate(indices):balanced[(offset+k)%5].append(int(j))
    allocations['balanced']=balanced
    exclusive=[[] for _ in range(5)];sizes=np.zeros(5,dtype=int)
    benign=rng.permutation(t.index[t.label4=='benign'].to_numpy())
    for k,j in enumerate(benign):exclusive[k%5].append(int(j));sizes[k%5]+=1
    for s in sorted(CLASSES[1:],key=lambda s:(-counts[CLASSES.index(s)],s)):
        c=int(np.argmin(sizes));idx=t.index[t.label4==s].tolist();exclusive[c].extend(idx);sizes[c]+=len(idx)
    allocations['exclusive']=exclusive
    partition_stats=[]
    global_freq=np.array(counts)/sum(counts)
    def stats(name,ds):
        for i,d in enumerate(ds,1):
            q=np.array([(d.label4==s).sum() for s in CLASSES],float);q/=q.sum();mid=(q+global_freq)/2
            kl=lambda a,b:float(np.sum(a[a>0]*np.log2(a[a>0]/b[a>0])))
            partition_stats.append({'partition':name,'client_id':i,'samples':len(d),'subtype_support':d.label4.nunique(),
              'family_support':d.label2.nunique(),'subtype_entropy_bits':float(-np.sum(q[q>0]*np.log2(q[q>0]))),
              'js_divergence_bits':.5*(kl(q,mid)+kl(global_freq,mid))})
    stats('original',clients)
    for name,parts in allocations.items():
        folder=OUT/'audit/allocations'/name;folder.mkdir(parents=True)
        flat=[j for indices in parts for j in indices]
        assert sorted(flat)==list(range(22450)) and all(parts)
        records=[];ds=[]
        for i,indices in enumerate(parts,1):
            d=t.loc[indices].copy();d.to_csv(folder/f'client_{i}_train.csv',index=False);ds.append(d)
            records.extend({'global_train_row':j,'client_id':i} for j in indices)
        pd.DataFrame(records).to_csv(folder/'allocation_manifest.csv',index=False);stats(name,ds)
    pd.DataFrame(partition_stats).to_csv(OUT/'audit/partition_statistics.csv',index=False)
    plan={'seeds':[42,52,62], 'reference':{'epochs':15,'rounds':15,'local_epochs':1,'batch_size':128,'lr':.001},
          'imbalance_methods':['unweighted','inverse_frequency','effective_number'],
          'effective_number_beta':.999,'imbalance_seed':42,'weights_source':'global training counts only; class metadata shared, no raw samples shared',
          'phase05_variants':['balanced_full_e1','exclusive_full_e1','original_partial3_e1','original_full_e2'],
          'phase05_seed':42,'network_only':['centralized','flower_fedavg'],
          'selection':'fixed grid before new results; exploratory use of frozen validation; no winner selected for deployment',
          'raw_row_iid_allocations_note':'new allocations operate on training rows, not independent episodes; evaluate fixed validation only'}
    dump(OUT/'audit/BOUNDED_EXPERIMENT_PLAN.json',plan)
    print('AUDIT PASSED',flush=True)


def fit(c):
    dest=OUT/f"phase{int(c['phase']):02d}"/c['experiment_id'];dest.mkdir(exist_ok=False)
    dump(dest/'config.json',c)
    if c['mode']=='flower_fedavg':
        launch_flower(c,dest)
    else:
        torch.set_num_threads(c['train_threads']);torch.manual_seed(c['seed']);torch.use_deterministic_algorithms(True)
        model=MLP(len(c['features']))
        path=train_path(ROOT,c,c['client_id'] if c['mode']=='local_only' else None)
        df=pd.read_csv(path)
        weights=class_weights(c['class_counts'],c['loss'])
        started=time.perf_counter()
        history=train_epochs(model,df,c,c['seed'],c['epochs'],weights=weights)
        pd.DataFrame(history).to_csv(dest/'training_history.csv',index=False)
        save_checkpoint(dest/'model.pt',model,c,training_rows=len(df),training_sha256=sha(path),
                        optimizer_steps=sum(h['optimizer_steps'] for h in history),
                        training_wall_seconds=time.perf_counter()-started)
    evaluate_checkpoint(ROOT,dest/'model.pt',dest)
    unseen_analysis(ROOT,dest/'predictions.csv',c['partition'],dest,c['experiment_id'])
    dump(dest/'COMPLETE.json',{'status':'complete','checkpoint_sha256':sha(dest/'model.pt'),
         'prediction_sha256':sha(dest/'predictions.csv'),'completed_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
    print('COMPLETE',c['experiment_id'],json.loads((dest/'metrics.json').read_text())['exact_subtype_accuracy'],flush=True)
    return dest


def references():
    for name,cp in [('centralized',ROOT/'models/subtype_centralized_val_v1.pt'),('flower_fedavg',ROOT/'models/subtype_flower_val_v1.pt')]:
        dest=OUT/'phase01'/f'historical_{name}_s42';dest.mkdir(exist_ok=False)
        c=config(f'historical_{name}_s42',1,name)
        c['provenance']='frozen historical checkpoint; no retraining';dump(dest/'config.json',c)
        evaluate_checkpoint(ROOT,cp,dest);unseen_analysis(ROOT,dest/'predictions.csv','original',dest,c['experiment_id'])
        dump(dest/'COMPLETE.json',{'status':'complete','source_checkpoint':str(cp.relative_to(ROOT)),'checkpoint_sha256':sha(cp)})


def locals_phase():
    for i in range(1,6):fit(config(f'ref_local_c{i}_s42',1,'local_only',client_id=i))
    references();aggregate()


def launch_flower(c,dest):
    home=Path('/home/seniorfl/.flwr/pre_pi_research_v1');home.mkdir(exist_ok=True)
    text='[superlink]\ndefault="pre-pi"\n[superlink.pre-pi]\naddress="127.0.0.1:39102"\ninsecure=true\noptions.num-supernodes=5\noptions.backend.name="ray"\noptions.backend.client-resources.num-cpus=1\noptions.backend.client-resources.num-gpus=0.0\n'
    if not (home/'config.toml').exists():(home/'config.toml').write_text(text)
    elif (home/'config.toml').read_text()!=text:raise ValueError('Dedicated runtime configuration changed')
    env=os.environ.copy();env.update({'FLWR_HOME':str(home),'FLWR_TELEMETRY_ENABLED':'0',
        'PATH':str(Path(sys.executable).parent)+os.pathsep+env.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1'})
    binary=Path(sys.executable).parent
    server_cmd=[str(binary/'flower-superlink'),'--insecure','--simulation','--disable-runtime-dependency-installation','--host','127.0.0.1','--port','39102']
    import tomli_w
    override=dest/'run_config.toml'
    override.write_text(tomli_w.dumps({'project-root':str(ROOT),'experiment-config':str((dest/'config.json').relative_to(ROOT))}))
    cmd=[str(binary/'flwr'),'run',str(ROOT/'pre_pi_app'),'pre-pi','--run-config',str(override),'--stream']
    dump(dest/'launch.json',{'server_command':server_cmd,'command':cmd,'cwd':str(ROOT),'flower_home':str(home),'loopback_only':True})
    with (dest/'superlink.log').open('x') as sl:
        process=subprocess.Popen(server_cmd,cwd=ROOT,env=env,stdout=sl,stderr=subprocess.STDOUT)
        try:
            for _ in range(150):
                if process.poll() is not None:raise RuntimeError('SuperLink startup failed')
                try:
                    with socket.create_connection(('127.0.0.1',39102),timeout=.2):break
                except OSError:time.sleep(.2)
            else:raise RuntimeError('SuperLink readiness timeout')
            with (dest/'simulation.log').open('x') as log:
                run=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
            if run.returncode or not (dest/'model.pt').exists():raise RuntimeError(f"Flower failed: {dest/'simulation.log'}")
        finally:
            process.terminate();process.wait(timeout=30)


def study():
    for seed in [42,52,62]:
        if seed!=42:
            for i in range(1,6):fit(config(f'ref_local_c{i}_s{seed}',3,'local_only',seed=seed,client_id=i))
        fit(config(f'ref_centralized_s{seed}',3,'centralized',seed=seed))
        fit(config(f'ref_flower_s{seed}',3,'flower_fedavg',seed=seed))
        aggregate()
    for method in ['inverse_frequency','effective_number']:
        fit(config(f'{method}_centralized_s42',4,'centralized',loss=method))
        for i in range(1,6):fit(config(f'{method}_local_c{i}_s42',4,'local_only',loss=method,client_id=i))
        fit(config(f'{method}_flower_s42',4,'flower_fedavg',loss=method));aggregate()
    for part,n,epochs in [('balanced',5,1),('exclusive',5,1),('original',3,1),('original',5,2)]:
        fit(config(f'{part}_flower_p{n}_e{epochs}_s42',5,'flower_fedavg',partition=part,clients_per_round=n,local_epochs=epochs));aggregate()
    network=[f for f in FEATURES if f.startswith('network_')]
    for mode in ['centralized','flower_fedavg']:
        fit(config(f'network64_{mode}_s42',9,mode,features=network))
    aggregate()


def aggregate():
    records=[];unseen=[];classes=[]
    keys=['exact_subtype_accuracy','subtype_macro_f1_observed','attack_only_subtype_accuracy','family_accuracy',
          'family_macro_f1_observed','attack_detection_recall','benign_false_positive_rate','hcm_f1']
    for complete in sorted(OUT.glob('phase*/*/COMPLETE.json')):
        folder=complete.parent;c=json.loads((folder/'config.json').read_text());m=json.loads((folder/'metrics.json').read_text())
        records.append({k:c.get(k) for k in ['experiment_id','phase','mode','seed','partition','loss','client_id','clients_per_round','local_epochs']}|
                       {'features':len(c['features']),'artifact_dir':str(folder.relative_to(ROOT)),**{k:m[k] for k in keys}})
        d=pd.read_csv(folder/'locally_unseen.csv');d['model_client_id']=c['client_id'];d['mode']=c['mode'];d['seed']=c['seed'];d['loss']=c['loss'];d['partition']=c['partition'];d['phase']=c['phase'];unseen.append(d)
        report=pd.read_csv(folder/'subtype_report.csv',index_col=0).loc[CLASSES].copy();report['experiment_id']=c['experiment_id'];report['seed']=c['seed'];report['mode']=c['mode'];report['client_id']=c['client_id'];report['loss']=c['loss'];classes.append(report.reset_index(names='subtype'))
    frame=pd.DataFrame(records);frame.to_csv(OUT/'EXPERIMENT_INDEX.csv',index=False)
    if not len(frame):return
    pd.concat(unseen,ignore_index=True).to_csv(OUT/'phase02/all_locally_unseen.csv',index=False)
    pd.concat(classes,ignore_index=True).to_csv(OUT/'phase03/all_per_class_metrics.csv',index=False)
    # Only matched local client and global models belong in each per-client comparison.
    u=pd.concat(unseen,ignore_index=True)
    u=u[(u['mode']!='local_only')|(u.client_id==u.model_client_id)]
    u.to_csv(OUT/'phase02/matched_locally_unseen.csv',index=False)
    reference=frame[(frame.loss=='unweighted')&(frame.partition=='original')&(frame.features==71)&~frame.experiment_id.str.startswith(('historical_','diagnostic_'))&(frame.phase.isin([1,3]))]
    reference.groupby(['mode','client_id'],dropna=False)[keys].agg(['mean','std','count']).to_csv(OUT/'phase03/repeated_seed_summary.csv')
    matched=u[(u.loss=='unweighted')&(u.partition=='original')&~u.experiment_id.str.startswith(('historical_','diagnostic_'))&u.phase.isin([1,3])]
    matched.groupby(['mode','model_client_id','client_id','subset'],dropna=False)[keys].agg(['mean','std','count']).to_csv(OUT/'phase03/repeated_seed_unseen_summary.csv')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['audit','locals','study','aggregate'])
    args=p.parse_args();{'audit':audit,'locals':locals_phase,'study':study,'aggregate':aggregate}[args.stage]()
