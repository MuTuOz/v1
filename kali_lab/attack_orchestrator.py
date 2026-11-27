#!/usr/bin/env python3
"""Automated attack-scenario orchestrator for the isolated Kali lab.

Runs on the Kali attacker box (not on the Pi, not in this cloud container).
Scope and rules come from ../docs/kali_lab_deployment_plan.md: isolated lab
only, owned devices only, labels are *intended* labels from orchestration,
never proof of compromise — target-side evidence must be attached separately
(see attach_target_evidence.py).

Usage
-----
    # 1. Dry run first: print every command, run nothing.
    python3 attack_orchestrator.py \\
        --target 10.77.20.60 --gateway 10.77.20.1 --iface eth1 \\
        --allowed-subnet 10.77.20.0/24 --subnet 10.77.20.0/24 \\
        --scenarios recon_port-scan,dos_syn-flood-port-80 \\
        --experiment-id kali_lab_session_01 --session-id s01 \\
        --duration 10 --cooldown 5 --dry-run

    # 2. Remove --dry-run and add the confirmation phrase to actually run.
    python3 attack_orchestrator.py ... --i-confirm-isolated-lab "I OWN THIS NETWORK"

Safety notes (read before use)
-------------------------------
* This script CANNOT verify that your network is actually isolated. It only
  checks that --target/--gateway/--subnet fall inside --allowed-subnet, which
  you must set correctly yourself per the plan's addressing section.
* `--scenarios all` is refused; you must name scenarios explicitly, so you
  always know what is about to run.
* Every run is wrapped in `timeout {duration}`; nothing runs forever.
* ddos_* scenarios need --extra-attackers (passwordless-SSH hosts) or they
  are downgraded to a logged dos_* run with a note, per the plan's rule that
  one Kali VM is not automatically a distributed attack.
* Scenarios requiring root (hping3 raw sockets, arpspoof, nmap -O) must be
  run as root on the Kali box; the script does not escalate privileges itself.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import platform
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOGUE = json.loads((HERE / "scenarios.json").read_text())
CONFIRM_PHRASE = "I OWN THIS NETWORK"


def sha256_file(p: Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def in_subnet(ip: str, subnet: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        return False


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def build_cmd(entry: dict, a: argparse.Namespace, scenario_id: str) -> tuple[str, str]:
    """Returns (effective_label2, shell_command)."""
    label2 = entry["label2"]
    if entry.get("requires_multi_source") and not a.extra_attackers:
        label2 = "dos"  # downgrade, per plan: one Kali VM != distributed attack
    fields = {
        "target": a.target, "iface": a.iface, "port": a.port, "duration": a.duration,
        "gateway": a.gateway or "", "subnet": a.subnet or "", "userlist": a.userlist or "",
        "wordlist": a.wordlist or "", "web_path": a.web_path or "", "upload_file": a.upload_file or "",
    }
    try:
        raw = entry["cmd"].format(**fields)
    except KeyError as e:
        raise SystemExit(f"{scenario_id}: missing required placeholder {e}; pass the matching --flag")
    return label2, raw


def run_local(cmd: str, duration: int, log_path: Path) -> dict:
    wrapped = f"timeout {duration + 2}s bash -c {shlex.quote(cmd)}"
    start = time.perf_counter()
    with open(log_path, "w") as log:
        proc = subprocess.run(["bash", "-lc", wrapped], stdout=log, stderr=subprocess.STDOUT)
    return {"returncode": proc.returncode, "wall_seconds": time.perf_counter() - start}


def run_remote(host: str, cmd: str, duration: int) -> subprocess.Popen:
    wrapped = f"timeout {duration + 2}s bash -c {shlex.quote(cmd)}"
    return subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, wrapped])


def start_capture(iface: str, out_pcap: Path, host_filter: str, duration: int) -> subprocess.Popen | None:
    try:
        return subprocess.Popen(
            ["tcpdump", "-i", iface, "-w", str(out_pcap), "host", host_filter],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("  (tcpdump not found; no PCAP captured for this scenario)", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True, help="owned target device/service IP")
    ap.add_argument("--iface", required=True, help="attacker interface on the lab segment")
    ap.add_argument("--allowed-subnet", required=True, help="CIDR the lab is confined to, e.g. 10.77.20.0/24")
    ap.add_argument("--gateway", help="required for mitm_* scenarios")
    ap.add_argument("--subnet", help="CIDR for *_ping-sweep style scenarios")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--userlist"); ap.add_argument("--wordlist")
    ap.add_argument("--web-path"); ap.add_argument("--upload-file")
    ap.add_argument("--scenarios", required=True,
                    help="comma-separated scenario ids from scenarios.json, e.g. recon_port-scan,dos_udp-flood "
                         "(the literal word 'all' is refused)")
    ap.add_argument("--duration", type=int, default=10, help="seconds per scenario (hard-capped at 120 unless --allow-long)")
    ap.add_argument("--allow-long", action="store_true")
    ap.add_argument("--cooldown", type=int, default=5, help="seconds of silence between scenarios")
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--client-id", help="FL client this traffic/capture maps to, if any")
    ap.add_argument("--extra-attackers", help="comma-separated ssh targets (user@host) for true multi-source ddos_*")
    ap.add_argument("--capture", action="store_true", help="run tcpdump per scenario (requires root/CAP_NET_RAW)")
    ap.add_argument("--out", default=None, help="output dir; default kali_lab/runs/<experiment-id>_<session-id>")
    ap.add_argument("--dry-run", action="store_true", help="print commands and manifest, run nothing")
    ap.add_argument("--i-confirm-isolated-lab", default="", help=f'must equal exactly "{CONFIRM_PHRASE}" to execute (ignored with --dry-run)')
    a = ap.parse_args()

    if a.scenarios.strip().lower() == "all":
        raise SystemExit("--scenarios all is refused; name the scenarios explicitly")
    if a.duration > 120 and not a.allow_long:
        raise SystemExit(f"--duration {a.duration}s exceeds the 120s default cap; pass --allow-long if your team agreed to a longer run")
    if not a.dry_run and a.i_confirm_isolated_lab != CONFIRM_PHRASE:
        raise SystemExit(f'Refusing to execute: pass --i-confirm-isolated-lab "{CONFIRM_PHRASE}" '
                         f"after re-reading docs/kali_lab_deployment_plan.md, or use --dry-run to preview.")

    ids = [s.strip() for s in a.scenarios.split(",") if s.strip()]
    unknown = [s for s in ids if s not in CATALOGUE]
    if unknown:
        raise SystemExit(f"unknown scenario id(s): {unknown}\navailable: {sorted(CATALOGUE)}")

    for name, val in (("target", a.target), ("gateway", a.gateway), ("subnet", a.subnet and a.subnet.split("/")[0])):
        if val and not in_subnet(val, a.allowed_subnet):
            raise SystemExit(f"--{name} {val} is outside --allowed-subnet {a.allowed_subnet}; "
                             f"this script will not touch addresses outside your declared lab range")

    out = Path(a.out) if a.out else HERE / "runs" / f"{a.experiment_id}_{a.session_id}"
    if out.exists() and not a.dry_run:
        raise SystemExit(f"refusing to overwrite existing {out}")
    if not a.dry_run:
        out.mkdir(parents=True)

    env_info = {}
    try:
        env_info["ip_addr"] = subprocess.run(["ip", "addr"], capture_output=True, text=True, timeout=5).stdout
        env_info["ip_route"] = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=5).stdout
    except Exception as e:
        env_info["error"] = str(e)

    extra_hosts = [h.strip() for h in a.extra_attackers.split(",")] if a.extra_attackers else []
    manifest = {
        "experiment_id": a.experiment_id, "session_id": a.session_id, "client_id": a.client_id,
        "attacker_role": "this Kali host", "attacker_device_os": platform.platform(),
        "target_role": a.target, "capture_role": a.iface if a.capture else None,
        "extra_attacker_hosts": extra_hosts, "allowed_subnet": a.allowed_subnet,
        "created_utc": utc_now(), "dry_run": a.dry_run,
        "label_evidence": "ORCHESTRATION-ONLY; attach target-side evidence with attach_target_evidence.py "
                          "before treating any row here as ground truth",
        "network_snapshot_at_start": env_info,
        "runs": [],
    }

    print(f"{'DRY RUN — ' if a.dry_run else ''}{len(ids)} scenario(s), {a.duration}s each, {a.cooldown}s cooldown")
    for i, sid in enumerate(ids):
        entry = CATALOGUE[sid]
        label2, cmd = build_cmd(entry, a, sid)
        run_id = f"{sid}_{i:03d}"
        print(f"\n[{run_id}] label2={label2} label3={entry['label3']} tool={entry.get('tool')}")
        print(f"  ATT&CK enterprise: {entry.get('attack_enterprise_id')} {entry.get('attack_enterprise_name')}")
        print(f"  ATT&CK ICS: {entry.get('attack_ics_id')} {entry.get('attack_ics_name')}")
        print(f"  Atomic Red Team: {entry.get('atomic_red_team_status')}")
        print(f"  $ {cmd}")
        if entry.get("notes"):
            print(f"  note: {entry['notes']}")
        if a.dry_run:
            manifest["runs"].append({"run_id": run_id, "scenario_id": sid, "intended_family": entry["label2"],
                                     "effective_family": label2, "intended_subtype": entry["label3"],
                                     "attack_enterprise_id": entry.get("attack_enterprise_id"),
                                     "attack_ics_id": entry.get("attack_ics_id"),
                                     "atomic_red_team_status": entry.get("atomic_red_team_status"),
                                     "command": cmd, "executed": False})
            continue

        start_t = utc_now()
        pcap = out / f"{run_id}.pcap"
        cap_proc = start_capture(a.iface, pcap, a.target, a.duration) if a.capture else None
        remote_procs = []
        if entry.get("requires_multi_source") and extra_hosts:
            remote_procs = [run_remote(h, cmd, a.duration) for h in extra_hosts]
        log_path = out / f"{run_id}.log"
        result = run_local(cmd, a.duration, log_path)
        for p in remote_procs:
            try:
                p.wait(timeout=a.duration + 15)
            except subprocess.TimeoutExpired:
                p.kill()
        if cap_proc:
            time.sleep(1)
            cap_proc.terminate()
            try:
                cap_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cap_proc.kill()
        end_t = utc_now()
        manifest["runs"].append({
            "run_id": run_id, "scenario_id": sid, "intended_family": entry["label2"],
            "effective_family": label2, "intended_subtype": entry["label3"], "tool": entry.get("tool"),
            "attack_enterprise_id": entry.get("attack_enterprise_id"),
            "attack_enterprise_name": entry.get("attack_enterprise_name"),
            "attack_ics_id": entry.get("attack_ics_id"), "attack_ics_name": entry.get("attack_ics_name"),
            "atomic_red_team_status": entry.get("atomic_red_team_status"),
            "command": cmd, "executed": True, "start_utc": start_t, "end_utc": end_t,
            "duration_s": a.duration, "returncode": result["returncode"], "wall_seconds": result["wall_seconds"],
            "remote_attacker_count": len(remote_procs), "log_file": str(log_path.relative_to(out)),
            "pcap_file": str(pcap.relative_to(out)) if cap_proc else None,
            "pcap_sha256": sha256_file(pcap) if cap_proc else None,
            "ambiguity_flag": True,
            "actual_effect": "not yet evaluated — inspect target-side logs/resource graphs and attach with attach_target_evidence.py",
        })
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
        if i < len(ids) - 1:
            print(f"  cooldown {a.cooldown}s ...")
            time.sleep(a.cooldown)

    if not a.dry_run:
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"\nwrote {out / 'manifest.json'}")
        print("Labels above are INTENDED labels only. Run attach_target_evidence.py with the "
              "target's own logs/metrics before treating any row as ground truth for training/evaluation.")
    else:
        print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
