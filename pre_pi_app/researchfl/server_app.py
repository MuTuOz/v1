import json
from pathlib import Path
import random
import time

import numpy as np
import pandas as pd
import torch
from flwr.common import ArrayRecord, ConfigRecord, Context, Message, MessageType, RecordDict
from flwr.serverapp import Grid, ServerApp
from flwr.serverapp.strategy import FedAvg

from .common import MLP, dump, save_checkpoint

app=ServerApp()


class ResearchFedAvg(FedAvg):
    def __init__(self,c,out,identities):
        super().__init__(fraction_train=1.,fraction_evaluate=0.,min_train_nodes=c['clients_per_round'],
                         min_available_nodes=c['num_clients'],weighted_by_key='num-examples')
        self.c=c;self.out=out;self.identities=identities;self.clients=[];self.rounds=[];self.selected={}
    def configure_train(self,server_round,arrays,config,grid):
        chosen=sorted(random.Random(self.c['seed']+1000*server_round).sample(sorted(self.identities),self.c['clients_per_round']))
        self.selected[server_round]=chosen
        config['server-round']=server_round
        self.downlink_bytes=arrays.count_bytes()*len(chosen)
        records=RecordDict({'arrays':arrays,'config':config})
        return self._construct_messages(records,[self.identities[i]['node_id'] for i in chosen],MessageType.TRAIN)
    def aggregate_train(self,server_round,replies):
        replies=list(replies)
        if len(replies)!=self.c['clients_per_round'] or any(m.has_error() for m in replies):
            raise RuntimeError('Required client updates missing')
        replies.sort(key=lambda m:int(m.content['metrics']['client-id']))
        ids=[int(m.content['metrics']['client-id']) for m in replies]
        if ids!=self.selected[server_round]:raise RuntimeError('Unexpected client identity')
        n=[int(m.content['metrics']['num-examples']) for m in replies]
        for cid,size in zip(ids,n):
            if size!=self.identities[cid]['samples']:raise RuntimeError('Training size changed within run')
        states=[m.content['arrays'].to_torch_state_dict() for m in replies]
        arrays,aggregated=super().aggregate_train(server_round,replies)
        actual=arrays.to_torch_state_dict();weights=np.array(n,dtype=float)/sum(n);error=0.
        for key,tensor in actual.items():
            expected=sum(s[key].double()*float(w) for s,w in zip(states,weights))
            error=max(error,float((tensor.double()-expected).abs().max()))
            torch.testing.assert_close(tensor.double(),expected,rtol=1e-6,atol=1e-7)
        for m,cid,w in zip(replies,ids,weights):
            self.clients.append({'round':server_round,'client_id':cid,'aggregation_weight':float(w),**dict(m.content['metrics'])})
        row={'round':server_round,'clients':len(ids),'selected_clients':','.join(map(str,ids)),
             'selected_training_samples':sum(n),'weighted_train_loss':float(aggregated['train_loss']),
             'aggregation_max_abs_error':error,'downlink_serialized_array_bytes':self.downlink_bytes,
             'uplink_serialized_array_bytes':sum(int(m.content['metrics']['serialized_array_bytes']) for m in replies),
             'examples_seen':sum(int(m.content['metrics']['examples_seen']) for m in replies),
             'optimizer_steps':sum(int(m.content['metrics']['optimizer_steps']) for m in replies)}
        self.rounds.append(row)
        pd.DataFrame(self.rounds).to_csv(self.out/'training_history.csv',index=False)
        pd.DataFrame(self.clients).to_csv(self.out/'client_rounds.csv',index=False)
        return arrays,aggregated


@app.main()
def main(grid:Grid,context:Context):
    root=Path(str(context.run_config['project-root']));config_path=(root/str(context.run_config['experiment-config'])).resolve()
    if not config_path.is_relative_to(root/'results/pre_pi_research_v1'):raise ValueError('Unexpected experiment path')
    c=json.loads(config_path.read_text());out=config_path.parent
    if (out/'model.pt').exists() or (out/'training_history.csv').exists():raise FileExistsError('Preserve existing run')
    config=ConfigRecord({'experiment-json':json.dumps(c)})
    deadline=time.monotonic()+120
    while len(list(grid.get_node_ids()))<c['num_clients']:
        if time.monotonic()>deadline:raise TimeoutError('Clients unavailable')
        time.sleep(.2)
    requests=[Message(content=RecordDict({'config':config}),dst_node_id=n,message_type='query.identity') for n in grid.get_node_ids()]
    identities={}
    for reply in grid.send_and_receive(requests,timeout=120):
        if reply.has_error():raise RuntimeError('Identity query failed')
        m=reply.content['metrics'];cid=int(m['client-id'])
        if cid in identities:raise RuntimeError('Duplicate client identity')
        identities[cid]={'node_id':int(reply.metadata.src_node_id),'samples':int(m['num-examples'])}
    if len(identities)!=c['num_clients']:raise RuntimeError('Wrong federation size')
    dump(out/'client_identity_audit.json',identities)
    torch.set_num_threads(1);torch.manual_seed(c['seed']);torch.use_deterministic_algorithms(True)
    model=MLP(len(c['features']))
    if c.get('initial_checkpoint'):
        checkpoint=torch.load(c['initial_checkpoint'],map_location='cpu',weights_only=True)
        if checkpoint['features']!=c['features']:raise ValueError('Initial checkpoint feature mismatch')
        model.load_state_dict(checkpoint['state_dict'])
    strategy=ResearchFedAvg(c,out,identities);start=time.perf_counter()
    result=strategy.start(grid=grid,initial_arrays=ArrayRecord(model.state_dict()),train_config=config,
                          num_rounds=c['rounds'],timeout=180)
    if len(strategy.rounds)!=c['rounds']:raise RuntimeError('Incomplete round schedule')
    model.load_state_dict(result.arrays.to_torch_state_dict())
    save_checkpoint(out/'model.pt',model,c,training_wall_seconds=time.perf_counter()-start,
                    optimizer_steps=sum(r['optimizer_steps'] for r in strategy.rounds),
                    examples_seen=sum(r['examples_seen'] for r in strategy.rounds),
                    payload_measurement='serialized ArrayRecord sizes; excludes transport/TLS/config overhead')
