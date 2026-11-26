# Physical PC-server / Raspberry Pi-client Flower runs — 2026-11-26

Question answered: *"Does it work with the PC as server and the Pi as client?"* — **Yes, for the two
runs below.** A real Raspberry Pi 5 ran a Flower 1.40.0 SuperNode that connected over the lab Wi-Fi with
TLS to a SuperLink running on the PC (WSL2), received the app, trained the 71→64→32→84 MLP on its own
training CSV and returned updates that were aggregated with sample-weighted FedAvg. These are
**physical two-device runs, not simulation**. They are short functional/performance runs (3 and 5 rounds,
balanced training-only allocation, seed 42) and are **not** a new accuracy experiment: no validation or
test file was read and no model was evaluated.

## Devices

| role | hardware (as reported by the device itself) | OS / platform string | Python / flwr / torch |
|---|---|---|---|
| SuperLink + ServerApp (+ client 1 in run 2) | 13th Gen Intel Core i7-13620H, 16 logical CPUs; Windows 11 + WSL2 Ubuntu, `networkingMode=mirrored` | `Linux-6.6.87.2-microsoft-standard-WSL2-x86_64-with-glibc2.39` | 3.12.3 / 1.40.0 / 2.15.0+cpu |
| SuperNode, client 2 | `/proc/device-tree/model` = **Raspberry Pi 5 Model B Rev 1.0**, 4 cores, 8 GB RAM | `Linux-6.12.96+rpt-rpi-2712-aarch64-with-glibc2.36` (Debian 12 Bookworm) | 3.11.2 / 1.40.0 / 2.15.0+cpu |

Network: PC `10.96.27.14`, Pi `10.96.27.10` (`wlan0`), same /24 Wi-Fi subnet; clocks checked equal in UTC
before the runs. TLS: throw-away lab CA (keys outside the repository, `~/.seniorfl_pki/pi_fl_v1` in WSL),
server SAN = `localhost, 127.0.0.1, 10.96.27.14`; only `ca.pem` (sha256 `38a5cba0…b314e`) was copied to
the Pi. SuperNode authentication was **disabled** (any node on the subnet could join).

Hardware identity evidence: each Pi per-round JSON in `device_2_pi/` carries the platform string above;
`device_2_pi/device_identity.txt` holds `/proc/device-tree/model`, `uname -a` and the Pi IP captured over
SSH at SuperNode start. SuperLink logs show the Pi registering from `10.96.27.10`. A screenshot of the Pi
terminal is **not yet saved** (requested from the team; see `screenshots/README.md` in each run).

## Runs

| experiment | clients | rounds | updates | verify | flwr run wall s | training wall s (ServerApp) |
|---|---|---|---|---|---|---|
| [`pi_lan_1client_r3_s42`](pi_lan_1client_r3_s42/verification.json) | Pi (client 2, 4,490 rows) | 3 | 3/3 | passed | 45.36 | 30.14 |
| [`pi_lan_2clients_r5_s42`](pi_lan_2clients_r5_s42/verification.json) | PC (client 1, 4,491 rows) + Pi (client 2, 4,490 rows) | 5 | 10/10 | passed | 60.59 | 45.56 |

Training data: `results/pre_pi_research_v1/audit/allocations/balanced/client_{1,2}_train.csv`
(sha256 client_1 `6c43b9c5…a76e`, client_2 `6b05b9db…d938`; the Pi copy hash equals the source).
Aggregation weights per round in run 2: 4491/8981 and 4490/8981; max |aggregate − manual weighted mean|
≤ 2.47e-08 in every round. Adam is re-created on each client every round.

### Per-round timing ([run 2 table](pi_lan_2clients_r5_s42/round_timing_v2.csv), [run 1 table](pi_lan_1client_r3_s42/round_timing_v2.csv))

| quantity (run 2, 5 rounds) | Pi client 2 | PC client 1 |
|---|---|---|
| local training seconds per round, median of 5 | 1.518 | 0.725 |
| interval between consecutive round JSONs, median of rounds 2–5 | 9.03 s | — (per-round values 10.01/8.93/6.96/10.05) |
| Pi finished after PC, per round (s) | 2.78, 1.75, 1.90, 2.94, 2.02 | |
| client RSS at end of training, median | 444.1 MiB | 427.2 MiB |

Server-side round duration (coarse; ServerApp log-chunk flush times): 10.22, 9.45, 6.67, 9.46, 9.77 s.
Only ~1.5 s of a ~9 s Pi round is local training; the rest is ClientApp process start each round
(Flower subprocess isolation imports torch/pandas), CSV load, 10 warm inference batches, transport and
polling delay. This decomposition is inferred, not separately timed.

### Communication

* Serialized model update (ArrayRecord) = **38,674 bytes** per client per direction per round
  (9,460 float32 parameters = 37,840 bytes + record overhead). Run 2: 10 updates → uplink 386,740 B and
  downlink 386,740 B (application payload only).
* Flower SuperLink run-table counters: run 1 bytes_sent 143,022 / bytes_recv 129,039; run 2 bytes_sent
  471,492 / bytes_recv 428,554 (run level, all nodes; Flower's own counting).
* Pi `wlan0` counter deltas around `flwr run` (all interface traffic incl. SSH, heartbeats, FAB download,
  TLS — upper bound): run 1 rx 237,562 / tx 303,656 B; run 2 rx 360,338 / tx 491,344 B.
* PC interface counters were **not measured** (WSL2 mirrored `eth2` counters read 0/0).

## Inference benchmark (scripts/35, same commit, 1 thread, 2,000 reps after 200 warm-up, 2,000 training rows)

| model | metric | PC i7-13620H (WSL2) | Raspberry Pi 5 |
|---|---|---|---|
| subtype_flower_val_v1.pt | single record, preprocess+model, median / p95 / p99 ms | 0.0250 / 0.0380 / 0.0890 | 0.3990 / 0.4130 / 0.4220 |
| subtype_flower_val_v1.pt | batch 128, model only: median ms, rows/s | 0.0373, 3,433,292 | 0.3067, 417,385 |
| subtype_centralized_val_v1.pt | single record, preprocess+model, median ms | 0.0243 | 0.3972 |
| family_rf_5sec.onnx (onnxruntime 1.32.0) | single record median ms; batch 128 rows/s | 0.0068; 285,776 | 0.0272; 128,364 |

Pi CPU temperature 49.05 °C at start, 51.8 °C at end of the benchmark. Results:
[PC](../performance_v1/pc_i7-13620H_wsl2_20261126T135402Z/benchmark.json),
[Pi](../performance_v1/pi5_model_b_8gb_arm64_20261126T141016Z/benchmark.json) (run on the Pi from a clone
of the same commit `004444e`; output copied back unchanged). The PC `script_sha256` differs from the Pi's
only because the Windows checkout uses CRLF (`core.autocrlf=true`); LF-normalised content hashes are equal
(`0e53bd11…b501`). Energy/power was **not measured**.

## Failures kept (not deleted)

* Pi SuperNode attempt 1 (run 1): `FileNotFoundError: flower-superexec` — venv `bin` not on PATH.
  Attempt 2: Runtime API failed to start because attempt 1's process still held port 9094. Both happened
  before any run was created; logs: `pi_lan_1client_r3_s42/device_2_pi/FAILED_attempt0*.log`.
* First Pi `pip install torch` pulled multi-hundred-MB CUDA wheels from PyPI; stopped and reinstalled
  from the PyTorch CPU index (`torch 2.15.0+cpu`, zero `nvidia-*` packages).
* `scripts/37` v1 read purged message tables and wrote empty tables, kept as
  `FAILED_v1_message_tables_empty_*`; v2 outputs are `round_timing_v2.csv` / `timing_and_bytes_summary_v2.json`.

## Environment changes made on the PC (outside the repository)

* `%UserProfile%\.wslconfig` created with `[wsl2] networkingMode=mirrored` (file did not exist before).
* Windows Firewall inbound rule `SeniorFL SuperLink 9092 (lab)` and Hyper-V firewall rule `SeniorFL9092`,
  TCP 9092, remote addresses `10.96.27.0/24` only. Remove with
  `Remove-NetFirewallRule -DisplayName "SeniorFL*"` and `Remove-NetFirewallHyperVRule -Name SeniorFL9092`.
* Repository-local `git config core.longpaths true` (needed to check out an existing long `__pycache__` path).

## Limitations

* Two short runs, one seed, one Pi, one partition; no accuracy evaluation of the resulting models.
* Not on an isolated lab network: shared Wi-Fi subnet; SuperNode authentication disabled; TLS server-auth only (no mTLS, no secure aggregation).
* The PC client in run 2 is a WSL2 process on the server machine, not a second edge device.
* Timing is coarse (file mtimes, log flush times); communication counters are payload-level or interface upper bounds, not packet captures.
* No live traffic, Kali generation or live feature-parity claim follows from these runs.
