#!/usr/bin/env python3
"""PC = Flower SuperLink (server), Raspberry Pi = Flower SuperNode (client).

Helper around the prepared deployment app in ``hardware_deployment/app`` (Flower
1.40.0). It never changes network/firewall settings and never uses sudo.

Sub-commands
------------
certs     create a throw-away lab CA + server certificate whose SAN contains the
          PC's LAN IP (keys are written OUTSIDE the repository, default ~/.seniorfl_pki)
prepare   create a NEW experiment directory results/pi_fl_v1/<experiment-id>/
          with config.json + run_config.toml for the server
commands  print the exact commands to run on the PC and on each Pi
loopback  run the whole federation on ONE machine (SuperLink + N SuperNodes on
          127.0.0.1) to verify the software path before touching the Pi
verify    check a finished experiment directory (rounds, updates, weights, device logs)

Typical lab session (see docs/pc_server_pi_client_quickstart_tr.md):
    python scripts/36_pc_pi_federation.py certs --server-ip 192.168.1.20
    python scripts/36_pc_pi_federation.py prepare --experiment-id pi_lan_2clients_s42 --num-clients 2 --rounds 5
    python scripts/36_pc_pi_federation.py commands --experiment-id pi_lan_2clients_s42 --server-ip 192.168.1.20
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "hardware_deployment/app"
OUT_ROOT = ROOT / "results/pi_fl_v1"
# Flower 1.40 serves the Fleet, Control and Runtime APIs over ONE HTTPS port
# (--host/--port; default 127.0.0.1:8000, which a Pi cannot reach). The
# deprecated --fleet-api-address/--control-api-address flags are ignored.
SERVER_PORT = 9092


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ----------------------------------------------------------------------------- certs
def cmd_certs(a) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    pki = Path(a.pki_dir).expanduser().resolve()
    if pki.is_relative_to(ROOT):
        raise SystemExit("Keep keys outside the repository")
    pki.mkdir(parents=True, exist_ok=False)
    os.chmod(pki, 0o700)
    now = dt.datetime.now(dt.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SeniorProject lab CA (pi_fl_v1)")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=a.days))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), True).sign(ca_key, hashes.SHA256()))
    srv_key = ec.generate_private_key(ec.SECP256R1())
    sans = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    for ip in a.server_ip:
        sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
    for name in a.server_dns:
        sans.append(x509.DNSName(name))
    srv = (x509.CertificateBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "seniorproject-superlink")]))
           .issuer_name(ca_name).public_key(srv_key.public_key()).serial_number(x509.random_serial_number())
           .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=a.days))
           .add_extension(x509.SubjectAlternativeName(sans), False)
           .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
           .sign(ca_key, hashes.SHA256()))
    pem = serialization.Encoding.PEM
    (pki / "ca.pem").write_bytes(ca.public_bytes(pem))
    (pki / "server.pem").write_bytes(srv.public_bytes(pem))
    for name, key in (("ca.key", ca_key), ("server.key", srv_key)):
        p = pki / name
        p.write_bytes(key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        p.chmod(0o600)
    print(json.dumps({"pki_dir": str(pki), "copy_to_each_pi": str(pki / "ca.pem"),
                      "ca_sha256_fingerprint": ca.fingerprint(hashes.SHA256()).hex(),
                      "server_sans": [str(s.value) for s in sans],
                      "note": "copy ONLY ca.pem to the Pi; never copy *.key"}, indent=2))


# ----------------------------------------------------------------------------- prepare
def cmd_prepare(a) -> Path:
    import tomli_w
    schema = json.loads((APP / "pifl/schema.json").read_text())
    out = (OUT_ROOT / a.experiment_id).resolve()
    out.mkdir(parents=True, exist_ok=False)
    c = {"experiment_id": a.experiment_id, "mode": "physical_pc_server_pi_client",
         "root": str(ROOT), "num_clients": a.num_clients, "clients_per_round": a.clients_per_round or a.num_clients,
         "rounds": a.rounds, "local_epochs": a.local_epochs, "seed": a.seed, "batch_size": a.batch_size,
         "learning_rate": a.learning_rate, "features": schema["features"], "class_counts": [0] * 84,
         "loss": "unweighted", "partition": a.partition_note,
         "optimizer_state_policy": "Adam re-created on every client every round (reset)",
         "aggregation": "sample-count weighted FedAvg over selected clients",
         "created_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    if a.initial_checkpoint:
        ck = (ROOT / a.initial_checkpoint).resolve()
        c["initial_checkpoint"] = str(ck)
        c["initial_checkpoint_sha256"] = sha256(ck)
    (out / "config.json").write_text(json.dumps(c, indent=2))
    (out / "run_config.toml").write_text(tomli_w.dumps(
        {"project-root": str(ROOT), "experiment-config": str((out / "config.json").relative_to(ROOT))}))
    print(f"prepared {out.relative_to(ROOT)}")
    return out


# ----------------------------------------------------------------------------- commands
def server_cmds(a, exp: Path, pki: Path, bin_dir: str = "", bind_host: str = "0.0.0.0") -> dict:
    b = (lambda x: str(Path(bin_dir) / x)) if bin_dir else (lambda x: x)
    superlink = [b("flower-superlink"), "--host", bind_host, "--port", str(SERVER_PORT),
                 "--ssl-ca-certfile", str(pki / "ca.pem"), "--ssl-certfile", str(pki / "server.pem"),
                 "--ssl-keyfile", str(pki / "server.key"), "--disable-runtime-dependency-installation",
                 "--database", str(exp / "superlink_state.db")]
    flwr_home_cfg = (f'[superlink]\ndefault = "pilab"\n[superlink.pilab]\n'
                     f'address = "127.0.0.1:{SERVER_PORT}"\nroot-certificates = "{pki / "ca.pem"}"\n')
    run = [b("flwr"), "run", str(APP), "pilab", "--run-config", str(exp / "run_config.toml"), "--stream"]
    return {"superlink": superlink, "flwr_config_toml": flwr_home_cfg, "run": run}


def client_cmd(server: str, cid: int, csv: str, logdir: str, ca: str, runtime_port: int = 9094, bin_dir: str = "") -> list[str]:
    b = (lambda x: str(Path(bin_dir) / x)) if bin_dir else (lambda x: x)
    node = f"client-id={cid} data-path={json.dumps(csv)} log-dir={json.dumps(logdir)}"
    return [b("flower-supernode"), "--superlink", f"{server}:{SERVER_PORT}", "--root-certificates", ca,
            "--host", "127.0.0.1", "--port", str(runtime_port), "--node-config", node]


def cmd_commands(a) -> None:
    exp = OUT_ROOT / a.experiment_id
    pki = Path(a.pki_dir).expanduser()
    s = server_cmds(a, exp, pki)
    j = lambda c: " ".join(shlex.quote(x) for x in c)
    print("# ---- PC (server), terminal 1: SuperLink")
    print(j(s["superlink"]))
    print("\n# ---- PC: one-time Flower CLI profile (~/.flwr/config.toml or $FLWR_HOME/config.toml)")
    print(s["flwr_config_toml"])
    for cid in range(1, a.num_clients + 1):
        print(f"# ---- client {cid} (Pi or PC), copy ca.pem there first")
        print(j(client_cmd(a.server_ip, cid, f"<PATH_ON_THAT_DEVICE>/client_{cid}_train.csv",
                           f"<PATH_ON_THAT_DEVICE>/pi_fl_logs/{a.experiment_id}", "<PATH_ON_THAT_DEVICE>/ca.pem",
                           9094 + cid - 1)))
    print("\n# ---- PC, terminal 2: start the run once all SuperNodes are connected")
    print(j(s["run"]))
    print(f"\n# ---- afterwards\npython scripts/36_pc_pi_federation.py verify --experiment-id {a.experiment_id}")


# ----------------------------------------------------------------------------- verify
def cmd_verify(a) -> dict:
    import pandas as pd
    import torch
    exp = OUT_ROOT / a.experiment_id
    c = json.loads((exp / "config.json").read_text())
    h = pd.read_csv(exp / "training_history.csv")
    cr = pd.read_csv(exp / "client_rounds.csv")
    ck = torch.load(exp / "model.pt", map_location="cpu", weights_only=False)
    ident = json.loads((exp / "client_identity_audit.json").read_text())
    checks = {
        "rounds_completed": len(h) == c["rounds"],
        "updates": len(cr) == c["rounds"] * c["clients_per_round"],
        "aggregation_weights_sum_to_1_each_round": bool((cr.groupby("round")["aggregation_weight"].sum() - 1).abs().max() < 1e-9),
        "aggregation_max_abs_error_lt_1e-6": bool(h["aggregation_max_abs_error"].max() < 1e-6),
        "client_identities": len(ident) == c["num_clients"],
        "model_outputs_84": tuple(ck["state_dict"]["net.4.weight"].shape) == (84, 32),
    }
    res = {"experiment_id": a.experiment_id, "checks": checks, "passed": all(checks.values()),
           "rounds": len(h), "client_updates": len(cr),
           "client_samples": {k: v["samples"] for k, v in ident.items()},
           "uplink_bytes_total": int(h["uplink_serialized_array_bytes"].sum()),
           "downlink_bytes_total": int(h["downlink_serialized_array_bytes"].sum()),
           "client_training_seconds_median_by_client": cr.groupby("client_id")["training_seconds"].median().to_dict(),
           "client_rss_mb_median_by_client": (cr.groupby("client_id")["rss_bytes"].median() / 2**20).to_dict(),
           "training_wall_seconds": ck.get("training_wall_seconds"),
           "model_sha256": sha256(exp / "model.pt"),
           "note": "Hardware identity is taken from each device's own log-dir JSON (platform string); "
                   "a run is Pi-verified only if those logs show an aarch64 Raspberry Pi."}
    p = exp / "verification.json"
    if p.exists():
        p = exp / f"verification_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    p.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))
    return res


# ----------------------------------------------------------------------------- loopback
def cmd_loopback(a) -> None:
    """Everything on this machine; exercises the same commands the lab will use."""
    bin_dir = str(Path(sys.executable).parent)
    connect = a.lan_ip or "127.0.0.1"
    a.server_ip = [connect]
    a.server_dns = []
    pki = Path(a.pki_dir).expanduser()
    if not pki.exists():
        a.days = 2
        cmd_certs(a)
    exp = cmd_prepare(a)
    home = exp / "flwr_home"
    home.mkdir()
    s = server_cmds(a, exp, pki, bin_dir, bind_host="0.0.0.0" if a.lan_ip else "127.0.0.1")
    (home / "config.toml").write_text(s["flwr_config_toml"])
    env = os.environ.copy()
    env.update({"FLWR_HOME": str(home), "FLWR_TELEMETRY_ENABLED": "0",
                "PATH": bin_dir + os.pathsep + env.get("PATH", "")})
    procs, handles, cmds = [], [], [s["superlink"]]
    csvs = a.client_csv
    if len(csvs) != a.num_clients:
        raise SystemExit("--client-csv must be given once per client")
    try:
        log = open(exp / "superlink.log", "x"); handles.append(log)
        procs.append(subprocess.Popen(s["superlink"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT))
        for _ in range(150):
            if procs[0].poll() is not None:
                raise RuntimeError("SuperLink exited; see superlink.log")
            try:
                with socket.create_connection(("127.0.0.1", SERVER_PORT), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError(f"SuperLink not listening on {SERVER_PORT}")
        for cid, csv in enumerate(csvs, start=1):
            cmd = client_cmd(connect, cid, str(Path(csv).resolve()), str(exp / f"device_{cid}"),
                             str(pki / "ca.pem"), 9094 + cid - 1, bin_dir)
            cmds.append(cmd)
            log = open(exp / f"supernode_{cid}.log", "x"); handles.append(log)
            procs.append(subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT))
        time.sleep(4)
        cmds.append(s["run"])
        t0 = time.perf_counter()
        with open(exp / "run.log", "x") as log:
            r = subprocess.run(s["run"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout)
        wall = time.perf_counter() - t0
        if r.returncode != 0:
            raise RuntimeError("flwr run failed; inspect run.log / superlink.log")
        deadline = time.time() + a.timeout
        while not (exp / "model.pt").exists() and time.time() < deadline:
            time.sleep(1)
        (exp / "commands.json").write_text(json.dumps({"commands": cmds, "flwr_run_wall_seconds": wall,
                                                        "scope": "one machine; SuperNodes reach SuperLink via " + connect + "; NOT a Raspberry Pi run"}, indent=2))
    finally:
        for p in reversed(procs):
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait()
        for h in handles:
            h.close()
    cmd_verify(a)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pki_default = "~/.seniorfl_pki/pi_fl_v1"

    p = sub.add_parser("certs"); p.add_argument("--server-ip", nargs="+", required=True)
    p.add_argument("--server-dns", nargs="*", default=[]); p.add_argument("--days", type=int, default=30)
    p.add_argument("--pki-dir", default=pki_default)

    def prep_args(p):
        p.add_argument("--experiment-id", required=True)
        p.add_argument("--num-clients", type=int, default=2)
        p.add_argument("--clients-per-round", type=int)
        p.add_argument("--rounds", type=int, default=5)
        p.add_argument("--local-epochs", type=int, default=1)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--batch-size", type=int, default=128)
        p.add_argument("--learning-rate", type=float, default=0.001)
        p.add_argument("--initial-checkpoint")
        p.add_argument("--partition-note", default="node_local_training_csv")

    p = sub.add_parser("prepare"); prep_args(p)
    p = sub.add_parser("commands"); p.add_argument("--experiment-id", required=True)
    p.add_argument("--server-ip", required=True); p.add_argument("--num-clients", type=int, default=2)
    p.add_argument("--pki-dir", default=pki_default)
    p = sub.add_parser("verify"); p.add_argument("--experiment-id", required=True)
    p = sub.add_parser("loopback"); prep_args(p)
    p.add_argument("--client-csv", nargs="+", required=True)
    p.add_argument("--pki-dir", default="~/.seniorfl_pki/loopback_test")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--lan-ip", help="bind SuperLink on 0.0.0.0 and connect SuperNodes via this non-loopback IP (cert SAN = this IP)")
    a = ap.parse_args()
    {"certs": cmd_certs, "prepare": cmd_prepare, "commands": cmd_commands,
     "verify": cmd_verify, "loopback": cmd_loopback}[a.cmd](a)


if __name__ == "__main__":
    main()
