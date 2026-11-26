"""Two independent Linux SuperNodes over TLS using synthetic CSVs, loopback only.

No interface/firewall changes, no capture and no external targets. This does not
claim Raspberry Pi or CLI-managed node-authentication execution.
"""
import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
import ssl

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/pre_pi_research_v1/phase08/loopback_tls_smoke'


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--flower-home',type=Path,default=Path('/home/seniorfl/.flwr/pre_pi_hardware_smoke_v1'))
    parser.add_argument('--initial-checkpoint',type=Path)
    args=parser.parse_args()
    OUT=args.output_dir.resolve()
    if not OUT.is_relative_to(ROOT/'results/pre_pi_research_v1/phase08'):raise ValueError('Use a new phase08 smoke destination')
    if not args.flower_home.resolve().is_relative_to(Path('/home/seniorfl/.flwr')):raise ValueError('Use the authorized Flower home')
    import numpy as np
    import pandas as pd
    import tomli_w
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
    OUT.mkdir(exist_ok=False)
    certdir=Path(tempfile.mkdtemp(prefix='seniorproject-loopback-tls-'))
    now=dt.datetime.now(dt.timezone.utc);key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SeniorProject ephemeral loopback CA')])
    ca=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(minutes=1)).not_valid_after(now+dt.timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),True).sign(key,hashes.SHA256())
    endpoint=ec.generate_private_key(ec.SECP256R1())
    cert=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])).issuer_name(name).public_key(endpoint.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(minutes=1)).not_valid_after(now+dt.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),False).sign(key,hashes.SHA256())
    ca_path=certdir/'ca.pem';cert_path=certdir/'server.pem';key_path=certdir/'server.key'
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM));cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(endpoint.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));key_path.chmod(0o600)
    home=args.flower_home.resolve();home.mkdir(exist_ok=True)
    config_text='[superlink]\ndefault="smoke"\n[superlink.smoke]\naddress="127.0.0.1:39112"\nroot-certificates='+json.dumps(str(ca_path))+'\n'
    with (home/'config.toml').open('x') as f:f.write(config_text)
    schema=json.loads((ROOT/'hardware_deployment/app/pifl/schema.json').read_text())
    c={'experiment_id':'two_linux_processes_tls_smoke','mode':'physical_preparation_smoke','root':str(ROOT),
       'num_clients':2,'clients_per_round':2,'rounds':2,'local_epochs':1,'seed':101,
       'batch_size':8,'learning_rate':.001,'features':schema['features'],'class_counts':[0]*84,
       'loss':'unweighted','partition':'node_local_synthetic','synthetic_smoke_only':True}
    if args.initial_checkpoint:
        checkpoint=args.initial_checkpoint.resolve()
        if not checkpoint.is_relative_to(ROOT):raise ValueError('Project checkpoint required')
        c['initial_checkpoint']=str(checkpoint)
    (OUT/'config.json').write_text(json.dumps(c,indent=2))
    run_config=OUT/'run_config.toml';run_config.write_text(tomli_w.dumps({'project-root':str(ROOT),'experiment-config':str((OUT/'config.json').relative_to(ROOT))}))
    for cid in [1,2]:
        rng=np.random.default_rng(100+cid);d=pd.DataFrame(rng.normal(size=(16,71)),columns=schema['features'])
        d['label4']=['benign','ddos_syn-flood-port-80']*8;d.to_csv(OUT/f'client_{cid}_train.csv',index=False)
    env=os.environ.copy();binary=Path(sys.executable).parent
    env.update({'FLWR_HOME':str(home),'FLWR_TELEMETRY_ENABLED':'0','PATH':str(binary)+os.pathsep+env.get('PATH','')})
    server=[str(binary/'flower-superlink'),'--host','127.0.0.1','--port','39112','--ssl-ca-certfile',str(ca_path),'--ssl-certfile',str(cert_path),'--ssl-keyfile',str(key_path),'--disable-runtime-dependency-installation']
    processes=[];handles=[]
    commands=[server]
    try:
        log=(OUT/'superlink.log').open('x');handles.append(log);processes.append(subprocess.Popen(server,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT))
        for _ in range(100):
            if processes[0].poll() is not None:raise RuntimeError('TLS SuperLink startup failed')
            try:
                with socket.create_connection(('127.0.0.1',39112),timeout=.2):break
            except OSError:time.sleep(.2)
        for cid in [1,2]:
            node_config=f'client-id={cid} data-path={json.dumps(str(OUT/f"client_{cid}_train.csv"))} log-dir={json.dumps(str(OUT/f"device_{cid}"))}'
            cmd=[str(binary/'flower-supernode'),'--superlink','127.0.0.1:39112','--root-certificates',str(ca_path),
                 '--host','127.0.0.1','--port',str(39112+cid),'--node-config',node_config,
                 '--ssl-ca-certfile',str(ca_path),'--ssl-certfile',str(cert_path),'--ssl-keyfile',str(key_path)]
            commands.append(cmd);log=(OUT/f'supernode_{cid}.log').open('x');handles.append(log)
            processes.append(subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT))
        time.sleep(3)
        launch=[str(binary/'flwr'),'run',str(ROOT/'hardware_deployment/app'),'smoke','--run-config',str(run_config),'--stream'];commands.append(launch)
        with (OUT/'run.log').open('x') as log:
            result=subprocess.run(launch,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        if result.returncode or not (OUT/'model.pt').exists():raise RuntimeError('Independent process smoke failed; inspect logs')
        histories=pd.read_csv(OUT/'training_history.csv');client_rounds=pd.read_csv(OUT/'client_rounds.csv')
        assert len(histories)==2 and len(client_rounds)==4
        assert len(list(OUT.glob('device_*/*.json')))==4
        wrong_ca_rejected=False
        try:
            with urllib.request.urlopen('https://127.0.0.1:39112/',context=ssl.create_default_context(),timeout=5):pass
        except urllib.error.URLError as error:wrong_ca_rejected=isinstance(error.reason,ssl.SSLCertVerificationError)
        assert wrong_ca_rejected
        installed=list((home/'apps').glob('seniorproject.seniorproject-pi-prepared.*'))
        assert len(installed)==1,'Use a dedicated new Flower home for each smoke'
        hashes={}
        for source in (ROOT/'hardware_deployment/app').rglob('*'):
            if source.is_file() and '__pycache__' not in source.parts:
                relative=source.relative_to(ROOT/'hardware_deployment/app')
                packaged=installed[0]/relative
                if str(relative)=='pyproject.toml':
                    assert tomllib.loads(packaged.read_text())==tomllib.loads(source.read_text()),'Packaged TOML semantics changed'
                else:
                    assert packaged.read_bytes()==source.read_bytes(),str(relative)
                hashes[str(relative)]=hashlib.sha256(source.read_bytes()).hexdigest()
        (OUT/'verification.json').write_text(json.dumps({'status':'passed','independent_linux_supernodes':2,'rounds':2,
            'successful_updates':4,'tls_enabled':True,'untrusted_ca_rejected':wrong_ca_rejected,
            'ca_sha256':ca.fingerprint(hashes.SHA256()).hex(),'private_keys_archived':False,
            'cli_managed_node_authentication_tested':False,'device_logs':4,'data':'synthetic 16-row training CSV per client',
            'raspberry_pi_execution':False,'network_scope':'loopback only','network_configuration_changed':False,
            'initial_checkpoint':c.get('initial_checkpoint'),
            'initial_checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest() if args.initial_checkpoint else None,
            'packaged_sources_equal_current_source':True,'packaged_source_sha256':hashes,
            'packaged_comparison':'Python/schema byte equality; pyproject.toml semantic equality (Flower reserializes formatting)',
            'commands':commands},indent=2))
        print('Two independent Linux SuperNodes, TLS, wrong-CA rejection and per-device measurements passed.')
    finally:
        for p in reversed(processes):
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for h in handles:h.close()


if __name__=='__main__':main()
