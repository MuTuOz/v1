# performance_v1 — "not only accuracy": inference, memory and communication cost

Script: [`scripts/35_performance_benchmark.py`](../../scripts/35_performance_benchmark.py). Every run writes
`results/performance_v1/<device-label>_<UTC>/benchmark.json` (+ communication table) and never overwrites.
**Each run describes only the machine it ran on.** The first run below is a cloud x86 container, not the
lab PC and not a Raspberry Pi. Run the same command on the PC and on the Pi to fill the comparison table.

```bash
python scripts/35_performance_benchmark.py --device-label pc_x86
python scripts/35_performance_benchmark.py --device-label pi4_arm64   # on the Pi
```

Inputs: saved checkpoints and 2,000 **training-only** rows (balanced allocation client 1) used only as
realistic feature vectors; no validation/test file is read. One PyTorch / ONNX Runtime thread.

## 1. Inference (run `cloud_x86_container_20261126T125602Z`)

Machine: Intel Xeon @ 2.10 GHz, 4 vCPU, 16 GB, Linux 6.18 container, Python 3.13.18, torch 2.15.0.
2,000 timed repetitions after 200 warm-up calls; percentiles of wall time per call.

| Model | Params | File bytes | 1 record, model only (median / p99 ms) | 1 record incl. preprocessing (median / p99 ms) | batch 128 rows/s (median) |
|---|---:|---:|---:|---:|---:|
| 84-class MLP, Flower (`subtype_flower_val_v1.pt`) | 9,460 | 49,557 | 0.0190 / 0.0451 | 0.0354 / 0.0765 | 2.91 M |
| 84-class MLP, centralized (`subtype_centralized_val_v1.pt`) | 9,460 | 45,845 | 0.0195 / 0.0492 | 0.0376 / 0.1023 | 2.76 M |
| 8-class family RF, ONNX (`family_rf_5sec.onnx`) | — | 5,968,368 | 0.0097 / 0.0298 | (raw features) | 0.17 M |

The 9,460 float32 weights are 37,840 bytes; one serialized Flower update is 38,674 bytes. A 5-second
feature window needs well under 1 ms of model time on this machine, so model inference is not the
bottleneck; feature extraction from packets (not measured here; see `docs/live_feature_compatibility_report.md`)
and capture are. Process RSS numbers in `benchmark.json` include the whole PyTorch runtime of this
environment and are not a model-memory measurement.

## 2. Communication per round (from saved Flower runs, application payload only)

Source: `communication_from_saved_flower_runs.csv` (built from each run's `training_history.csv` /
`client_rounds.csv`). Serialized ArrayRecord sizes; TLS, HTTP framing, config messages and retries
are **not** included.

| Quantity | Value |
|---|---:|
| one client update (uplink) or global model (downlink) | 38,674 B |
| one round, 5 clients, uplink | 193,370 B |
| 15 rounds, uplink + downlink, 5 clients | 5.80 MB |
| 15 rounds, 3-of-5 participation | 3.48 MB |
| centralized alternative: ship 22,450 training vectors once (71 × float32) | 6.38 MB |
| median client training time per round (1 epoch, simulation on WSL2 x86) | 0.064–0.089 s (2 epochs: 0.158 s) |

Accuracy vs. communication for the same 5.80 MB budget (seed 42): original allocation detection
recall 0.726, balanced 0.770, exclusive 0.632; inverse-frequency loss 0.847. Communication cost is fixed
by model size × clients × rounds; what changes the outcome for the same bytes is data heterogeneity and
loss weighting. A federated round is not a centralized epoch (Adam reset per round, different number of
optimizer steps; see `results/pre_pi_research_v1/phase05/training_and_payload_budgets.csv`).

Not yet measured and needed from the lab: per-round wall time over Wi-Fi/Ethernet between PC and Pi,
bytes on the wire (e.g. `tcpdump`/`ifstat` counters on the PC interface during a run), Pi CPU
temperature/throttling, and energy (requires a USB power meter; cannot be inferred from time).
`scripts/36_pc_pi_federation.py verify` reports per-client training time and RSS from the real run.

## 3. Loopback federation checks (this session)

| Run | Path exercised | Result |
|---|---|---|
| `results/pi_fl_v1/loopback_check_2clients_r3_s42` | SuperLink 127.0.0.1:9092 + 2 SuperNodes, TLS | passed: 3 rounds, 6 updates, weights verified |
| `results/pi_fl_v1/lanip_check_2clients_r3_s42` | SuperLink bound 0.0.0.0:9092, SuperNodes via non-loopback IP, cert SAN = that IP | passed: 3 rounds, 6 updates |
| `results/pi_fl_v1/FAILED_attempt01_*` (2 dirs) | deprecated `--fleet-api-address` flags (SuperLink stayed on 127.0.0.1:8000); proxy env var not bypassed for the test IP | kept as failure evidence |

Data: balanced allocation clients 1–2 and 3–4 (training rows only, 4,488–4,493 rows each). These runs
are on one x86 machine; **they do not establish Raspberry Pi execution.**
