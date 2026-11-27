# Kali lab attack automation

**Need to set up Kali itself first (VMware or an alternative)?** See
[`kali_vm_kurulum_tr.md`](kali_vm_kurulum_tr.md) (Turkish).

Automates the scenarios in `../docs/kali_lab_deployment_plan.md` against **your
own isolated Pi/target**, mapped to the project's taxonomy
(`../results/attack_taxonomy_5sec.csv`). Runs on the Kali box, not on the Pi
and not in the cloud session that wrote these files (no Kali/Pi access from
there — this was prepared for you to run).

**No code here has been executed against real hardware.** Nothing is
verified until you run it and attach target-side evidence.

## Files

| File | Purpose |
|---|---|
| `scenarios.json` | per-`label3` tool + command template, one entry per taxonomy subtype you can automate today |
| `attack_orchestrator.py` | runs a chosen list of scenarios back-to-back with cooldowns, writes `manifest.json` |
| `attach_target_evidence.py` | merges what you observed on the **target** into that manifest — required before any row counts as ground truth |
| `make_synthetic_wordlists.py` | synthetic (not leaked) user/password list for `bruteforce_*` |
| `mitre_attack_mapping.csv` | MITRE ATT&CK Enterprise + ATT&CK for ICS technique id per scenario, with sourced notes |
| `ATOMIC_RED_TEAM_NOTES.md` | what's confirmed vs. not for each technique/Atomic Red Team test, and how to pull the live repo for exact current commands |

Every scenario in `scenarios.json` carries `attack_enterprise_id`, `attack_ics_id` and
`atomic_red_team_status`; the orchestrator prints and logs them for every run. **Read
`ATOMIC_RED_TEAM_NOTES.md` before citing a specific Atomic Red Team test number in your report** —
several techniques here (e.g. ARP spoofing, the hydra dictionary scenarios) have no confirmed
public Atomic Red Team test behind them; they are mapped to the MITRE ATT&CK technique itself.

## Install (on the Kali box)

```bash
sudo apt update && sudo apt install -y nmap hping3 hydra ettercap-text-only \
    dsniff slowhttptest sqlmap mosquitto-clients tcpdump
```
(`dsniff` provides `arpspoof`.)

## One-time setup per scenario family

* **recon / dos / ddos / mitm**: just need the target's IP and your attacker
  interface — nothing to install on the target beyond it running normally.
* **bruteforce_***: create a **disposable** test account on the target
  (`ssh`/`telnet`) with a password you choose, then:
  ```bash
  python3 make_synthetic_wordlists.py --hit-password <your-test-password>
  ```
* **web_***: deploy a disposable intentionally-vulnerable app on the target
  (e.g. DVWA). Fill in `--web-path` to the actual vulnerable endpoint your
  install exposes; the commands in `scenarios.json` are skeletons, not
  guaranteed to match DVWA's default paths without checking them yourself.
* **malware_mirai-***: read the note in `scenarios.json` first — these run
  the *traffic pattern* (hping3 SYN/UDP flood), not actual Mirai malware.
  Decide with your advisor whether that is acceptable evidence for the
  malware family label in a new training/evaluation session.
* **ddos_***: pass `--extra-attackers user@host1,user@host2` (passwordless
  SSH already set up) to actually run from multiple sources; without it the
  scenario is automatically downgraded to a logged `dos_*` run.

## `--port` only applies to a few scenarios — it does not retarget a named one

A scenario id like `dos_syn-flood-port-80` has its port **hard-coded in the
command template**, to keep the scenario id and the traffic it actually
produces always matching (so a result never gets silently mislabeled). The
global `--port` flag only takes effect for the handful of scenarios whose
`cmd` in `scenarios.json` contains the `{port}` placeholder (currently
`dos_udp-flood`, `dos_udp-frag-flood`, `dos_connect-flood`,
`dos_http-flood-port-80`, `dos_mqtt-publish-flood` and the matching
`ddos_*` ones). **To attack a different fixed port, use (or add) a scenario
id for that exact port** instead of passing `--port` to a `-port-N` scenario
id — e.g. `dos_syn-flood-port-22` for SSH, which exists in `scenarios.json`
precisely because this came up in testing: passing `--port 22` to
`dos_syn-flood-port-80` silently kept flooding port 80, since that
template has no `{port}` in it at all. If you need a fixed-port variant
that isn't in the catalogue yet, add it as a new entry (same pattern as
`dos_syn-flood-port-22`) rather than trying to repurpose an existing one.

## Run it

```bash
# 1. Preview every command — runs nothing.
python3 attack_orchestrator.py \
  --target 10.77.20.60 --gateway 10.77.20.1 --iface eth1 \
  --allowed-subnet 10.77.20.0/24 --subnet 10.77.20.0/24 \
  --experiment-id kali_session01 --session-id s01 \
  --scenarios recon_port-scan,recon_os-scan,dos_syn-flood-port-80,dos_udp-flood \
  --duration 15 --cooldown 10 --dry-run

# 2. Actually run (needs root for hping3/nmap -O/arpspoof; drop --dry-run,
#    add the confirmation phrase after re-reading the isolation plan).
sudo python3 attack_orchestrator.py \
  --target 10.77.20.60 --gateway 10.77.20.1 --iface eth1 \
  --allowed-subnet 10.77.20.0/24 --subnet 10.77.20.0/24 \
  --experiment-id kali_session01 --session-id s01 \
  --scenarios recon_port-scan,recon_os-scan,dos_syn-flood-port-80,dos_udp-flood \
  --duration 15 --cooldown 10 --capture \
  --i-confirm-isolated-lab "I OWN THIS NETWORK"
```

Everything lands in `runs/<experiment-id>_<session-id>/`: one log (and PCAP
with `--capture`) per scenario, plus `manifest.json` with UTC boundaries,
the exact command, return code, and an `ambiguity_flag` that starts `true`.

## Attach target-side evidence (required)

The attacker side alone never proves an attack worked. On the target, during
or right after each scenario, capture something real: service log lines,
`vmstat`/`top` snapshot, a dropped-connection count, failed-login count. Then:

```bash
python3 attach_target_evidence.py --manifest runs/kali_session01_s01/manifest.json \
  --run-id dos_syn-flood-port-80_000 \
  --effect "nginx access.log: 0 completed requests in the window; vmstat shows 98% CPU, run queue 40" \
  --evidence-file /path/to/vmstat_snapshot.txt
```

Only after this step should a run's rows be treated as labelled ground truth
for a new training/evaluation session, per the plan's rule that scenario
labels come from orchestration **plus** target evidence, never from the
model itself.

## Safety limits built into the script

* `--scenarios all` is refused — you always name what will run.
* `--duration` capped at 120 s unless you pass `--allow-long`.
* Every command is wrapped in `timeout`; nothing runs forever.
* Target/gateway/subnet must fall inside `--allowed-subnet`, or the script
  refuses — this is a software sanity check only, **not** a substitute for
  the physical/network isolation checklist in the deployment plan.
* Won't execute at all without `--i-confirm-isolated-lab "I OWN THIS NETWORK"`
  (ignored for `--dry-run`).
