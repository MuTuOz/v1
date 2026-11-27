# MITRE ATT&CK / Atomic Red Team mapping

Every scenario in `scenarios.json` now carries `attack_enterprise_id`/`attack_enterprise_name`
(MITRE ATT&CK Enterprise), `attack_ics_id`/`attack_ics_name` (MITRE ATT&CK **for ICS**, more
appropriate for an IIoT project), and `atomic_red_team_status`. The full table with sources and
per-row notes is [`mitre_attack_mapping.csv`](mitre_attack_mapping.csv). `attack_orchestrator.py`
prints and logs these IDs for every scenario it runs (dry-run or real).

## What this adds for the report

Citing a recognized technique taxonomy for each generated attack row is standard practice in IDS
papers for external validity, and most of your taxonomy's families line up cleanly:

| Your family | Enterprise ATT&CK | ICS ATT&CK |
|---|---|---|
| recon | T1046 / T1018 / T1595.x | **T0846 Remote System Discovery** (+ T0846.001 Port Scan, T0846.002 Broadcast Discovery), T0888 |
| dos / ddos | T1498.001 Direct Network Flood, T1499.002 Service Exhaustion Flood | **T0814 Denial of Service** |
| bruteforce | T1110.001 Password Guessing | T0812 Default Credentials |
| mitm | T1557.002 ARP Cache Poisoning, T1557, T1656 | **T0830 Adversary-in-the-Middle** (renamed from "Man-in-the-Middle") |
| web | T1190 Exploit Public-Facing Application, T1505.003 Web Shell | T0883 Internet Accessible Device |
| malware (mirai-*) | T1498.001 (traffic pattern only — see caveat) | T0814 |

## What is verified vs. not (checked 2026-11-27, via MITRE's own pages and public Atomic
Red Team / Atomic Playbook mirrors — not the live `redcanaryco/atomic-red-team` repo itself,
since this session has no access to run it)

* **Confirmed directly on MITRE's own technique pages** (strongest citation, independent of
  Atomic Red Team): T1498/T1498.001 explicitly lists `hping3`/`nping` as a procedure example —
  every `dos_*`/`ddos_*` flood scenario using `hping3` is a literal instance of this. sqlmap is
  MITRE's own listed software (S0225) for T1190.
* **Atomic Red Team has a public Linux test** for T1046 (nmap-based port scan); exact test
  number differs between repo branches/forks, so don't cite a specific test number without
  checking the current `atomics/T1046/T1046.yaml` yourself (see below).
* **No public Atomic Red Team test currently exists** for T1557.002 (ARP cache poisoning) per
  the mirrors checked. `arpspoof` is the standard tool for the technique, but running it is not
  itself "an Atomic Red Team test" — say so in the report rather than implying otherwise.
* **T1110.001's visible Linux tests don't match our scenario**: the public Linux atomics for
  this technique cover SSH-key/sudo privilege checks, not a dictionary attack against a login
  prompt. Our `hydra` scenarios are mapped to the ATT&CK *technique* (which explicitly names SSH
  and Telnet as targeted services) without claiming an Atomic Red Team test backs them.
* `malware_mirai-*` scenarios are **not** the actual Mirai malware (MITRE software S0450, which
  additionally does default-credential scanning, self-propagation and C2) — they run the same
  `hping3` flood as the matching `dos_*` scenario. This was already flagged in `scenarios.json`
  before this mapping was added; it's repeated here because it's the single biggest risk of
  overclaiming in a report.

## If you want the exact current Atomic Red Team commands/parameters

Clone the official repo on the Kali box (read-only reference; this does **not** run its
PowerShell automation framework, which is why the bash orchestrator here reimplements the
Linux-relevant techniques natively instead of depending on `Invoke-AtomicRedTeam`):

```bash
git clone --depth 1 https://github.com/redcanaryco/atomic-red-team.git ~/atomic-red-team
cat ~/atomic-red-team/atomics/T1046/T1046.yaml   # confirm the current nmap test's exact command
cat ~/atomic-red-team/atomics/T1498.001/T1498.001.yaml
```

Before citing any specific "Atomic Test #N" in your report, read it from that clone, not from
this file or from a search-engine summary — numbering and content change between repo revisions.

## Sources

- [MITRE ATT&CK T1498 / T1498.001](https://attack.mitre.org/techniques/T1498/001/) — hping3/nping procedure example
- [MITRE ATT&CK T1046](https://attack.mitre.org/techniques/T1046/), [Atomic Playbook mirror for T1046](https://cyberbuff.github.io/TheAtomicPlaybook/tactics/discovery/T1046.html)
- [MITRE ATT&CK T1557.002](https://attack.mitre.org/techniques/T1557/002), [Atomic Playbook mirror for T1557.002](https://cyberbuff.github.io/TheAtomicPlaybook/tactics/collection/T1557.002.html) (no tests listed)
- [MITRE ATT&CK T1110.001](https://attack.mitre.org/techniques/T1110/001/), [Atomic Playbook mirror for T1110.001](https://cyberbuff.github.io/TheAtomicPlaybook/tactics/credential-access/T1110.001.html)
- [MITRE ATT&CK T1190](https://attack.mitre.org/techniques/T1190/), [sqlmap / S0225](https://attack.mitre.org/software/S0225/)
- [MITRE ATT&CK for ICS: T0814 Denial of Service](https://attack.mitre.org/techniques/T0814), [T0830 Adversary-in-the-Middle](https://attack.mitre.org/techniques/ics/), [T0812 Default Credentials](https://attack.mitre.org/techniques/T0812), [T0846 Remote System Discovery](https://attack.mitre.org/techniques/T0846), [T0846.001 Port Scan](https://attack.mitre.org/techniques/T0846/001), [T0888 Remote System Information Discovery](https://attack.mitre.org/techniques/T0888)
