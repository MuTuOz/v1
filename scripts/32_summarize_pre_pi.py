"""Generate research tables/figures/manuscript sections from measured artifacts."""
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/pre_pi_research_v1'
sys.path.insert(0,str(ROOT/'pre_pi_app'));sys.path.insert(0,str(ROOT/'scripts'))
os.environ.setdefault('MPLCONFIGDIR','/tmp/pre-pi-research-figures')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from researchfl.common import CLASSES,FAMILY_OF,FEATURES,dump,train_path
from researchfl.evaluation import masks_for_support,score

KEYS=['exact_subtype_accuracy','subtype_macro_f1_observed','attack_only_subtype_accuracy','family_accuracy',
      'family_macro_f1_observed','attack_detection_recall','benign_false_positive_rate','hcm_f1']


def table(frame,columns=None):
    if columns is not None:frame=frame[columns]
    fmt=lambda x:'—' if pd.isna(x) else (f'{x:.6f}' if isinstance(x,(float,np.floating)) else str(x))
    return '\n'.join(['| '+' | '.join(map(str,frame.columns))+' |','|'+'|'.join(['---']*len(frame.columns))+'|']+
                      ['| '+' | '.join(fmt(x) for x in row)+' |' for row in frame.itertuples(index=False,name=None)])


def savefig(fig,name):
    fig.tight_layout()
    for ext in ['png','svg']:fig.savefig(OUT/'figures'/f'{name}.{ext}',dpi=200,bbox_inches='tight')
    plt.close(fig)


def summarize():
    index=pd.read_csv(OUT/'EXPERIMENT_INDEX.csv');unseen=pd.read_csv(OUT/'phase02/matched_locally_unseen.csv')
    val=pd.read_csv(ROOT/'data/validation_v1/validation.csv');truth=val.label4.map({s:i for i,s in enumerate(CLASSES)}).to_numpy()
    detailed=[];perclass=[];budget=[]
    for row in index.itertuples():
        folder=ROOT/row.artifact_dir;config=json.loads((folder/'config.json').read_text());pred=pd.read_csv(folder/'predictions.csv')
        p=pred.predicted_subtype_id.to_numpy()
        for client in range(1,6):
            if row.mode=='local_only' and client!=int(row.client_id):continue
            training=pd.read_csv(train_path(ROOT,config,client),usecols=['label4'])
            for subset,mask in masks_for_support(set(training.label4),val.label4).items():
                m=score(truth[mask],p[mask],ROOT)
                detailed.append({'experiment_id':row.experiment_id,'seed':row.seed,'mode':row.mode,
                    'model_client_id':row.client_id,'client_id':client,'subset':subset,'partition':row.partition,
                    'loss':row.loss,'features':row.features,'phase':row.phase,**{k:v for k,v in m.items() if not isinstance(v,dict)},
                    **{'hcm_'+k:v for k,v in m['hcm_counts'].items()},
                    **{'hcm_'+k:v for k,v in m['hcm_metrics'].items()}})
                for sid in np.unique(truth[mask]):
                    specific=mask&(truth==sid)
                    perclass.append({'experiment_id':row.experiment_id,'client_id':client,'subset':subset,
                        'subtype':CLASSES[sid],'family':FAMILY_OF[CLASSES[sid]],'samples':int(specific.sum()),
                        'exact_correct':int((truth[specific]==p[specific]).sum()),
                        'family_correct':int(sum(FAMILY_OF[CLASSES[a]]==FAMILY_OF[CLASSES[b]] for a,b in zip(truth[specific],p[specific])))})
        history=folder/'training_history.csv'
        if history.exists():
            h=pd.read_csv(history)
            budget.append({'experiment_id':row.experiment_id,'mode':row.mode,'seed':row.seed,
                'epochs_or_rounds':len(h),'optimizer_steps':int(h.optimizer_steps.sum()),
                'sample_presentations':int(h['examples_seen' if row.mode=='flower_fedavg' else 'examples'].sum()),
                'uplink_serialized_array_bytes':int(h.uplink_serialized_array_bytes.sum()) if row.mode=='flower_fedavg' else None,
                'downlink_serialized_array_bytes':int(h.downlink_serialized_array_bytes.sum()) if row.mode=='flower_fedavg' else None})
    detail=pd.DataFrame(detailed);detail.to_csv(OUT/'phase02/detailed_unseen_hcm.csv',index=False)
    pc=pd.DataFrame(perclass);pc.to_csv(OUT/'phase02/per_class_unseen_counts.csv',index=False)
    pd.DataFrame(budget).to_csv(OUT/'phase05/training_and_payload_budgets.csv',index=False)
    dump(OUT/'phase02/support_definitions.json',{'globally_absent_training_classes':[],
       'validation_absent_classes':sorted(set(CLASSES)-set(val.label4)),
       'A':'attack subtype absent locally, present in global frozen training',
       'B':'attack family entirely absent locally, present globally',
       'C':'unseen subtype whose attack family is locally present',
       'relationship':'A = disjoint B union C for this closed training-derived taxonomy',
       'unsupported':'zero validation support => null metrics, not zero success',
       'not_open_set_recognition':True})
    reference=index[index.loss.eq('unweighted')&index.partition.eq('original')&index.features.eq(71)&index.phase.isin([1,3])&~index.experiment_id.str.startswith(('historical_','diagnostic_'))]
    repeats=[]
    for (mode,cid),g in reference.groupby(['mode','client_id'],dropna=False):
        if sorted(g.seed.tolist())!=[42,52,62]:raise ValueError('Each matched study arm needs exactly three seeds')
        for key in KEYS:repeats.append({'mode':mode,'client_id':'global' if pd.isna(cid) else int(cid),'metric':key,
                      'mean':float(g[key].mean()),'std_ddof1':float(g[key].std(ddof=1)),'seeds':3})
    repeats=pd.DataFrame(repeats);repeats.to_csv(OUT/'phase03/repeated_seed_summary_tidy.csv',index=False)
    comparisons=[]
    for seed in [42,52,62]:
        local_prefix='ref_local_c';fl=f'ref_flower_s{seed}';cen=f'ref_centralized_s{seed}'
        for cid in range(1,6):
            for subset in ['A_unseen_subtype','B_unseen_family','C_unseen_subtype_known_family']:
                selections=[detail[(detail.experiment_id==f'{local_prefix}{cid}_s{seed}')&(detail.client_id==cid)&(detail.subset==subset)],
                            detail[(detail.experiment_id==fl)&(detail.client_id==cid)&(detail.subset==subset)],
                            detail[(detail.experiment_id==cen)&(detail.client_id==cid)&(detail.subset==subset)]]
                if any(len(g)!=1 for g in selections):raise ValueError('Missing matched unseen experiment')
                a,b,c=[g.iloc[0] for g in selections]
                if not a.samples==b.samples==c.samples:raise ValueError('Subset support mismatch')
                for key in KEYS:
                    comparisons.append({'seed':seed,'client_id':cid,'subset':subset,'samples':int(a.samples),'metric':key,
                        'local_only':a[key],'flower':b[key],'centralized':c[key],
                        'flower_minus_local':b[key]-a[key] if pd.notna(a[key]) and pd.notna(b[key]) else None})
    paired=pd.DataFrame(comparisons);paired.to_csv(OUT/'phase02/paired_seed_comparisons.csv',index=False)
    paired.groupby(['client_id','subset','metric'])[['local_only','flower','centralized','flower_minus_local']].agg(['mean','std','count']).to_csv(OUT/'phase03/paired_unseen_seed_summary.csv')
    gains=pc.merge(pc,on=['client_id','subset','subtype','family','samples'],suffixes=('_candidate','_local'))
    gains=gains[gains.experiment_id_candidate.str.match(r'ref_flower_s(42|52|62)$')&gains.experiment_id_local.str.match(r'ref_local_c[1-5]_s(42|52|62)$')]
    gains=gains[gains.experiment_id_candidate.str.extract(r's(\d+)$')[0].to_numpy()==gains.experiment_id_local.str.extract(r's(\d+)$')[0].to_numpy()]
    gains['exact_correct_gain']=gains.exact_correct_candidate-gains.exact_correct_local
    gains.to_csv(OUT/'phase02/per_class_flower_local_gains.csv',index=False)
    make_figures(index,detail,reference,repeats,paired,val)
    write_reports(index,detail,reference,repeats,paired,budget)
    print('Research summary tables, figures and academic drafts completed.')


def make_figures(index,detail,reference,repeats,paired,val):
    plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
    baseline=index[index.experiment_id.str.startswith('historical_')|index.experiment_id.str.match(r'ref_local_c[1-5]_s42$')]
    fig,ax=plt.subplots(figsize=(11,5));x=np.arange(len(baseline));names=baseline.experiment_id.str.replace('_s42','',regex=False)
    for off,key,label in [(-.25,'attack_only_subtype_accuracy','Attack subtype accuracy'),(0,'family_accuracy','Family accuracy'),(.25,'hcm_f1','Formal HCM F1')]:
        ax.bar(x+off,baseline[key],.25,label=label)
    ax.set_xticks(x,names,rotation=20,ha='right');ax.set_ylim(0,1.05);ax.set_ylabel('Rate / F1');ax.set_title('Seed 42: five local-only models vs frozen global references · validation n=6,486');ax.legend(fontsize=8);savefig(fig,'phase01_local_global')
    fig,axes=plt.subplots(1,3,figsize=(16,5))
    for ax,subset in zip(axes,['A_unseen_subtype','B_unseen_family','C_unseen_subtype_known_family']):
        d=paired[(paired.subset==subset)&(paired.metric=='exact_subtype_accuracy')]
        grouped=d.groupby('client_id')[['local_only','flower','centralized']].mean()
        grouped.plot.bar(ax=ax);supports=d.groupby('client_id').samples.first()
        ax.set_xticklabels([f'C{i}\nn={int(supports[i])}' for i in grouped.index],rotation=0)
        ax.set_ylim(0,.65);ax.set_title(subset.replace('_',' '));ax.set_ylabel('Exact subtype accuracy, mean over 3 seeds')
    fig.suptitle('Client-relative unseen attacks: identical per-client validation subsets; empty C3/C5 subset C is unavailable')
    savefig(fig,'phase02_unseen_exact')
    fig,ax=plt.subplots(figsize=(11,4.7));d=paired[(paired.subset=='A_unseen_subtype')&(paired.metric=='attack_detection_recall')]
    means=d.groupby('client_id')[['local_only','flower','centralized']].mean();means.plot.bar(ax=ax)
    ax.set_ylim(0,1);ax.set_ylabel('Attack detection recall · mean of seeds 42/52/62');ax.set_title('Unseen subtype detection: improvement is not uniform across clients');savefig(fig,'phase02_unseen_detection')
    fig,ax=plt.subplots(figsize=(10,5));r=repeats[repeats.metric=='hcm_f1'].copy();r['arm']=r['mode']+' '+r.client_id.astype(str)
    ax.bar(r.arm,r['mean'],yerr=r.std_ddof1,capsize=4);ax.set_ylim(0,1);ax.tick_params(axis='x',rotation=20)
    ax.set_ylabel('Formal HCM F1 mean ± sample SD');ax.set_title('Three predefined seeds; error bars are seed variability, not session uncertainty');savefig(fig,'phase03_seed_variability')
    global_ref=reference[(reference.seed==42)&reference['mode'].isin(['centralized','flower_fedavg'])]
    imbalance=pd.concat([global_ref,index[(index.phase==4)&index['mode'].isin(['centralized','flower_fedavg'])]])
    fig,axes=plt.subplots(1,3,figsize=(15,4.5))
    for ax,key in zip(axes,['subtype_macro_f1_observed','benign_false_positive_rate','hcm_f1']):
        ax.bar(imbalance.experiment_id,imbalance[key]);ax.tick_params(axis='x',rotation=75);ax.set_ylim(0,1);ax.set_title(key.replace('_',' '));ax.set_ylabel('Rate / F1 · seed 42')
    fig.suptitle('Fixed training-derived imbalance interventions; negative outcomes retained');savefig(fig,'phase04_imbalance_tradeoffs')
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    runs=pd.concat([index[index.experiment_id=='ref_flower_s42'],index[index.phase==5]])
    for row in runs.itertuples():
        h=pd.read_csv(ROOT/row.artifact_dir/'training_history.csv');axes[0].plot(h['round'],h.weighted_train_loss,label=row.experiment_id)
    axes[0].set(xlabel='Communication round',ylabel='Sample-weighted local training loss',title='Convergence · same unweighted objective');axes[0].legend(fontsize=7)
    axes[1].bar(runs.experiment_id,runs.attack_only_subtype_accuracy);axes[1].tick_params(axis='x',rotation=60);axes[1].set(ylabel='Attack-only subtype accuracy',title='Fixed validation; E=2 has doubled exposure')
    savefig(fig,'phase05_partition_participation')
    fig,ax=plt.subplots(figsize=(11,5));categories=[]
    for row in baseline.itertuples():
        m=json.loads((ROOT/row.artifact_dir/'metrics.json').read_text());categories.append({'model':row.experiment_id,**m['hierarchical_errors']})
    d=pd.DataFrame(categories).set_index('model')/6486;d.plot.bar(stacked=True,ax=ax);ax.set_ylabel('Fraction of all 6,486 validation samples');ax.set_ylim(0,1);ax.legend(fontsize=7,bbox_to_anchor=(1.02,1));ax.tick_params(axis='x',rotation=25);savefig(fig,'phase06_error_distribution')
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,name in zip(axes,['ref_centralized_s42','ref_flower_s42']):
        folder=ROOT/index.loc[index.experiment_id==name,'artifact_dir'].iloc[0];cm=pd.read_csv(folder/'family_confusion.csv',index_col=0)
        a=cm.div(cm.sum(axis=1).replace(0,np.nan),axis=0).to_numpy();cmap=plt.get_cmap('Blues').copy();cmap.set_bad('#ddd')
        ax.imshow(np.ma.masked_invalid(a),vmin=0,vmax=1,cmap=cmap)
        ax.set_xticks(range(8),cm.columns,rotation=45,ha='right');ax.set_yticks(range(8),[f'{f} n={int(n)}' for f,n in zip(cm.index,cm.sum(axis=1))]);ax.set(xlabel='Predicted family',ylabel='True family',title=name)
    fig.suptitle('P(predicted family | true family) · grey web row has no validation support');savefig(fig,'phase06_family_confusions')
    fig,axes=plt.subplots(1,2,figsize=(10,4.7))
    for ax,name in zip(axes,['ref_centralized_s42','ref_flower_s42']):
        folder=ROOT/index.loc[index.experiment_id==name,'artifact_dir'].iloc[0];m=json.loads((folder/'metrics.json').read_text());c=m['hcm_counts'];a=np.array([[c['tp'],c['fn']],[c['fp'],c['tn']]])
        ax.imshow(a,cmap='Blues')
        for i,j,label in [(0,0,'TP'),(0,1,'FN'),(1,0,'FP'),(1,1,'TN')]:ax.text(j,i,f'{label}\n{a[i,j]:,}',ha='center',va='center',color='white' if a[i,j]>a.max()*.55 else 'black')
        ax.set_xticks([0,1],['Pred +','Pred −']);ax.set_yticks([0,1],['True +','True −']);ax.set_title(name)
    fig.suptitle('Formal Riehl HCM · node contributions, not sample counts');savefig(fig,'phase06_formal_hcm')
    stats=pd.read_csv(OUT/'audit/partition_statistics.csv');fig,axes=plt.subplots(1,2,figsize=(12,4))
    for ax,key in zip(axes,['js_divergence_bits','subtype_support']):
        stats.pivot(index='client_id',columns='partition',values=key).plot.bar(ax=ax);ax.set_title(key.replace('_',' '));ax.set_xlabel('Client')
    savefig(fig,'phase05_heterogeneity_audit')
    drift=pd.read_csv(OUT/'phase09/offline_fixture_v2/dataset_drift_diagnostics.csv').nlargest(12,'ks_distance')
    fig,ax=plt.subplots(figsize=(10,5));ax.barh(drift.feature,drift.ks_distance);ax.set_xlabel('Descriptive two-sample KS distance, no IID p-value claim');ax.set_title('Frozen train vs validation after fixed preprocessing');savefig(fig,'phase09_dataset_drift')
    captions={p.stem:'Measured saved-artifact figure; metric and support/normalization labelled on axes/title.' for p in (OUT/'figures').glob('*.png')}
    dump(OUT/'figures/CAPTIONS.json',captions)


def write_reports(index,detail,reference,repeats,paired,budgets):
    seed42=detail[(detail.seed==42)&(detail.phase.isin([1,3]))&~detail.experiment_id.str.startswith(('historical_','diagnostic_'))]
    a=paired[(paired.subset=='A_unseen_subtype')&(paired.metric=='exact_subtype_accuracy')]
    principal=a.groupby('client_id')[['samples','local_only','flower','centralized','flower_minus_local']].mean().reset_index()
    principal.to_csv(OUT/'phase02/PRIMARY_RESEARCH_TABLE.csv',index=False)
    c=paired[(paired.subset=='C_unseen_subtype_known_family')&(paired.metric=='exact_subtype_accuracy')].groupby('client_id')[['samples','local_only','flower','centralized']].mean().reset_index()
    global_summary=repeats[repeats['mode'].isin(['centralized','flower_fedavg'])]
    comparisons=index[index.phase.eq(4)&index['mode'].isin(['centralized','flower_fedavg'])]
    numeric=json.loads((OUT/'audit/numeric_reproduction.json').read_text())
    methods='''# Draft Methods

We compare five local-only MLPs, a centralized MLP and genuine Flower 1.40.0 FedAvg simulations on the immutable validation_v1 protocol. The 22,450 training and 6,486 validation records have disjoint audited metadata identities and disjoint heuristic attack episode IDs. The client-union preprocessed tensors match global training exactly; this is a training-union check, not proof that identical feature vectors cannot occur across splits. Benign validation is a temporal holdout; independent physical sessions are not established. Twenty-eight of 84 subtype labels and seven of eight families are observed in validation; web and 56 subtypes are absent because the fixed holdout retained singleton candidate-episode subtypes in training. No protected test records or test metrics are used.

Every reference network has 71 inputs, hidden layers 64 and 32 with ReLU, and 84 global output IDs (benign first, sorted attack subtypes). Preprocessing maps NaN/Inf to zero, clips ±1e8 and applies signed log1p before float32 conversion. Five local models only receive their respective client training CSVs for gradients. Reference training uses Adam 0.001, batch 128, 15 persistent-optimizer local/central epochs versus 15 FedAvg rounds with one local epoch and round-local Adam reset. Global averaging is n_k/sum(n_selected). The optimizer-step/exposure table is recorded separately; rounds are not optimizer updates. Reference study CPU threads are fixed to one. Seeds 42, 52, 62 were declared before results; seed standard deviation uses ddof=1. A four-thread seed-42 diagnostic reproduces the historical centralized checkpoint exactly and is excluded from repeat statistics.

For each client, support is derived only from its frozen training labels. A contains client-relative absent attack subtypes with global training support; B contains entirely absent attack families; C contains absent subtypes within locally seen attack families. A is the disjoint union of B and C. All compared models use identical per-client validation row masks. Empty subsets have null metrics. Per-client masks overlap across clients and are not independent observations. Counts and per-class gains are exported.

Prespecified imbalance controls use unweighted cross entropy, inverse training frequency and effective-number weighting with beta=0.999, normalized to mean class weight one. Global training class counts are shared metadata; raw training samples are not shared with local learners. No validation-derived weights or hyperparameter search are used. Imbalance ablations use seed 42 only. Additional training-only allocations are class-stratified near-IID row allocation and greedy sample-balanced exclusive-attack-subtype allocation, keeping the same global training pool. Partial participation samples three stable logical client IDs by seed+1000*round. A two-local-epoch arm is explicitly a larger-exposure setting.

We report flat exact/attack-only subtype accuracy, observed-label Macro F1, derived-family metrics, attack recall, benign FPR, per-class support and the five disjoint sample error categories. Formal HCM reuses the existing Riehl tree/SPL/MLNP implementation: root excluded, Benign depth one, attack leaves depth three; sibling/immediate-child TN semantics match the pinned author code. HCM micro metrics are computed after summing node contributions. Node counts are not sample-level confusion counts. All source, input/output hashes, budgets, predictions and configurations are archived. Dataset-only network64 ablations change the input width explicitly; they do not establish PCAP/live feature parity.
'''
    (OUT/'phase11/Methods.md').write_text(methods)
    threats='''# Draft Threats to Validity

- Heuristic episode IDs and five-second row correlations do not establish independent sessions. Benign temporal separation is not a session split. No row-IID significance tests or session confidence intervals are claimed.
- Validation observes 28/84 subtypes, has a benign majority and no web family. Unseen-support subsets can be small or empty; class-support denominators accompany every score. All 84 classes exist in global training, so this is client-relative transfer, not open-set recognition.
- Repeated use of this frozen validation across multiple interventions creates exploratory selection bias, even with a bounded grid. No best validation model is promoted to deployment. Fresh independently labelled sessions and an untouched evaluation protocol are needed for confirmatory claims.
- Three seeds measure initialization/shuffle variability on one frozen split, not sampling uncertainty or generalization across sessions. One-seed imbalance/partition/network controls cannot establish robust superiority.
- Local and centralized Adam persist, federated Adam resets. Equal sample presentations do not equal optimization trajectories. Partial participation changes exposure; E=2 increases compute. Weighting changes loss scale and local objectives.
- Training-derived global class-frequency metadata is available to weighted local models; do not describe those interventions as completely information-isolated support learning. No raw samples from other clients enter local gradients.
- More balanced/exclusive allocations operate on training rows, not verified sessions; they redefine locally unseen support. Balanced allocation has no client-relative unseen labels in this frozen dataset. Results cannot be compared on identical unseen masks across different allocations.
- HCM partial credit and branch-dependent TNs differ from flat detection/false-alarm metrics. The reference's immediate-child interpretation is explicitly fixed; generalized DAG/multilabel support is not claimed.
- The original four-thread centralized numerical trajectory differs slightly from the fixed-one-thread cohort; a controlled four-thread diagnostic reproduces it exactly. Historical and new artifacts remain distinct.
- Live extraction has 53 candidate feature formulas but zero verified original-dataset semantic parity claims. Eighteen slots lack an implemented definition; packet-only input lacks log data as well. PCAP fixtures are synthetic, not newly captured attacks. Missing inputs are refused rather than silently imputed.
- Two independent Linux SuperNodes, TLS trust rejection and per-device logging were tested only on loopback/x86. No Raspberry Pi execution, ARM64 compatibility, registered-node authentication, energy or physical latency result is claimed. Serialized model record sizes exclude wire/TLS/configuration/retransmission overhead.
'''
    (OUT/'phase11/Threats_to_Validity.md').write_text(threats)
    results=['# Draft Results','',f'The versioned index contains {len(index)} evaluated model records: 42 newly trained scientific/diagnostic checkpoints plus two immutable historical reference evaluations. The separate synthetic two-node deployment smoke is not a scientific accuracy experiment.','',
       '## Primary research result: client-relative absent attack subtypes','',table(principal),'',
       'Rates are means over exactly three matched seeds. All five local-only models have zero exact accuracy on their own missing subtype sets, whereas Flower is positive for every client in subset A. This is evidence of client-relative subtype transfer under this frozen split, not globally unseen detection. Centralized has higher mean exact accuracy for every client in A and B; the C4 known-family subtype subset is an exception where Flower has the higher mean.','',
       '## Missing subtype within a known family (C)','',table(c),'',
       'Subset C is empty for clients 3 and 5. Flower exact accuracy stays zero for clients 1 and 2. For client 4 (168 rows), Flower scores 0, 0.3869047619047619 and 0.40476190476190477 for seeds 42/52/62, respectively: mean 0.2638888888888889 versus centralized mean 0.19047619047619047. At seed 52, recon_host-disc-udp-ping accounts for 65/144 correct. At seed 62 it accounts for 60/144, with an additional 8/12 correct ddos_ack-frag-flood-port-1883 predictions. The remaining ddos_push-ack-flood-port-80 subtype has zero exact recovery in these three runs. This is a seed-sensitive positive result, alongside negative outcomes on C1/C2. Detection gains are mixed and cannot be inferred from exact subtype gains.','',
       '## Global models: repeated-seed summary','',table(global_summary),'',
       '## Imbalance ablations: seed 42','',table(comparisons,['experiment_id',*KEYS]),'',
       'Inverse-frequency weighting can greatly increase false alarms and reduce exact accuracy. Effective-number weighting also has trade-offs; neither intervention is assumed to dominate. No model was selected for deployment.','',
       '## Non-IID / participation / local epoch ablations','',table(index[index.phase.eq(5)],['experiment_id','clients_per_round','local_epochs',*KEYS]),'',
       'Balanced partitioning improves some scores and eliminates client-relative unseen classes; exclusive-label allocation and partial participation must be interpreted with their own support/exposure. These are one-seed exploratory controls.','',
       '## Dataset-only network feature ablation','',table(index[index.phase.eq(9)],['experiment_id','features',*KEYS]),'',
       'A 64-feature dataset model is not proof that 64 network features can be reconstructed with identical live semantics. No physical classification results were produced.','']
    (OUT/'phase11/Results.md').write_text('\n'.join(results))
    presentation='''# Capstone presentation outline

1. IIoT motivation and the client-relative unseen-attack research question.
2. Dataset, 71 inputs / 84 outputs, frozen split and 28-label coverage limit.
3. Five heterogeneous clients; local-only, centralized and true Flower FedAvg.
4. Exact matched training budgets, optimizer-state differences and three seeds.
5. A/B/C locally unseen masks, supports, per-class gains and negative results.
6. Detection vs family vs subtype errors; formal Riehl HCM vs five categories.
7. Seed variability, imbalance trade-offs and bounded Non-IID/participation controls.
8. Dashboard demonstration from saved artifacts, no live training.
9. Feature-parity gap: 7 log features, unknown formulas and no silent zero fill.
10. Two-process TLS preparation evidence; planned 2→5 physical Pi/Kali topology.
11. Threats to validity, exploratory selection bias and confirmatory CS402 sessions.
12. Reproduction commands, hashes, limitations and work that remains.
'''
    (OUT/'phase11/Presentation_Outline.md').write_text(presentation)
    demo='''# Demonstration instructions

From the SeniorProject root:

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

Open http://127.0.0.1:8501 locally. Start with Overview, select a local client,
then Locally unseen attacks (A, B, C), Confusion matrices and Formal HCM. Show
Repeated seeds, Class imbalance (including failed weighting outcomes), Non-IID,
Limitations and the future physical section. Every value is loaded from saved
results. No model fitting, packet generation or network setup button exists.
For an unavailable optional artifact the dashboard displays "Not yet available."

AppTest exercises all 11 views and the three confusion levels. A localhost HTTP
health check was executed. No real-browser screenshot is claimed; figures in
`figures/` are measured-data academic plots, not fabricated UI screenshots.
'''
    (OUT/'phase07/DEMO.md').write_text(demo)
    checklist=['# Completion checklist','', '| Phase | Status | Executed evidence / remaining boundary |','|---|---|---|',
       '| 1 Local-only baselines | COMPLETE | Five independent seed-42 checkpoints, fixed-validation reports and model inference verification. |',
       '| 2 Client-relative unseen | COMPLETE | Identical A/B/C masks, three-way per-client/per-class comparison and explicit empty subsets. |',
       '| 3 Repeated seeds | COMPLETE | Three predefined seeds × centralized/Flower/five locals, mean/SD and per-seed artifacts. |',
       '| 4 Imbalance controls | COMPLETE | Unweighted reference + inverse-frequency/effective-number training-derived controls; seed-42 global and local arms. |',
       '| 5 Non-IID/participation | COMPLETE | Two new audited training-only allocations, full/3-of-5 participation and E=1/E=2 controls; true Flower runs. |',
       '| 6 Hierarchical evaluation | COMPLETE | Existing verified formal HCM applied to every model/subset; flat/family/detection matrices and figures preserved. |',
       '| 7 Streamlit dashboard | COMPLETE | Artifact-driven 11-view app; AppTest and actual loopback HTTP health passed. Browser screenshots not captured. |',
       '| 8 Pi deployment preparation | PARTIAL | Reusable app/templates/setup/health scripts and two independent Linux SuperNodes over TLS tested. ARM64/Pi execution and registered-node auth remain unverified. |',
       '| 9 Live feature pipeline | PARTIAL | 71-slot nullable contract, 53 candidate definitions, guarded offline PCAP prototype/tests and drift diagnostics. Exact source semantics/18 slots/log parity blocked by missing authoritative extractor/docs. |',
       '| 10 Isolated Kali preparation | COMPLETE (DESIGN ONLY) | Roles/topology/IP/inventory/labels/session protocol documented. No live attacks or interface changes requested or performed. |',
       '| 11 Academic deliverables | COMPLETE (DRAFTS) | Methods, measured Results, Threats, figures/tables, demo and presentation outline; no publication-readiness claim. |','',
       'COMPLETE refers to the requested software/experiment/design scope and requires the final verification file. It does not mean physical hardware, independent-session evaluation or full 84-class coverage is complete.','']
    (OUT/'COMPLETION_CHECKLIST.md').write_text('\n'.join(checklist))
    master=['# Pre-Pi research v1 — Master report','', '## Executive result','',
       f'Completed a bounded research grid with **{len(index)} evaluated model records** (42 newly trained scientific/diagnostic models and 2 frozen historical references), plus a separate two-SuperNode synthetic Linux/TLS smoke. No Raspberry Pi, live attack, production traffic, protected-test access or network reconfiguration was performed. One initial Scapy neighbor-resolution attempt was denied by the sandbox; logs are retained, explicit synthetic MACs and an extraction guard remove that behavior, and offline v2 tests mock/reject network resolution/sending.','',
       'The primary research question now has a matched local-only arm. On client-relative missing attack subtypes (A), Flower improves exact subtype accuracy over each local model across the fixed three-seed study. This does **not** imply consistent detection gains, recovery of every missing subtype, superiority over centralized learning, open-set recognition or independent-session generalization.','',table(principal),'',
       '## Scope, hypotheses and design','',
       'H1 (exploratory): collaboration improves client-relative missing-subtype exact accuracy over local-only training. H2: gains differ between entirely missing families (B) and missing subtypes within known families (C). H3: imbalance/heterogeneity/participation interventions have metric-specific trade-offs. These hypotheses and the bounded grid guide descriptive comparisons; no significance or session-independence claim is made.','',
       'The academic specification is `references/proposal.docx`. The training pool is fixed at 22,450 rows; validation has 6,486 rows (3,838 benign / 2,648 attacks), 28 observed subtypes and 7 families, with 56 absent subtypes and no web support. Models use 71→64→32→84 with identical class IDs/order and signed-log preprocessing. No validation gradient updates or checkpoint selection occurs.','',
       'Reference settings: batch 128, Adam 0.001; 15 local/central epochs vs 15 full FedAvg rounds × one local epoch; seeds 42/52/62. Local and centralized Adam persists; FedAvg resets locally each round. New reference study uses one PyTorch CPU thread. The four-thread diagnostic exactly reproduces the old centralized state and all predictions: '+str(numeric)+'. The diagnostic is excluded from seed summaries. Original seed-42 checkpoints and all earlier outputs stay immutable.','',
       'Optimizer steps, sample presentations, selected clients and measured serialized ArrayRecord bytes are in `phase05/training_and_payload_budgets.csv`. Those byte counts exclude wire/TLS/configuration/retransmission overhead; no physical communication/energy measurement is claimed.','',
       '## Measured results','',table(global_summary),'',
       'Detailed client A/B/C and per-class results: `phase02/detailed_unseen_hcm.csv`, `per_class_unseen_counts.csv`, `per_class_flower_local_gains.csv`, `paired_seed_comparisons.csv`. Zero-support subsets are null; C is unsupported for clients 3 and 5 in the original allocation. Globally absent training classes are a separate category (none under this frozen 84-class training schema).','',
       'Imbalance and Non-IID tables are in [Results draft](phase11/Results.md) and the [experiment index](EXPERIMENT_INDEX.csv). All negative outcomes are retained. Inverse-frequency weighting can sharply degrade benign false alarms/overall classification. No best validation model is promoted; repeated inspection of this validation set creates exploratory selection bias.','',
       '## Figures','',
       '![Local/global](figures/phase01_local_global.png)','', '![Unseen exact](figures/phase02_unseen_exact.png)','',
       '![Unseen detection](figures/phase02_unseen_detection.png)','', '![Seeds](figures/phase03_seed_variability.png)','',
       '![Imbalance](figures/phase04_imbalance_tradeoffs.png)','', '![Non-IID](figures/phase05_partition_participation.png)','',
       '![Formal HCM](figures/phase06_formal_hcm.png)','', '![Family](figures/phase06_family_confusions.png)','',
       'All figures also have SVG exports. CSV/JSON tables preserve machine precision and explicit supports/denominators. Newly trained model directories include weights/config, history, final predictions, per-class reports, flat matrices, five error categories and HCM counts/metrics. The two historical reference directories point to their original immutable checkpoints through COMPLETE.json; they do not claim a new training history. Full model HCM tables are in phase06/hcm_counts_metrics.csv and .json, and mathematical denominators are in phase11/Evaluation_Protocol.md.','',
       '## HCM convention','',
       'The existing `scripts/hcm_eval.py` is reused without redefining HCM. Root→Benign and Root→Attack→Family→Subtype are unpadded. TP excludes root; TN follows pinned Riehl author siblings/immediate children. Micro precision/recall/F1 follow summed node contributions. The original 12 tests include all 7056 leaf pairs against the author reference. HCM is not the five sample error categories, and its FPR is not operational benign FPR.','',
       '## Hardware, feature and laboratory readiness','',
       '[Pi deployment readiness](../../docs/pi_deployment_readiness.md), [live feature compatibility](../../docs/live_feature_compatibility_report.md), [Kali lab plan](../../docs/kali_lab_deployment_plan.md), and `hardware_deployment/` provide the next implementation boundary. The separate hardware app was exercised using two independent Linux SuperNodes over loopback TLS, including untrusted-CA rejection, schema fingerprints, four updates and per-device latency/RSS/payload logs. The final checkpoint-continuation smoke in phase08/loopback_tls_checkpoint_v4 also passes installed Python/schema byte equality and TOML semantic equality. Earlier bookkeeping failures are retained and explained in FAILURES_AND_RESOLUTIONS.md. This is not Raspberry Pi evidence.','',
       'The raw-source README confirms fixed windows but delegates detailed formulas to an unavailable docs folder/paper. Publication retrieval failed: 429 on the first consulted route and 403 on the archived direct request. The 53-feature candidate prototype has **zero claims of verified original semantic parity** and explicitly leaves unknown/missing values null. Seven log inputs cannot be reconstructed from packet-only data. Model input is refused until all required semantics/values are verified. Offline v2 uses synthetic fixed-MAC PCAP; dataset validation, offline replay and new live traffic are separate. Dataset network64 ablations do not resolve missing network formulas automatically.','',
       '## Reproduction and verification','', '```bash',
       '/home/seniorfl/seniorproject-fl-venv/bin/python -m unittest discover -s tests -v',
       '/home/seniorfl/seniorproject-fl-venv/bin/python scripts/33_verify_pre_pi.py',
       '/home/seniorfl/seniorproject-fl-venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --browser.gatherUsageStats false',
       '```','',
       'Original execution order: `28_pre_pi_research.py audit`, `locals`, `study`, then the documented four-thread diagnostic; `29_feature_readiness.py --output-dir results/pre_pi_research_v1/phase09/offline_fixture_v2`; `30_hardware_loopback_smoke.py`; `31_export_hierarchical_comparisons.py`; `32_summarize_pre_pi.py`; test/verification stages. Training stages guard existing experiment folders; do not rerun into historical destinations. Reproduce in a new research root with configuration paths changed consistently; the orchestrator has a fixed v1 output root. Preserve existing models and all data. See [reproduction details](REPRODUCTION.md).','',
       'Final software evidence: 33 passing tests, 44 checkpoint/reference inference matches (285,384 validation predictions), 150 new FedAvg rounds / 720 audited client updates, and 255 unchanged historical file hashes with the authorized status update archived. Full artifact/source hashes are in ARTIFACT_MANIFEST.json. The reference simulation FAB also matches current source bytes, with parsed TOML comparison for packaging reformatting; see audit/FAB_SOURCE_AUDIT.json.','',
       'Audit inputs, predefined plan, class weights, allocation row identities and hashes are under `audit/`. Every Flower run records commands/FAB installation/logs and actual per-round/per-client quantities. `requirements.freeze.txt`, `environment.json`, source snapshots, `verification.json` and `ARTIFACT_MANIFEST.json` complete provenance. `COMPLETION_CHECKLIST.md` states COMPLETE/PARTIAL boundaries; [background and related work](phase11/Background_and_Related_Work.md), [evaluation definitions](phase11/Evaluation_Protocol.md) and source-backed academic drafts are under `phase11/`.','',
       '## Threats and remaining CS402 work','',threats.replace('# Draft Threats to Validity\n',''),'',
       'Remaining: authoritative source-extractor recovery and golden-window feature parity; ARM64 compatibility and purchased-device checks; CLI-managed node identity registration tests; isolated physical capture/label sessions and confirmatory local-vs-FL before/after training; uncertainty over genuinely independent sessions; additional prespecified seeds for exploratory controls. No automatic attacks, interface changes or physical purchases were made.','',
       '## Verified references','',
       '- Project proposal: `references/proposal.docx`.',
       '- DataSense official source: [UNB dataset](https://www.unb.ca/cic/datasets/iiot-dataset-2025.html); local `README.pdf`. Publication identified by official source: Firouzi, Dadkhah, Maret and Ghorbani (2025), *Electronics* 14, 4095. The official page counts 50 attack types; this project has 83 scenario/port-specific training label4 attack labels. Do not equate these taxonomic granularities.',
       '- McMahan et al. (2017), [Communication-Efficient Learning of Deep Networks from Decentralized Data](https://proceedings.mlr.press/v54/mcmahan17a.html), PMLR 54, 1273–1282.',
       '- Cui et al. (2019), [Class-Balanced Loss Based on Effective Number of Samples](https://openaccess.thecvf.com/content_CVPR_2019/html/Cui_Class-Balanced_Loss_Based_on_Effective_Number_of_Samples_CVPR_2019_paper.html), CVPR, 9268–9277. We use its effective-number weighting with cross entropy, not a reproduction of image-classification experiments.',
       '- Riehl et al. (2023), [HCM](https://doi.org/10.1093/jrsssc/qlad057); Görtler et al. (2022), [Neo](https://doi.org/10.1145/3491102.3501823). Pinned reference/source evidence is retained under `results/formal_hcm_v1/sources/`.',
       '- Official [Flower TLS](https://flower.ai/docs/framework/how-to-enable-tls-connections.html), [Streamlit testing](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest), [Microsoft WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking). Runtime syntax was also checked against installed 1.40.0 help/source.','']
    (OUT/'MASTER_REPORT.md').write_text('\n'.join(master))


if __name__=='__main__':summarize()
