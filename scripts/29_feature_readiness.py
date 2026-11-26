"""Offline fixture/schema/drift evidence; no live capture or network activity."""
import json
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'pre_pi_app'))
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from scapy.all import Ether,IP,TCP,UDP,Raw,wrpcap
from live_pipeline.extract import aggregate_packets,feature_contract,model_ready
from researchfl.common import FEATURES,dump,prepare,sha

OUT=ROOT/'results/pre_pi_research_v1/phase09'
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    OUT=parser.parse_args().output_dir.resolve();OUT.mkdir(parents=True,exist_ok=True)
    dump(OUT/'feature_schema.json',{'window_seconds':5,'window_boundary':'[origin+k*5, origin+(k+1)*5)',
          'origin_utc_seconds':0,'group':'IPv4 packets involving explicitly configured monitor address',
          'normalization':'frozen signed_log1p_clip_1e8 only after semantic and missing-feature acceptance',
          'features':feature_contract(),'live_parity_verified':False})
    pd.DataFrame(feature_contract()).to_csv(OUT/'feature_contract.csv',index=False)
    packets=[]
    for ts,src,dst,flag in [(0.,'192.0.2.1','192.0.2.2','S'),(4.99,'192.0.2.2','192.0.2.1','A')]:
        p=Ether(src='02:00:00:00:00:01',dst='02:00:00:00:00:02')/IP(src=src,dst=dst,ttl=64)/TCP(sport=1234,dport=80,flags=flag)/Raw(b'fixture');p.time=ts;packets.append(p)
    p=Ether(src='02:00:00:00:00:01',dst='02:00:00:00:00:02')/IP(src='192.0.2.1',dst='192.0.2.2')/UDP(sport=1000,dport=2000);p.time=5.;packets.append(p)
    wrpcap(str(OUT/'offline_synthetic_fixture.pcap'),packets)
    from scapy.utils import PcapReader
    with PcapReader(str(OUT/'offline_synthetic_fixture.pcap')) as reader:rows=aggregate_packets(reader,'192.0.2.1')
    dump(OUT/'offline_fixture_features.json',rows)
    try:model_ready(rows[0]);raise AssertionError('Missing feature guard failed')
    except ValueError as error:guard=str(error)
    train=pd.read_csv(ROOT/'data/validation_v1/train.csv');val=pd.read_csv(ROOT/'data/validation_v1/validation.csv')
    x=prepare(train).numpy();y=prepare(val).numpy();drift=[]
    for j,f in enumerate(FEATURES):
        a=x[:,j];b=y[:,j];edges=np.unique(np.quantile(a,np.linspace(0,1,11)))
        if len(edges)>1:
            edges[0]=-np.inf;edges[-1]=np.inf
            pa=np.histogram(a,edges)[0].astype(float);pb=np.histogram(b,edges)[0].astype(float)
            pa=(pa+1e-4)/(len(a)+1e-4*len(pa));pb=(pb+1e-4)/(len(b)+1e-4*len(pb));psi=float(np.sum((pb-pa)*np.log(pb/pa)))
        else:psi=None
        drift.append({'feature':f,'train_mean_signed_log':float(a.mean()),'validation_mean_signed_log':float(b.mean()),
                      'standardized_mean_difference':float((b.mean()-a.mean())/(a.std()+1e-8)),
                      'ks_distance':float(ks_2samp(a,b).statistic),'psi_train_quantile_bins':psi,
                      'train_raw_missing_fraction':float(train[f].isna().mean()),'validation_raw_missing_fraction':float(val[f].isna().mean())})
    pd.DataFrame(drift).to_csv(OUT/'dataset_drift_diagnostics.csv',index=False)
    raw=[]
    for kind in ['attack','benign']:
        path=ROOT/f'data/raw/all_attack_benign_samples/{kind}_data/{kind}_samples_5sec.csv'
        raw.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'columns':pd.read_csv(path,nrows=0).columns.tolist(),'read_scope':'header only'})
    dump(OUT/'feature_parity_report.json',{'status':'PARTIAL','network_features':64,'log_features':7,
         'candidate_implemented':sum(f['implementation_status']=='candidate' for f in feature_contract()),
         'original_dataset_semantics_verified_features':0,'source_README_sha256':sha(ROOT/'README.pdf'),
         'original_README_statement':'features are fixed 1..10 second windows; complete definitions refer to paper/docs folder',
         'local_source_docs_directory_found':False,'raw_capture_files_found_locally':False,
         'original_publication_fetch':'MDPI DOI landing page returned HTTP 429; no authoritative extractor source recovered',
         'raw_headers':raw,'fixture_scope':'3 locally constructed packets serialized to PCAP; 2 half-open windows; not live traffic',
         'packet_sending_or_capture_performed':False,'model_input_guard_result':guard,
         'missing_features_first_window':rows[0]['missing_features'],
         'drift_note':'descriptive distances on fixed train/validation; no IID p-value claims, no training selection or preprocessing change',
         'network64_ablation_note':'dataset-only 64-feature baseline; does not establish live parity for all network features'})
    print('Offline feature fixture, contract, guard and drift diagnostics completed.')
