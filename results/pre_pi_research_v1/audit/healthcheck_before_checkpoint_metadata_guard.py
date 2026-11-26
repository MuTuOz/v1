"""Local-only environment/schema/data/checkpoint checks; does not open sockets."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'app'))
from pifl.common import FEATURES,CLASSES,MLP,prepare,labels
from pifl.client_app import fingerprint
import pandas as pd
import torch

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--training-csv',type=Path);p.add_argument('--checkpoint',type=Path);a=p.parse_args()
    result={'platform':platform.platform(),'machine':platform.machine(),'python':sys.version,
            'flower':importlib.metadata.version('flwr'),'schema_sha256':fingerprint(),
            'raspberry_pi_execution_claimed':False,'network_actions':False}
    if a.training_csv:
        if any(w in a.training_csv.name.lower() for w in ['test','validation']):raise ValueError('Training file required')
        d=pd.read_csv(a.training_csv);x=prepare(d);y=labels(d)
        if not torch.isfinite(x).all():raise ValueError('Nonfinite model tensors')
        result.update({'training_samples':len(d),'training_class_counts':[int((y==i).sum()) for i in range(84)],
                       'file_sha256':hashlib.sha256(a.training_csv.read_bytes()).hexdigest()})
    if a.checkpoint:
        c=torch.load(a.checkpoint,map_location='cpu',weights_only=True)
        if c['features']!=FEATURES or c['classes']!=CLASSES:raise ValueError('Checkpoint schema mismatch')
        MLP().load_state_dict(c['state_dict']);result['checkpoint_load']='passed'
    print(json.dumps(result,indent=2))
