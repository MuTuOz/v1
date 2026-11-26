# Live feature compatibility report

Status: **PARTIAL / exact DataSense live parity not established**.
This is a measured software-readiness/gap report, not a claim that the existing
model accepts faithfully reproduced live traffic.

## Evidence inspected

The project `README.pdf` describes fixed 1–10 second slices and points to a
paper/docs folder for complete feature definitions. Only the two processed
5-second raw CSVs were found locally; their headers were inspected without
training on raw-source or protected test records. No original PCAP, log capture
or authoritative extractor source was available in the inspected tree. The
[official UNB publication page](https://www.unb.ca/cic/datasets/iiot-dataset-2025.html)
describes synchronized sensor/network data. The linked DataSense publication
retrieval failed (HTTP 429 on the first route; HTTP 403 on the archived direct
request), and no missing-formula workaround or account form
submission was attempted. Retrieval evidence is under the research `sources/`.

## Implemented prototype and explicit boundary

- Frozen ordering: 71 slots, **64 network + 7 log**, recorded in
  [feature_contract.csv](../results/pre_pi_research_v1/phase09/offline_fixture_v2/feature_contract.csv)
  and `feature_schema.json`.
- **53 candidate feature formulas** are implemented under documented engineering
  conventions. Their exact original-dataset semantics are unverified; the
  authoritative-parity count is **zero**, not 53.
- Candidate inputs are IPv4 packets involving an explicit monitored address,
  grouped into UTC five-second half-open windows anchored at a declared origin.
  Source/destination conventions, bytes/seconds, population std (ddof=0), empty
  measurements and log timestamp grouping are explicit.
- **18 feature slots** lack an implemented source-equivalent formula: 14 network
  slots (header-length, MSS and time-delta aggregates plus fragmentation-related
  fields), and four log data-range aggregates. These remain null. In a packet-only
  capture, all seven log slots are unavailable; protocol-specific fields can also
  be unavailable for individual windows.
- Three log candidates require actual explicit monitor-matched service/device
  events: message count, mean message interarrival and distinct supplied data
  types. No log values are inferred from encrypted packets or zero-filled.
- `model_ready` refuses missing slots and also refuses unverified semantic
  parity even if a caller supplies every numeric value. NaN/Inf→0 in the original
  dataset preprocessing is not permission to invent absent live feature values.

`live_pipeline/extract.py` is **offline-only**: it reads an explicitly supplied
PCAP and optional log JSON; it has no sniff/send/attack commands. Initial synthetic
frames omitted MAC addresses, triggering Scapy neighbor-resolution attempts
that the sandbox denied. The old logs are preserved in
`phase09/blocked_neighbor_resolution.json`. Version 2 uses fixed locally
administered synthetic MAC addresses, rejects unspecified Ethernet addresses,
and has tests that fail if neighbor resolution or packet sending is invoked.
No permissions or sandbox settings were changed.

## Tests and reproducibility

The fixture contains three constructed packets in two windows, not captured
traffic and not a device/session evaluation. Tests cover the 5-second boundary,
direction counts, flags/TTL, unrelated traffic exclusion, explicit log alignment,
missing-feature refusal, all 71 schema slots and offline network-resolution
guards. The version-2 output is the canonical fixture evidence.

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python -m unittest discover -s tests -p 'test_live_pipeline.py' -v
# Explicit offline replay; choose a NEW output file:
/home/seniorfl/seniorproject-fl-venv/bin/python -m live_pipeline.extract results/pre_pi_research_v1/phase09/offline_fixture_v2/offline_synthetic_fixture.pcap --monitor-ip 192.0.2.1 --output /tmp/new_offline_features.json
```

Raw PCAP/log hashes, UTC clock offset, capture visibility, grouping/window origin,
parser version, packet drops and mixed-scenario handling must accompany future
captures. Golden windows with authoritative expected raw features are required
before comparing signed-log float32 model tensors/predictions on Pi and WSL.

## Drift and dataset-only alternative

`dataset_drift_diagnostics.csv` reports missingness, signed-log means,
standardized mean differences, KS **distance** and PSI using training-derived
quantile bins on the fixed train/validation sets. These are descriptive
diagnostics; correlated rows do not justify IID p-values. No scaler, model
selection or training labels are changed by the diagnostic.

Two new **network64 dataset-only baselines** (Centralized and actual Flower,
seed 42) were executed with the same validation and training pool. The input
architecture is explicitly **64→64→32→84**; IDs and preprocessing are unchanged.
Their metrics/checkpoints are under `phase09/network64_*`. This is a defensible
log-ablation reference, not proof of live-network parity: fourteen network slots
still need authoritative extraction definitions. If later choosing a smaller
reproducible subset, version the feature contract and retrain matched baselines;
do not silently truncate the 71-input model.

Dataset validation, synthetic offline PCAP replay and newly generated physical
traffic are distinct evidence levels. Exact extractor recovery, independent
sensor/log instrumentation and physical golden-window validation remain open.
