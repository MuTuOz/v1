"""Read-only capstone dashboard; every number comes from saved artifacts."""
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR','/tmp/seniorproject-dashboard-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/pre_pi_research_v1'
st.set_page_config(page_title='IIoT · Hierarchical FL',page_icon='📊',layout='wide')
st.title('Hierarchical Evaluation of Cyber Events in IIoT')
st.caption('Özyeğin University · CS401 / CS402 · Saved-artifact research demonstration')
st.info('Research question: Does collaboration help a client recognize attacks absent from its own training data but present at other clients?')
LIMIT='Validation: 6,486 rows; 28/84 subtypes and 7/8 families. Web absent. Heuristic episode IDs; benign temporal holdout. Seed variability is not independent-session uncertainty.'


def csv(path,**kwargs):
    if not path.exists():st.info('Not yet available.');return None
    return pd.read_csv(path,**kwargs)


index=csv(OUT/'EXPERIMENT_INDEX.csv')
if index is None or not len(index):st.stop()
pages=['Overview','Data and clients','Model comparison','Confusion matrices','Formal HCM','Locally unseen attacks','Repeated seeds','Class imbalance','Non-IID and convergence','Limitations','Future physical testbed']
page=st.sidebar.selectbox('View',pages,key='page')
experiment=st.sidebar.selectbox('Experiment / model',index.experiment_id.tolist(),key='experiment')
record=index.loc[index.experiment_id==experiment].iloc[0];folder=ROOT/record.artifact_dir
client=st.sidebar.selectbox('Client-relative support',[1,2,3,4,5],key='client')
level=st.sidebar.selectbox('Label level',['detection','family','subtype'],key='level')
metric=json.loads((folder/'metrics.json').read_text());config=json.loads((folder/'config.json').read_text())
st.sidebar.caption(f"Seed {record.seed} · {record['mode']} · {record.partition} · {record.loss} · {int(record.features)} features")
st.caption(LIMIT)

if page=='Overview':
    cols=st.columns(4)
    for col,label,k in zip(cols,['Exact subtype accuracy','Observed subtype Macro F1','Attack detection recall','Formal HCM F1'],['exact_subtype_accuracy','subtype_macro_f1_observed','attack_detection_recall','hcm_f1']):
        col.metric(label,f'{metric[k]:.3f}')
    st.write('Local-only, real Flower simulation and centralized models share the frozen validation rows. Network64 and imbalance/partition ablations are explicitly separate configurations.')
    st.dataframe(index[['experiment_id','phase','mode','seed','partition','loss','features','exact_subtype_accuracy','hcm_f1']],width='stretch')
elif page=='Data and clients':
    d=csv(OUT/'audit/original_client_class_support.csv')
    if d is not None:
        counts=d.groupby(['client_id','family']).training_support.sum().unstack(fill_value=0)
        st.bar_chart(counts);st.dataframe(d[d.client_id==client],width='stretch')
    stats=csv(OUT/'audit/partition_statistics.csv')
    if stats is not None:st.dataframe(stats,width='stretch')
elif page=='Model comparison':
    modes=st.multiselect('Learning modes',sorted(index['mode'].unique()),default=sorted(index['mode'].unique()))
    d=index[index['mode'].isin(modes)]
    st.dataframe(d,width='stretch')
    st.bar_chart(d.set_index('experiment_id')[['attack_only_subtype_accuracy','family_accuracy','hcm_f1']])
    st.json(config)
elif page=='Confusion matrices':
    cm=csv(folder/f'{level}_confusion.csv',index_col=0)
    normalize=st.checkbox('Row normalize P(predicted | actual)',value=True)
    if cm is not None:
        st.caption(f'{level}: actual rows × predicted columns; sample total {int(cm.to_numpy().sum())}; no-support normalized rows are N/A.')
        displayed=cm.div(cm.sum(axis=1).replace(0,np.nan),axis=0) if normalize else cm
        st.dataframe(displayed,width='stretch')
        if level!='subtype':
            fig,ax=plt.subplots(figsize=(7,5));a=displayed.to_numpy(dtype=float);ax.imshow(np.ma.masked_invalid(a),cmap='Blues',aspect='auto')
            ax.set_xticks(range(len(cm)),cm.columns,rotation=40,ha='right');ax.set_yticks(range(len(cm)),cm.index)
            ax.set(xlabel='Predicted',ylabel='Actual');fig.tight_layout();st.pyplot(fig);plt.close(fig)
        st.dataframe(pd.read_csv(folder/f'{level}_report.csv',index_col=0),width='stretch')
elif page=='Formal HCM':
    c=metric['hcm_counts'];st.dataframe(pd.DataFrame([[c['tp'],c['fn']],[c['fp'],c['tn']]],index=['Actual positive','Actual negative'],columns=['Predicted positive','Predicted negative']))
    st.json(metric['hcm_metrics']);st.caption('Riehl reference-compatible sibling/immediate-child TN; root excluded; benign depth 1, attack leaf depth 3. HCM counts are node decisions, not the five sample categories or operational benign FPR.')
    st.bar_chart(pd.Series(metric['hierarchical_errors'],name='Sample count'))
elif page=='Locally unseen attacks':
    d=csv(OUT/'phase02/matched_locally_unseen.csv')
    subset=st.selectbox('Training-support subset',['A_unseen_subtype','B_unseen_family','C_unseen_subtype_known_family'])
    if d is not None:
        selected=d[(d.client_id==client)&(d.subset==subset)]
        st.dataframe(selected,width='stretch')
        if selected.samples.max()==0:st.info('Unsupported / empty subset. No zero-score claim.')
        else:st.bar_chart(selected.set_index('experiment_id')[['exact_subtype_accuracy','family_accuracy','attack_detection_recall','hcm_f1']])
    st.caption('A = all client-relative missing attack subtypes. B = entirely missing attack families. C = missing subtype in a locally known family. These are not globally unseen/open-set classes. Client masks overlap; do not sum them as independent rows.')
elif page=='Repeated seeds':
    st.write('Predefined seeds: 42, 52, 62. Standard deviation is across seeds (ddof=1), not a confidence interval across independent sessions.')
    d=csv(OUT/'phase03/repeated_seed_summary.csv',header=[0,1,2])
    if d is not None:st.dataframe(d,width='stretch')
elif page=='Class imbalance':
    selected=index[(index.phase==4)|((index.phase.isin([1,3]))&(index.seed==42)&~index.experiment_id.str.startswith('historical_'))]
    st.dataframe(selected,width='stretch');st.bar_chart(selected.set_index('experiment_id')[['subtype_macro_f1_observed','benign_false_positive_rate','hcm_f1']])
    st.caption('One fixed seed per imbalance ablation; global training-derived class counts only. Effective-number beta=0.999. No search or presumption of improvement.')
elif page=='Non-IID and convergence':
    d=csv(OUT/'audit/partition_statistics.csv')
    if d is not None:st.dataframe(d,width='stretch')
    h=csv(folder/'training_history.csv')
    if h is not None:
        loss='weighted_train_loss' if 'weighted_train_loss' in h else 'loss';step='round' if 'round' in h else 'epoch'
        st.line_chart(h.set_index(step)[[loss]]);st.dataframe(h,width='stretch')
    st.caption('Serialized ArrayRecord sizes are measured application payloads; they exclude transport, TLS, configuration and retransmission overhead. Local E=2 doubles exposure in the full-participation schedule.')
elif page=='Limitations':
    st.warning(LIMIT)
    st.write('Repeated evaluation of this fixed validation set creates exploratory selection bias. No protected test metrics are used, no best validation model is promoted to deployment, and no physical-session independence or complete 84-class coverage is claimed.')
    st.write('Model seed-42 threads and training RNG details are recorded. Client-relative zero-support subsets are unavailable, not successful. Live feature parity has not been demonstrated.')
elif page=='Future physical testbed':
    st.warning('Future physical deployment — no Raspberry Pi execution, attacks or network changes claimed.')
    p=ROOT/'docs/pi_deployment_readiness.md'
    if p.exists():st.markdown(p.read_text())
    else:st.info('Not yet available.')
    p=OUT/'phase09/feature_parity_report.json'
    if p.exists():st.json(json.loads(p.read_text()))
