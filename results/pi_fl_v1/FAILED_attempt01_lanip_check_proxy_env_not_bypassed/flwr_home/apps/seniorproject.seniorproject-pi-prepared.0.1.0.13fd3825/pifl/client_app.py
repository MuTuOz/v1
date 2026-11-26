"""Simulation clients and node-local physical-client preparation share handlers."""
import json
import hashlib
import platform
from pathlib import Path
import time

import pandas as pd
import psutil
import torch
from flwr.clientapp import ClientApp
from flwr.common import ArrayRecord, Context, Message, MetricRecord, RecordDict

from .common import MLP, SCHEMA, class_weights, dump, prepare, train_epochs, train_path

app=ClientApp()


def fingerprint():
    return hashlib.sha256(json.dumps({k:SCHEMA[k] for k in ['classes','features','family_of','preprocessing']},sort_keys=True).encode()).hexdigest()


def client_id(context):
    return int(context.node_config.get("client-id",int(context.node_config.get("partition-id",0))+1))


def data_path(context, config):
    if "data-path" in context.node_config:
        p=Path(str(context.node_config["data-path"])).resolve()
        if "test" in p.name.lower() or "validation" in p.name.lower():
            raise ValueError("Client gradient handler accepts training files only")
        return p
    return train_path(config['root'],config,client_id(context))


@app.query("identity")
def identity(msg:Message,context:Context):
    c=json.loads(msg.content['config']['experiment-json'])
    df=pd.read_csv(data_path(context,c),usecols=['label4'])
    from flwr.common import ConfigRecord
    return Message(RecordDict({'metrics':MetricRecord({'client-id':client_id(context),'num-examples':len(df)}),
                              'schema':ConfigRecord({'sha256':fingerprint()})}),reply_to=msg)


@app.train()
def train(msg:Message,context:Context):
    c=json.loads(msg.content['config']['experiment-json']);round_num=int(msg.content['config']['server-round'])
    if c['features']!=SCHEMA['features'] or c.get('schema_sha256')!=fingerprint():
        raise ValueError('Frozen 71-feature/class/preprocessing schema mismatch')
    cid=client_id(context);torch.set_num_threads(1)
    model=MLP(len(c['features']));model.load_state_dict(msg.content['arrays'].to_torch_state_dict())
    df=pd.read_csv(data_path(context,c));start=time.perf_counter()
    history=train_epochs(model,df,c,c['seed']+100*round_num+cid,c['local_epochs'],
                         weights=class_weights(c['class_counts'],c['loss']))
    arrays=ArrayRecord(model.state_dict())
    metrics={'client-id':cid,'num-examples':len(df),'train_loss':history[-1]['loss'],
             'optimizer_steps':sum(h['optimizer_steps'] for h in history),
             'examples_seen':sum(h['examples'] for h in history),'training_seconds':time.perf_counter()-start,
             'rss_bytes':psutil.Process().memory_info().rss,'serialized_array_bytes':arrays.count_bytes()}
    model.eval();batch=prepare(df.head(128));timings=[]
    with torch.inference_mode():
        model(batch)
        for _ in range(10):
            start=time.perf_counter();model(batch);timings.append((time.perf_counter()-start)*1000)
    if 'log-dir' in context.node_config:
        folder=Path(str(context.node_config['log-dir']));folder.mkdir(parents=True,exist_ok=True)
        dump(folder/f"{c['experiment_id']}_client{cid}_round{round_num}.json",{
            **metrics,'platform':platform.platform(),'physical_raspberry_pi_verified':False,
            'inference_batch_rows':len(batch),'inference_batch_ms':timings,
            'note':'Batch timing after warm-up; not per-record independent timing. Hardware identity must be verified externally.'})
    return Message(RecordDict({'arrays':arrays,'metrics':MetricRecord(metrics)}),reply_to=msg)
