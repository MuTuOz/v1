"""Offline PCAP to candidate five-second features, with explicit unavailable slots.

Never captures/sends packets. Names/order match the frozen schema, but candidate
semantics are engineering definitions, not verified DataSense extraction parity.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'flower_subtype_app/seniorfl_subtype/schema.json').read_text())
FEATURES=SCHEMA['features']


def aggregate_packets(packets,monitor_ip,logs=(),window_seconds=5,origin=0.):
    from scapy.layers.inet import IP,TCP,UDP
    from scapy.layers.l2 import Ether
    groups=defaultdict(list)
    for packet in packets:
        if IP not in packet or monitor_ip not in [packet[IP].src,packet[IP].dst]:continue
        if Ether in packet and any(packet[Ether].fields.get(f) is None for f in ['src','dst']):
            raise ValueError('Explicit Ethernet source/destination MACs required; automatic neighbor resolution is forbidden')
        timestamp=float(packet.time)
        if not math.isfinite(timestamp):raise ValueError('Nonfinite timestamp')
        start=origin+math.floor((timestamp-origin)/window_seconds)*window_seconds
        groups[start].append(packet)
    loggroups=defaultdict(list)
    for event in logs:
        if event.get('monitor_id')!=monitor_ip:continue
        ts=float(event['timestamp']);start=origin+math.floor((ts-origin)/window_seconds)*window_seconds
        loggroups[start].append(event)
    rows=[]
    for start,ps in sorted(groups.items()):
        f={name:None for name in FEATURES}
        times=sorted(float(p.time) for p in ps)
        f['network_packets_all_count']=len(ps)
        f['network_packets_src_count']=sum(p[IP].src==monitor_ip for p in ps)
        f['network_packets_dst_count']=sum(p[IP].dst==monitor_ip for p in ps)
        f['network_interval-packets']=float(np.diff(times).mean()) if len(times)>1 else None
        for kind,getter in [('ips',lambda p:(p[IP].src,p[IP].dst)),
                            ('macs',lambda p:(p[Ether].src,p[Ether].dst) if Ether in p else (None,None)),
                            ('ports',lambda p:(int(p[TCP].sport),int(p[TCP].dport)) if TCP in p else ((int(p[UDP].sport),int(p[UDP].dport)) if UDP in p else (None,None)))]:
            pairs=[getter(p) for p in ps]
            for suffix,values in [('src',[a for a,b in pairs]),('dst',[b for a,b in pairs]),('all',[x for pair in pairs for x in pair])]:
                f[f'network_{kind}_{suffix}_count']=len({x for x in values if x is not None})
        protocols={int(p[IP].proto) for p in ps}
        f['network_protocols_all_count']=len(protocols)
        for direction in ['src','dst']:
            f[f'network_protocols_{direction}_count']=len({int(p[IP].proto) for p in ps if getattr(p[IP],direction)==monitor_ip})
        for flag,bit in [('fin',1),('syn',2),('rst',4),('psh',8),('ack',16),('urg',32)]:
            name=f'network_tcp-flags-{flag}_count'
            if name in f:f[name]=sum(TCP in p and bool(int(p[TCP].flags)&bit) for p in ps)
        measures={
          'packet-size':[len(bytes(p)) for p in ps],
          'ip-length':[int(p[IP].len) if p[IP].len is not None else len(bytes(p[IP])) for p in ps],
          'ttl':[int(p[IP].ttl) for p in ps],
          'tcp-flags':[int(p[TCP].flags) for p in ps if TCP in p],
          'ip-flags':[int(p[IP].flags) for p in ps],
          'window-size':[int(p[TCP].window) for p in ps if TCP in p],
          'payload-length':[len(bytes(p[TCP].payload if TCP in p else p[UDP].payload)) for p in ps if TCP in p or UDP in p],
        }
        for name,values in measures.items():
            if not values:continue
            for statistic,function in [('avg',np.mean),('max',np.max),('min',np.min),('std_deviation',np.std)]:
                key=f'network_{name}_{statistic}'
                if key in f:f[key]=float(function(values))
        events=loggroups.get(start)
        if events:
            f['log_messages_count']=len(events)
            lt=sorted(float(e['timestamp']) for e in events)
            f['log_interval-messages']=float(np.diff(lt).mean()) if len(lt)>1 else None
            if all('data_type' in e for e in events):f['log_data-types_count']=len({e['data_type'] for e in events})
        rows.append({'window_start_utc_seconds':start,'window_seconds':window_seconds,'monitor_id':monitor_ip,
                     'features':f,'available_features':[k for k,v in f.items() if v is not None],
                     'missing_features':[k for k,v in f.items() if v is None],
                     'dataset_parity_verified':False,'provenance':'offline PCAP candidate extraction'})
    return rows


def model_ready(row,features=FEATURES):
    missing=[f for f in features if row['features'].get(f) is None]
    if missing:raise ValueError('Model input refused: unsupported/missing features: '+','.join(missing))
    if not row.get('dataset_parity_verified',False):
        raise ValueError('Model input refused: dataset feature semantics not verified')
    return np.array([row['features'][f] for f in features],dtype=np.float32)


def feature_contract():
    counters=['packets','ips','macs','ports','protocols']
    definitions={
      'network_interval-packets':'Mean consecutive matching-IPv4-packet interarrival seconds within a half-open window; singleton unavailable.',
      'network_fragmentation-score':'UNAVAILABLE: original score formula not recovered.',
      'log_messages_count':'Count explicitly supplied monitor-matched log events in window; no log stream means unavailable, not zero.',
      'log_interval-messages':'Mean interarrival seconds of supplied log events; singleton unavailable.',
      'log_data-types_count':'Distinct explicit data_type values in supplied log events; undefined if fields absent.',
    }
    for kind in counters:
        for direction in ['all','src','dst']:
            name=f'network_{kind}_{direction}_count'
            if name in FEATURES:definitions[name]=f'Candidate count of {kind}; src/dst packet direction is relative to monitor IPv4 address for packet/protocol counts; address/port src/dst refers to packet header fields. Exact source semantics unverified.'
    for name in FEATURES:
        if name.startswith('network_tcp-flags-') and name.endswith('_count'):definitions[name]='Count matching packets whose named TCP flag bit is set; non-TCP contributes no flag count.'
        if any(name.startswith('network_'+q+'_') for q in ['packet-size','ip-length','ttl','tcp-flags','ip-flags','window-size','payload-length']):
            definitions[name]='Candidate arithmetic mean/min/max/population std (ddof=0) of wire frame bytes, IPv4 length bytes, TTL, integer flag bits, TCP window field, or transport-payload bytes as indicated; protocol-inapplicable observations excluded.'
    return [{'index':i,'name':f,'dtype':'nullable float64 before baseline float32 preprocessing',
             'definition':definitions.get(f,'UNAVAILABLE: exact source definition not recovered; no guessed value emitted.'),
             'implementation_status':'candidate' if f in definitions and 'UNAVAILABLE' not in definitions[f] else 'unavailable',
             'dataset_semantic_parity':'not verified','source':'PCAP+explicit local logs; original dataset README gives window resolution but not complete formulas'} for i,f in enumerate(FEATURES)]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pcap',type=Path);p.add_argument('--monitor-ip',required=True)
    p.add_argument('--logs',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    from scapy.utils import PcapReader
    events=json.loads(a.logs.read_text()) if a.logs else []
    with PcapReader(str(a.pcap)) as packets:rows=aggregate_packets(packets,a.monitor_ip,events)
    with a.output.open('x') as f:json.dump(rows,f,indent=2,allow_nan=False)
