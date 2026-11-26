# Project status

Evidence reviewed: **2026-10-25**. This documentation update inspected the proposal, source, saved checkpoints, metrics and reports; it did not train models, rerun evaluation or implement future experiments. Numerical values below are copied from saved evidence, without additional rounding unless explicitly identified as printed log values.

## Research specification and completion boundary

[Proposal](references/proposal.docx): **Hierarchical Evaluation of Cyber Event Classification in Industrial IoT Networks**. The main question is whether collaborative learning improves recognition of attacks absent from an individual client’s training data but present at other clients. The planned comparison is local-only vs federated vs centralized learning under Non-IID distributions, with leakage-aware splits, per-class reports, false alarms and hierarchical error analysis.

Implemented evidence includes dataset audits and splits, RF/MLP model artifacts, five historical 8-class local models, custom PyTorch FedAvg experiments, Flower simulations, and matched centralized/Flower 84-class validation_v1 results. The current matched 84-class comparison has **no completed local-only arm**. Historical locally unseen reports exist on another split; they do not complete the current validation_v1 research question. Formal tree-based evaluation, repeated-seed/imbalance studies, a dashboard and physical federated clients are not established as complete by the inspected evidence.

## Current data and model conventions

- Data source named by the proposal: DataSense CIC IIoT 2025. The preparation code uses 5-second sample tables under `data/raw/all_attack_benign_samples/`.
- Detection: `label1` (benign/attack). Family: `label2` (benign plus bruteforce, ddos, dos, malware, mitm, recon, web). Subtype: `label4` (benign plus 83 attack subtypes); `label3` is additional attack descriptor metadata.
- Current training: `data/validation_v1/train.csv`, **22,450 rows**. Client sizes: **4,430 / 6,216 / 2,901 / 5,103 / 3,800**. Existing Non-IID partitions are preserved.
- Validation: `data/validation_v1/validation.csv`, **6,486 rows = 3,838 benign + 2,648 attack**; **28 observed subtypes**, including benign, and **7 observed families**. No web-family validation rows.
- The split manifest records 36 selected attack candidate episodes, a 5-minute benign temporal gap and 2,280 excluded benign rows. The 31,216-row earlier training pool became 22,450 training + 6,486 validation + 2,280 excluded rows.
- The subtype audit verified training-derived class/mapping equality with the centralized checkpoint, unique subtype→family mapping, identical initialization at seed 42, identical preprocessing, zero attack candidate-episode overlap and zero full-row overlap between training and validation. Client-union metadata identities and preprocessed float32 tensors match centralized training exactly. Two raw parsed numbers differ by at most **4.1359030627651384e-25**, with no difference in model inputs.
- MLP input: 71 ordered network/log features; NaN/±Inf→0, ±1e8 clip, signed log1p, float32 output. No label/device/time/episode metadata inputs. Classes are benign first, then sorted attack subtypes. Family/detection outputs of a subtype model are derived from its predicted subtype, not separate trained heads.

Sources: [split manifest](results/validation_v1_manifest.json), [experiment data audit](results/subtype_flower_val_v1/data_audit.json), [class mapping and client coverage](results/subtype_flower_val_v1/class_mapping_and_coverage.csv), [client family counts](results/subtype_flower_val_v1/client_family_counts.csv).

## Completed matched 84-class validation_v1 experiment

Models: [centralized checkpoint](models/subtype_centralized_val_v1.pt) and [Flower checkpoint](models/subtype_flower_val_v1.pt). Both inspected checkpoint schemas have 71 inputs and 84 outputs. The architecture is **71→64→32→84**, ReLU, **9,460 parameters**.

Centralized: 15 epochs, batch 128, Adam 0.001, seed 42. Flower **1.40.0**: five simulated clients, **15 rounds**, one local epoch, batch 128, Adam 0.001, all clients every round, aggregation weighted by `n_i/22450`. Client shuffle seed: `42 + 100*round + client_id`. CPU, one PyTorch thread per process, deterministic algorithms. Local Adam resets each round; centralized Adam persists across epochs. Total training sample presentations are 336,750 for each model; optimization trajectories differ.

**75 successful client updates and all 15 weighted aggregations were verified.** Final evaluation used validation.csv only, with no checkpoint selection. The existing centralized checkpoint was reevaluated; its saved metrics and all 6,486 historical predictions were reproduced exactly. No new centralized training was performed during that comparison.

All table entries are rates/F1 on the **0–1 scale**, copied exactly from JSON:

| Metric | Centralized | Flower FedAvg |
|---|---:|---:|
| Exact subtype accuracy | 0.6954979956830095 | 0.6378353376503237 |
| Subtype Macro F1: 28 observed labels | 0.3702992133538757 | 0.09671945280651104 |
| Attack-only exact subtype accuracy | 0.2609516616314199 | 0.11367069486404834 |
| Attack-only subtype Macro F1: 27 labels | 0.3501461814106698 | 0.06647544301448552 |
| Derived family accuracy | 0.8509096515572001 | 0.769195189639223 |
| Derived family Macro F1: 7 observed labels | 0.6248067195867406 | 0.33536314691286667 |
| Attack detection recall | 0.7651057401812689 | 0.726963746223565 |
| Benign false-positive rate | 0.004689942678478374 | 0.0005211047420531526 |
| Subtype Macro F1: all 84, zero support included | 0.1234330711179586 | 0.03223981760217034 |

Observed-label Macro F1 uses ground-truth coverage and `zero_division=0`. The all-84 average is a different statistic; zero-support classes were not evaluated successfully merely because they appear in that average. The family CSV report includes all eight families, so its macro average also differs from the primary observed-seven value.

| Disjoint hierarchical category | Centralized | Flower FedAvg |
|---|---:|---:|
| Exact correct, including benign | 4511 | 4137 |
| Correct attack family, wrong subtype | 1008 | 852 |
| Attack predicted benign | 622 | 723 |
| Benign predicted attack | 18 | 2 |
| Wrong attack family | 327 | 772 |
| **Total** | **6486** | **6486** |

In this run, Flower reduced benign false alarms from 18 to 2, but increased missed attacks from 622 to 723. Its exact subtype, attack subtype and derived-family performance was lower than centralized performance. Flower family recall was zero on the observed bruteforce (120 rows), dos (228) and malware (433) families. The experiment does not identify a causal explanation or establish a general ranking of learning approaches.

Evidence: [full Turkish summary](results/subtype_flower_val_v1_summary.md), [comparison JSON](results/subtype_flower_val_v1/comparison.json), [Flower metrics](results/subtype_flower_val_v1/fedavg_metrics.json), [centralized recomputation](results/subtype_flower_val_v1/centralized_recomputed_metrics.json), [original centralized metrics](results/subtype_centralized_val_v1_metrics.json), [verification](results/subtype_flower_val_v1/verification.json). Strategy/training wall time was **12.15364475899969 seconds**, excluding packaging, SuperLink startup and final evaluation; this is a simulation measurement.

## Other completed experiments evidenced by saved artifacts

These are recorded historical runs, not newly rerun results. Do not pool different label tasks, splits or Macro F1 conventions into a single benchmark.

### Direct 8-class family models on validation_v1

Checkpoints: `models/centralized_mlp_val_v1.pt`, `models/flower_fedavg_val_v1.pt`. Both have architecture 71→64→32→8 (6,952 parameters); 15 centralized epochs vs 15 Flower rounds, five clients, one local epoch; seed 42, batch 128, Adam 0.001. Same 22,450/6,486 split as above, but direct family classification rather than a subtype-derived family prediction.

| Metric (0–1) | Centralized 8-class | Flower 8-class |
|---|---:|---:|
| Family accuracy | 0.8590810977489979 | 0.8018809744064138 |
| Macro F1: 7 observed families | 0.6590124881282478 | 0.4320930627833201 |
| Macro F1: all 8 families | 0.5766359271122168 | 0.3780814299354051 |
| Attack detection recall | 0.7722809667673716 | 0.69297583081571 |
| Attack-only family accuracy | 0.6620090634441088 | 0.5147280966767371 |
| Benign false-positive rate | 0.0049504950495049506 | 0.0 |

Saved missed-attack counts: centralized **603**, Flower **813**. Sources: [centralized metrics](results/centralized_mlp_val_v1_metrics.json), [Flower metrics](results/flower_fedavg_val_v1_metrics.json), [comparison summary](results/validation_v1_comparison_summary.json); code: `scripts/23_train_centralized_val_v1.py`, `scripts/24_compare_validation_models.py`, `flower_app/seniorfl/`.

### Earlier splits_v2 experiments

Source code and saved reports identify the older protocol: **31,216 training rows**, five `data/fl_clients_v1/` partitions, **10,896 episode-test rows**. These historical labels name a heuristic split; they do not prove independent sessions. The protected test CSVs were not opened during this documentation update.

| Historical run | Label task | Saved accuracy | Saved Macro F1 | Metric evidence |
|---|---|---:|---:|---|
| Centralized MLP | 8 families | 0.8502202643171806 | 0.6255251069304716 | [centralized_mlp_v1_metrics.json](results/centralized_mlp_v1_metrics.json) |
| Custom PyTorch FedAvg | 8 families | 0.7608296622613803 | 0.4440180630631887 | [fedavg_v1_metrics.json](results/fedavg_v1_metrics.json) |
| Flower FedAvg | 8 families | 0.760737885462555 | 0.4438591468585883 | [flower_fedavg_v1_metrics.json](results/flower_fedavg_v1_metrics.json) |
| Centralized MLP | 84 subtypes | 0.6257342143906021 | 0.26129280200965826 | [subtype_centralized_metrics.json](results/subtype_centralized_metrics.json) |
| Custom PyTorch FedAvg | 84 subtypes | 0.5357011747430249 | 0.052061997836372616 | [subtype_fedavg_metrics.json](results/subtype_fedavg_metrics.json) |

The older subtype evaluation reports **56 observed classes**, unlike validation_v1’s 28. Its derived family metrics were:

| Earlier subtype model | Family accuracy | Family Macro F1 |
|---|---:|---:|
| Centralized | 0.8266336270190896 | 0.5778403861822586 |
| Custom PyTorch FedAvg | 0.7053046989720999 | 0.39264088529906127 |

Code: `scripts/15_train_fedavg.py`, `16_train_centralized_mlp.py`, `18_train_centralized_subtypes.py`, `19_train_fedavg_subtypes.py`. Scripts 15 and 19 implement averaging in PyTorch; they are not Flower deployments. The older Flower run also has a separate archived source/model/metric bundle at [results/flower_experiment_01/](results/flower_experiment_01/). Its saved metrics duplicate the older Flower metrics above; it is not an additional independent trial.

Archived web diagnostics, read from saved JSON only: 8-class centralized recall **0.8899082568807339**, custom FedAvg recall **0.1559633027522936**; older subtype FedAvg web-family recall **0.0**, web-subtype accuracy **0.0**. These are older diagnostic-set measurements, not validation_v1 web results or current tuning targets.

### Existing local and locally unseen evidence

Five `models/local_mlp_clientN.pt` checkpoints were inspected and have **8 outputs**, not 84. Their source `scripts/14_train_local_mlp.py` uses the old fl_clients_v1/splits_v2 protocol. The five [local logs](results/local_client_1.txt) report:

| Client | Old training rows | Seen test rows | Unseen test rows | Seen accuracy as printed | Unseen accuracy as printed |
|---|---:|---:|---:|---:|---:|
| 1 | 5914 | 8448 | 2448 | 0.8647 | 0.0000 |
| 2 | 7955 | 6922 | 3974 | 0.9593 | 0.0000 |
| 3 | 4275 | 5604 | 5292 | 0.9880 | 0.0000 |
| 4 | 7951 | 8846 | 2050 | 0.9385 | 0.0000 |
| 5 | 5121 | 8210 | 2686 | 0.9440 | 0.0000 |

These log accuracies are preserved at their printed four-decimal precision; unrounded local aggregate accuracies are not inferred. Legacy global unseen-family tables also exist at [fedavg_v1_unseen.csv](results/fedavg_v1_unseen.csv) and [centralized_mlp_v1_unseen.csv](results/centralized_mlp_v1_unseen.csv).

The earlier **custom subtype FedAvg** already has per-client missing-subtype and missing-family measurements in [subtype_fedavg_unseen.csv](results/subtype_fedavg_unseen.csv):

| Client | Unseen subtype rows | Exact subtype accuracy | Unseen family rows | Family accuracy |
|---|---:|---:|---:|---:|
| 1 | 3864 | 0.07945134575569358 | 2448 | 0.7079248366013072 |
| 2 | 4514 | 0.07642888790429773 | 3974 | 0.24609964771011575 |
| 3 | 5292 | 0.06972789115646258 | 5292 | 0.4189342403628118 |
| 4 | 3876 | 0.0043859649122807015 | 2050 | 0.008292682926829269 |
| 5 | 3136 | 0.07174744897959184 | 2686 | 0.6414743112434848 |

These are archived scores of a global model on subsets defined relative to each client’s old training support. They do not supply missing 84-class local-only checkpoints or an apples-to-apples local/Flower/centralized comparison on validation_v1.

### Random forests, ONNX and historical Pi-labelled log

Present artifacts: `models/binary_rf_5sec.joblib`, `family_rf_5sec.joblib`, `family_rf_network_only_5sec.joblib`, `family_rf_5sec.onnx`, plus two Pi sample CSVs. Sources `scripts/05_train_baseline.py`, `06_train_family.py`, `07_export_onnx.py`, `09_train_network_only.py` describe their training/export workflows. File presence establishes saved models/export, not a recoverable full-dataset RF score or independently verified ONNX parity; no such score is invented here.

[results/pi_results_5sec.txt](results/pi_results_5sec.txt) is a historical text log labelled Raspberry Pi performance: **151/160** correct (**94.38% as printed**), **71 features**, average **0.033 ms**, median **0.031 ms**, P95 **0.049 ms**, process RAM **114.09 MB** (before model **46.14 MB**, after model **112.94 MB**). The inspected log does not establish the device configuration, measurement protocol or current reproducibility. Treat it as an archived inference report; do not attach these numbers to the 84-class MLP, live network traffic or physical Flower training. Physical Raspberry Pi federated clients and the Kali testbed remain future work.

## Methodological limitations

1. Episode IDs are heuristic candidate groups. Zero ID overlap does not establish independent physical sessions, devices or collection campaigns. No full independent-session evaluation is claimed.
2. Benign validation uses a temporal holdout and gap, not independent benign episode groups. Nearby/correlated records remain a methodological concern requiring explicit evidence.
3. Validation covers only 28/84 subtypes; **56 classes and the web family are absent**. Singleton candidate-episode subtypes were kept in training. Unknown-class detection and full 84-class generalization are not measured.
4. Benign is 3,838/6,486 validation rows. Overall accuracy hides poor minority attack recognition; report attack-only, per-class, detection and family results together.
5. Current matched 84-class results use one seed and one fixed Non-IID partition, all-client participation and fixed hyperparameters. There are no established repeated-seed uncertainty estimates, imbalance ablations or participation sweeps for this comparison.
6. Federated rounds reset Adam locally; centralized training retains Adam. Equal data exposure does not imply equivalent optimization updates or explain performance differences causally.
7. Locally unseen classes mean absent at a particular client and present in global training. They are not globally unseen/open-set classes. The current 84-class Flower run has no matched local-only comparison proving transfer.
8. Five disjoint error categories and derived-family metrics are implemented. A prespecified formal hierarchical metric framework, tree-distance/cost analysis and uncertainty treatment are still future work.
9. Flower/Ray runs are simulation. Simulation wall time is not physical network, Raspberry Pi, energy or communication-cost performance. Existing Pi-labelled inference evidence has limited provenance.
10. Saved legacy scores and modern validation_v1 results use different splits and, sometimes, label denominators. Do not claim a fair cross-protocol improvement from their numerical differences.

## Current project structure

| Path | Role |
|---|---|
| `references/proposal.docx` | Academic specification |
| `AGENTS.md`, `PROJECT_STATUS.md` | Permanent working rules and evidence-backed status |
| `data/raw/` | Original source data; preserve |
| `data/splits_v1/`, `data/splits_v2/`, `data/fl_clients_v1/` | Historical split/client protocols; preserve |
| `data/validation_v1/` | Current matched training, five client training partitions, validation; client-specific validation files also exist |
| `flower_app/seniorfl/` | Original 8-class ClientApp/ServerApp/task; `subtype_task.py` defines the centralized subtype model/schema |
| `flower_subtype_app/seniorfl_subtype/` | Separate 84-class ClientApp/ServerApp/task, packaged schema, strict aggregation audit |
| `scripts/01*`–`13*` | Exploration, quality/leakage analysis, RF/export and split/client preparation source |
| `scripts/14*`–`19*` | Historical local, centralized and custom FedAvg MLP experiments/audits |
| `scripts/20*`–`22*` | Validation feasibility and split generation source |
| `scripts/23*`–`24*` | Direct 8-class validation_v1 centralized training/comparison |
| `scripts/25_train_centralized_subtype_val_v1.py` | Existing 84-class centralized training |
| `scripts/26_run_flower_subtype_val_v1.py` | Audit/train/finalize/verify stages for current 84-class Flower experiment |
| `models/` | Historical checkpoint/export files and current subtype Flower checkpoint |
| `results/` | Historical metrics/logs, audits, experiment snapshots and summaries |
| `results/subtype_flower_val_v1/` | Full 84-class simulation artifact bundle and manifests |

Current artifact bundle includes configuration, exact dependency freeze, environment, data audit/hashes, source backup and final source archive, packaged-code verification, final model hash, two sets of JSON/CSV reports/predictions/confusion matrices, 15 round rows, 75 client-update rows, and PNG/SVG figures. Important figures: `comparison`, `family_confusion`, `subtype_confusion_observed`, `training_loss`, `client_distribution`. No new screenshot capture is claimed in this update; future important UI/device/run screenshots should be preserved with captions and provenance.

## Reproducibility and safe commands

Run from the SeniorProject root. Existing WSL interpreter: `/home/seniorfl/seniorproject-fl-venv/bin/python`. Recorded environment: Python **3.12.3**, Flower **1.40.0**, Ray **2.55.1**, torch **2.14.1+cpu**, NumPy **2.5.4**, pandas **3.0.6**, scikit-learn **1.9.1**, matplotlib **3.11.2**. See [environment](results/subtype_flower_val_v1/environment.json), [freeze](results/subtype_flower_val_v1/requirements.freeze.txt), [config](results/subtype_flower_val_v1/config.json). The freeze includes an editable project path and a CPU torch build; it is a machine-specific record, not a portable lockfile.

Read-only inspection of the saved comparison:

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python -m json.tool results/subtype_flower_val_v1/comparison.json
```

Read-only integrity verification, which does not rewrite any historical result:

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python - <<'PY'
from pathlib import Path
import hashlib, json
root = Path.cwd()
bundle = root / "results/subtype_flower_val_v1"
manifest = json.loads((bundle / "artifact_manifest.json").read_text())
for name, record in manifest.items():
    path = root / name
    assert path.stat().st_size == record["bytes"], name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"], name
protected = json.loads((bundle / "preservation_before.json").read_text())
for name, digest in protected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
print(f"Verified {len(manifest)} experiment artifacts and {len(protected)} protected files")
PY
```

This read-only check passed during the documentation review: **56 experiment artifact hashes and 115 protected file hashes match**. The saved training verification also records 15 rounds, 75 updates and both 6,486-row hierarchical/confusion totals. No existing verification manifest was rewritten for this update.

Original training/evaluation entry points, for a **new isolated reproduction with distinct outputs only**:

```bash
# Historical centralized command; fixed destinations would overwrite the baseline.
PYTHONPATH="$PWD/flower_app" /home/seniorfl/seniorproject-fl-venv/bin/python scripts/25_train_centralized_subtype_val_v1.py
# Flower staged workflow; existing audit/model/evaluation guards refuse this completed run.
/home/seniorfl/seniorproject-fl-venv/bin/python scripts/26_run_flower_subtype_val_v1.py --stage all
```

Do not execute these training commands against the completed workspace. For a future authorized reproduction, snapshot source first; configure new result/model paths consistently in the runner and ServerApp, and bootstrap the new directory with a source backup/preservation manifest. The current runner does not provide an arbitrary run-ID/output-directory option, and `--stage all` is not a fresh-workspace bootstrap. Its `--stage verify` also rewrites verification/manifests; prefer the read-only command above when preserving this run. Other legacy preparation/training/comparison scripts also contain fixed outputs and may access protected tests.

The successful Flower CLI command was `flwr run <absolute-project-root>/flower_subtype_app subtype-simulation --stream`; see [launch_attempt_01.json](results/subtype_flower_val_v1/launch_attempt_01.json). The runner starts a dedicated SuperLink with `--disable-runtime-dependency-installation`, five simulated SuperNodes and one CPU per client, reusing the existing venv. Its separate Flower home is `/home/seniorfl/.flwr/subtype84_val_v1/`; packaged data resolution uses explicit `project-root`, not the app installation directory. Moving the project requires updating that setting and auditing new paths.

The earlier default CLI attempt failed on the read-only `~/.cache/uv` directory (runtime exit 608); its failed log is preserved. A mounted-filesystem metadata/utime backup operation was also denied; content backups were kept. No security settings or directory permissions were changed. Success is identified by `successful_launch.json` and `simulation_attempt_01.log`; `simulation.log` is the earlier failure. A CLI exit code of zero alone was insufficient to establish training success.

## Next research priorities — planned, not implemented in this update

1. **Matched 84-class local-only baselines.** Train five independent 71→64→32→84 models on the exact existing validation_v1 client partitions, preserving global class IDs, feature/preprocessing schema, seed policy, evaluation rows and documented training budget. Save separate weights and the same detection/family/subtype/error reports. These are new experiments; existing 8-class local models cannot substitute.
2. **Locally unseen subtype and family evaluation.** Define masks solely from each client’s training support and the fixed validation labels. Separately evaluate missing subtypes within locally observed families and entirely missing attack families. Require global-training support, record evaluated supports/empty subsets, and compare each local model against the same global Flower and centralized predictions. Do not treat client-relative overlapping subsets as independent samples or generalize to absent validation classes.
3. **Repeated seeds and class-imbalance experiments.** Prespecify seeds, repeats and imbalance interventions; keep an unchanged reference arm. Separate model/shuffle randomness from changes to client allocation. Derive weights/resampling from training only, maintain immutable validation, and report per-class results plus appropriate uncertainty without treating correlated rows as independent sessions. Do not assume a remedy will improve the observed weak minority-family recall.
4. **Formal hierarchical evaluation.** Specify the benign/attack→family→subtype taxonomy, treatment of benign, metric denominators and error costs before running comparisons. Extend the existing five-category counts with formally defined hierarchical precision/recall/F1 or path-distance/cost metrics, grouped confusion views and justified uncertainty. Keep exact flat metrics so formal scores do not conceal attack→benign errors.

After these priorities, consider further Non-IID distributions, partial participation and the proposed Streamlit dashboard under separate experiment IDs. No such experiment, deployment or dashboard was implemented by this documentation task.

## Future Raspberry Pi clients and isolated Kali Linux IIoT testbed

Planned hardware work is separate from simulation and from the archived Pi inference log. Build real Raspberry Pi Flower clients with verified feature extraction and model schema parity; then measure inference/training latency, memory, communication and energy where instrumentation supports those claims. Save device/OS/runtime versions, topology, commands, timestamped logs and important setup screenshots.

Plan an isolated, authorized Kali Linux IIoT attack testbed to generate controlled traffic, establish scenario/session ground truth, and assess trained models against captured traffic using matching preprocessing. Document isolation, attack schedule, capture provenance, feature parity and limitations before claiming real-world or independent-session performance. Physical clients, live collaborative training and this testbed are **future work**, not completed deliverables evidenced here.
