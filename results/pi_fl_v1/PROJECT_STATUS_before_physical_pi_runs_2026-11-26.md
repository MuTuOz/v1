# Project status

Evidence reviewed: **2026-11-26**. Latest additions (post-hoc, no new IDS training): **subtype_sensitivity_v1** (subtype × Non-IIDness × detection/mitigation analysis of all 44 saved validation_v1 prediction sets), **performance_v1** (inference latency/size and communication cost), and a **PC-server / Pi-client** helper with two passed single-machine TLS federation checks. **Physical Raspberry Pi execution is still unverified.** Pre-update status: `results/subtype_sensitivity_v1/PROJECT_STATUS_before.md`. Details in the next section.

## Advisor feedback follow-up — 2026-11-26 (subtype sensitivity, performance, PC↔Pi)

Advisor notes asked for: performance beyond accuracy (communication per round, inference), a sensitivity analysis of cyber-event detection by attack subtype and Non-IIDness (example tree ddos → http flood / icmp flood / icmp frag flood), why subtypes differ given non-normal distributions, from both detection and mitigation perspectives, and whether a PC-server / Pi-client federation works.

* **[subtype_sensitivity_v1 report](results/subtype_sensitivity_v1/REPORT.md)** — [script 34](scripts/34_subtype_sensitivity_analysis.py), 285,384 saved prediction rows, training-only feature statistics, no training/inference, no validation features or protected test files. Adds technique (port-agnostic), mechanism (dos/ddos-agnostic) and analyst-defined mitigation-action levels ([heuristic mapping](docs/mitigation_mapping_v1.csv), not a validated playbook). Attack rows, 3 seeds: centralized detection 0.7754 / mitigation action 0.7163 / exact 0.2777; Flower 0.7189 / 0.4752 / 0.1362. Flower with balanced → original → exclusive allocation (JS 0.0001 → 0.2354 → 0.2569 bits, seed 42): detection 0.7708 → 0.7270 → 0.6322. 99.2% of 3,069 per-subtype Shapiro–Wilk tests reject normality (BH q<0.05), so only distribution-free statistics are used. Sibling subtypes look separable on training rows (median C2ST 0.99) but only 8/157 pairs allow episode-grouped CV (median 0.86) and dos/ddos twins are heavily confused on validation, consistent with session-specific rather than technique-specific signatures (interpretation, not a proven cause). Subtype-level Non-IID correlations (n=27, Spearman, uncorrected) are exploratory.
* **[performance_v1](results/performance_v1/README.md)** — [script 35](scripts/35_performance_benchmark.py), portable to the Pi. Cloud x86 container only so far: 84-class MLP 9,460 parameters, one record incl. preprocessing median 0.035 ms; one Flower update 38,674 B; 15 rounds × 5 clients = 5.80 MB application payload vs 6.38 MB to ship the training features once. Not wire-level, not energy, not Pi.
* **PC↔Pi federation** — [script 36](scripts/36_pc_pi_federation.py) and [Turkish quickstart](docs/pc_server_pi_client_quickstart_tr.md). Flower 1.40 serves all APIs on one `--host/--port`; the deprecated fleet/control address flags left SuperLink on 127.0.0.1:8000 (first attempt failed, kept). Passed: `results/pi_fl_v1/loopback_check_2clients_r3_s42` and `lanip_check_2clients_r3_s42` (SuperLink on 0.0.0.0:9092, SuperNodes via a non-loopback IP with cert SAN, 3 rounds, 6 verified updates, training-only balanced-allocation rows). Both ran on one x86 machine. WSL2 NAT/firewall forwarding and the actual Pi run remain for the lab.

## Research specification and completion boundary

[Proposal](references/proposal.docx): **Hierarchical Evaluation of Cyber Event Classification in Industrial IoT Networks**. The main question is whether collaborative learning improves recognition of attacks absent from an individual client’s training data but present at other clients. The planned comparison is local-only vs federated vs centralized learning under Non-IID distributions, with leakage-aware splits, per-class reports, false alarms and hierarchical error analysis.

Implemented evidence includes the historical audits/baselines, the original centralized/Flower 84-class comparison, and the separate matched local-only/repeated-seed study documented below. Formal Riehl HCM reuses the same verified tree/single-path/leaf-only evaluator. The dashboard and two independent Linux SuperNodes over loopback TLS have been exercised. **Physical Raspberry Pi execution, independent physical capture sessions and exact live feature parity remain unverified.** Simulation and x86 process tests cannot establish those capabilities.

## Completed pre-Pi research study — current milestone

Evidence: [experiment index](results/pre_pi_research_v1/EXPERIMENT_INDEX.csv), [Methods](results/pre_pi_research_v1/phase11/Methods.md), [Results](results/pre_pi_research_v1/phase11/Results.md), [formal definitions](results/pre_pi_research_v1/phase11/Evaluation_Protocol.md), [threats](results/pre_pi_research_v1/phase11/Threats_to_Validity.md). New source is in `pre_pi_app/researchfl/`, scripts 28–33, `dashboard/`, `live_pipeline/` and `hardware_deployment/`; original apps are preserved.

Reference seeds are 42, 52, 62; 71→64→32→84; batch 128; Adam 0.001. Local-only models train only on their own original client CSV for 15 epochs. Centralized uses 15 global epochs; Flower uses 15 rounds × one local epoch with selected-client sample-count weighting. Local/central Adam persists; federated Adam resets per round. The new cohort fixes PyTorch threads to one. A separate four-thread seed-42 diagnostic exactly reproduces the old centralized checkpoint (maximum state difference 0.0; zero prediction mismatches), and is excluded from seed summaries. [Budget table](results/pre_pi_research_v1/phase05/training_and_payload_budgets.csv) records optimizer steps and sample presentations separately from rounds.

Global results, full precision read from the three-seed CSV (rates/F1; SD uses ddof=1):

| mode | client_id | metric | mean | std_ddof1 | seeds |
|---|---|---|---|---|---|
| centralized | global | exact_subtype_accuracy | 0.6981704183369309 | 0.0103084414737378 | 3 |
| centralized | global | subtype_macro_f1_observed | 0.3810879515457938 | 0.008751593524962 | 3 |
| centralized | global | attack_only_subtype_accuracy | 0.2776938569989929 | 0.0163930923171855 | 3 |
| centralized | global | family_accuracy | 0.8500359749203413 | 0.0076428456963804 | 3 |
| centralized | global | family_macro_f1_observed | 0.6226077750288769 | 0.0152846954824749 | 3 |
| centralized | global | attack_detection_recall | 0.7754279959718028 | 0.0264494278238979 | 3 |
| centralized | global | benign_false_positive_rate | 0.0117248566961958 | 0.0151859792818111 | 3 |
| centralized | global | hcm_f1 | 0.7391599743665096 | 0.0077300897610444 | 3 |
| flower_fedavg | global | exact_subtype_accuracy | 0.6471888169390482 | 0.0136178163512613 | 3 |
| flower_fedavg | global | subtype_macro_f1_observed | 0.1262511847401241 | 0.0428639605066502 | 3 |
| flower_fedavg | global | attack_only_subtype_accuracy | 0.1362034239677743 | 0.0333147787614631 | 3 |
| flower_fedavg | global | family_accuracy | 0.7809127351218007 | 0.013028744642814 | 3 |
| flower_fedavg | global | family_macro_f1_observed | 0.3878956920890532 | 0.0639615011005312 | 3 |
| flower_fedavg | global | attack_detection_recall | 0.7189073514602216 | 0.0094812840169438 | 3 |
| flower_fedavg | global | benign_false_positive_rate | 0.0002605523710265 | 0.0002605523710265 | 3 |
| flower_fedavg | global | hcm_f1 | 0.6639684522641004 | 0.015516371296988 | 3 |

All five local arms and per-class metrics are available in [repeated summaries](results/pre_pi_research_v1/phase03/repeated_seed_summary_tidy.csv) and [per-class CSV](results/pre_pi_research_v1/phase03/all_per_class_metrics.csv). Seed variability is not independent-session uncertainty.

The primary client-relative unseen-subtype (A) result, mean exact accuracy over three seeds, uses identical per-client validation masks:

| client_id | samples | local_only | flower | centralized | flower_minus_local |
|---|---|---|---|---|---|
| 1 | 2192.0 | 0.0 | 0.1310827250608272 | 0.2125912408759124 | 0.1310827250608272 |
| 2 | 1955.0 | 0.0 | 0.0375106564364876 | 0.235464620630861 | 0.0375106564364876 |
| 3 | 2528.0 | 0.0 | 0.142668776371308 | 0.2908755274261603 | 0.142668776371308 |
| 4 | 1210.0 | 0.0 | 0.1790633608815427 | 0.4173553719008264 | 0.1790633608815427 |
| 5 | 1987.0 | 0.0 | 0.1667505452105351 | 0.2039926186881395 | 0.1667505452105351 |

Every local A exact accuracy is zero in these runs; Flower is positive for every client and seed, while centralized A means are higher for all five clients. Detection gains are mixed. A partitions into entirely missing attack families (B) and missing subtypes within known families (C). C supports are 72/874/0/168/0 rows for clients 1–5. Flower remains zero for C1/C2, but C4 improves at seeds 52/62: exact accuracies 0/0.3869047619047619/0.40476190476190477, mean 0.2638888888888889 versus centralized mean 0.19047619047619047. At seed 52 the 65 correct rows are recon_host-disc-udp-ping; at seed 62 the 68 correct rows split into 60/144 reconnaissance and 8/12 ddos_ack-frag-flood-port-1883. The other missing DDoS subtype stays at zero. Empty subsets have null metrics. This is client-relative transfer on a fixed split, not open-set recognition; overlapping client subsets are not independent observations. [Detailed HCM](results/pre_pi_research_v1/phase02/detailed_unseen_hcm.csv), [per-class gains](results/pre_pi_research_v1/phase02/per_class_flower_local_gains.csv) and [per-seed comparisons](results/pre_pi_research_v1/phase02/paired_seed_comparisons.csv) preserve supports and negative outcomes.

Seed-42 controls include inverse-frequency and effective-number weighting for centralized/Flower/all five locals; two new training-only allocations; 3-of-5 participation; two local epochs; and network64 dataset ablations. Inverse-frequency centralized accuracy drops to 0.16358310206598828 versus the matched unweighted 0.6950354609929078. No weighting method is assumed superior and no validation winner is promoted. Every original training row is used once in each new allocation; changed allocation changes unseen masks. Balanced allocation has no client-relative missing labels. [Index](results/pre_pi_research_v1/EXPERIMENT_INDEX.csv) and [family comparisons](results/pre_pi_research_v1/phase04/per_family_comparison.csv) record exact outcomes.

Scientific re-verification reproduces all 44 model records' 285,384 validation predictions and audits 150 new FedAvg rounds / 720 updates, all three allocations, matrix/category totals and formal HCM. [33 tests passed](results/pre_pi_research_v1/unit_test_results_revision_03.json), including all 7,056 HCM leaf pairs, unseen masks, extraction guards, hardware metadata and all 11 dashboard views. Eleven measured-data figures have PNG and SVG exports. No real-browser screenshot is claimed. Final [verification](results/pre_pi_research_v1/verification_revision_03.json) and [SHA-256 manifest](results/pre_pi_research_v1/ARTIFACT_MANIFEST_revision_03.json) bind sources/artifacts. Historical manifests retain the earlier mutable PROJECT_STATUS hash; their files are not rewritten. The current status has a separate final hash, with its pre-update bytes archived.

Run the dashboard or read-only verifier from the root:

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
/home/seniorfl/seniorproject-fl-venv/bin/python scripts/33_verify_pre_pi.py
```

[Pi readiness](docs/pi_deployment_readiness.md), [feature compatibility](docs/live_feature_compatibility_report.md), and [Kali plan](docs/kali_lab_deployment_plan.md) distinguish software preparation from hardware evidence. The independent two-node x86 Linux smoke exercised TLS trust rejection and four updates over two rounds on synthetic rows; logs measure warmed batch timings, RSS and serialized array sizes, not Pi/wire/energy performance. ARM64/registered-node authentication remain unverified. The offline extractor has 53 candidate formulas but zero verified original semantic-parity claims; 18 slots lack definitions and packets alone cannot supply seven log inputs. It refuses missing/unverified model input. Network64 dataset models do not establish live parity. Pi preparation and live parity are PARTIAL; the Kali deliverable is DESIGN ONLY. The final [checkpoint-continuation smoke](results/pre_pi_research_v1/phase08/loopback_tls_checkpoint_v4/verification.json) passes with the current packaged source and preserved Flower checkpoint. Earlier bookkeeping failures remain documented in [failure records](results/pre_pi_research_v1/FAILURES_AND_RESOLUTIONS.md).

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

Centralized: 15 epochs, batch 128, Adam 0.001, seed 42. Flower **1.40.0**: five simulated clients, **15 rounds**, one local epoch, batch 128, Adam 0.001, all clients every round, aggregation weighted by `n_i/22450`. Client shuffle seed: `42 + 100*round + client_id`. Flower uses CPU, one PyTorch thread per process and deterministic algorithms. The later reproduction diagnostic establishes that the old centralized run used four threads. Local Adam resets each round; centralized Adam persists across epochs. Total training sample presentations are 336,750 for each model; optimization trajectories differ.

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

## Completed formal Riehl HCM evaluation (formal_hcm_v1)

Post-hoc evaluation used the **existing 84-class Centralized and Flower FedAvg validation_v1 predictions**, aligned to all 6,486 validation metadata rows. No new training or model inference occurred. The hierarchy is **Root → Benign** and **Root → Attack → seven attack families → 83 attack subtypes**: 93 nodes and 84 leaves. Benign remains a depth-1 leaf; attack subtypes have depth 3; root is excluded from TP. All 84 leaves remain in the taxonomy despite limited observed validation coverage.

The implementation follows Riehl et al. (2023), [DOI 10.1093/jrsssc/qlad057](https://doi.org/10.1093/jrsssc/qlad057), and author reference commit `2256f4c24b813ffb752a53e20a8092ec7b1e3ac3`. **Formal HCM counts are node/decision contributions, not the earlier five sample error categories.** Micro metrics are calculated after summing TP/TN/FP/FN over samples. Undefined denominators are null. The scope is T/SPL/MLNP; generalized DAG/multilabel/internal-node predictions are not implemented.

**TN assumption is explicit:** the author reference uses siblings and immediate children at the common path terminal, although the paper describes descendants. Primary results reproduce that reference and the published examples. A separate transitive-descendant TN sensitivity result is saved and is not labelled the primary reference HCM. Precision/recall/F1 are unchanged by this TN-only variant. The standard FN/(TP+FN) FNR formula is used rather than the Table 2 numerator typo.

| Metric (rates 0–1) | Centralized | Flower FedAvg |
|---|---:|---:|
| TP_H | 8236 | 7215 |
| TN_H | 34025 | 24965 |
| FP_H | 2338 | 3125 |
| FN_H | 3546 | 4567 |
| HCM precision | 0.7788916209570645 | 0.6977756286266924 |
| HCM recall | 0.6990324223391614 | 0.6123748090307248 |
| HCM f1 | 0.7368044372875291 | 0.6522918361811771 |
| HCM accuracy | 0.8777858552289958 | 0.8070826645264848 |
| HCM specificity | 0.9357038748178094 | 0.88875044499822 |
| HCM false_positive_rate | 0.06429612518219069 | 0.11124955500177999 |
| HCM false_negative_rate | 0.3009675776608386 | 0.38762519096927517 |
| HCM mcc | 0.6591536569631522 | 0.5217049639055975 |

HCM decision totals are **48,145** (Centralized) and **39,872** (Flower); neither should equal 6,486. Both satisfy **TP+FN = 11,782 = 3,838 + 3×2,648**, the total true-path length. On the attack-truth subset (2,648 rows), HCM F1 is **0.603113903305108** (Centralized) and **0.46794072843096524** (Flower). This subset excludes benign false alarms and is supplementary. HCM recall/FPR are not operational attack recall/benign FPR.

**Validation:** 12 unit tests passed, including exact attack/benign, wrong subtype in correct family, wrong attack family, attack→benign, benign→attack, published Figure 4a examples, invalid inputs and undefined metrics. Every **84×84 = 7,056** leaf pair matches the pinned author reference. Prediction/label/episode alignment, original flat accuracy and five-category totals were reproduced; count matrices each sum to 6,486 and upper-level matrices recover from leaf aggregation. PNG/SVG figures and an offline Neo-inspired explorer complement the formal 2×2 HCM.

Coverage and independence limits remain unchanged: 28/84 observed subtypes, 7/8 observed families, 56 absent classes, no web validation, heuristic episode IDs and temporal benign holdout. HCM does not establish independent sessions, full-class coverage, statistically significant gains or real-device deployment. Neo (CHI 2022, [DOI 10.1145/3491102.3501823](https://doi.org/10.1145/3491102.3501823)) informs multiresolution visualization, not the Riehl counting definitions; a full Neo-system reproduction is not claimed.

Artifacts: [formal HCM Turkish report](results/formal_hcm_v1_summary.md), [comparison JSON](results/formal_hcm_v1/comparison.json), [CSV](results/formal_hcm_v1/comparison.csv), [source registry](results/formal_hcm_v1/sources/REFERENCES.md), [unit-test log](results/formal_hcm_v1/unit_tests.log), [verification](results/formal_hcm_v1/verification.json), [offline confusion explorer](results/formal_hcm_v1/confusion_explorer.html). Source: `scripts/hcm_eval.py`, `scripts/27_evaluate_formal_hcm_v1.py`, `tests/test_formal_hcm.py`. Pre-edit source/status backup and input/output SHA-256 manifests are retained in the new artifact directory.

Read-only checks and separate-output reproduction:

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python -m unittest discover -s tests -p 'test_formal_hcm.py' -v
/home/seniorfl/seniorproject-fl-venv/bin/python scripts/27_evaluate_formal_hcm_v1.py --mode verify
# Optional independent repetition from the same immutable saved predictions:
/home/seniorfl/seniorproject-fl-venv/bin/python scripts/27_evaluate_formal_hcm_v1.py --output-dir results/formal_hcm_v1_repeat
```

Evaluation requires the archived author reference in `results/formal_hcm_v1/sources/`; no network download is needed to repeat it. Existing evaluation destinations are refused. `--mode seal` creates a new output/source manifest once; `--mode verify` is read-only. The original Flower experiment verification and all earlier experiment artifacts remain unchanged.

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
8. The five sample error categories and formal Riehl HCM are now separately implemented. HCM follows a documented author-reference TN interpretation for a tree, single path and mandatory leaves; a transitive-TN sensitivity is separate. Generalized DAG/multilabel support, tree-distance/cost analysis and uncertainty treatment remain future work.
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
| `scripts/hcm_eval.py`, `scripts/27_evaluate_formal_hcm_v1.py`, `tests/test_formal_hcm.py` | Formal tree HCM, post-hoc runner, hand-derived/reference parity tests |
| `docs/pi_kali_fl_testbed_design.md` | Future two-Pi-to-five-Pi physical deployment design; no rollout |
| `results/formal_hcm_v1/`, `results/formal_hcm_v1_summary.md` | New formal HCM metrics, matrices, figures, explorer, papers and provenance |
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

## Next research priorities — after pre_pi_research_v1

0. **(2026-11-26)** Run the PC-server / Pi-client federation on the real Pi with `scripts/36_pc_pi_federation.py` and save the Pi's own device logs, `verify` output and screenshots; run `scripts/35_performance_benchmark.py` on both PC and Pi; record per-round wall time and interface byte counters. Review the mitigation mapping with the advisor before using mitigation-level results in the report. Per-round validation curves (accuracy vs communication round) need the local `data/validation_v1/` files, which are not in this repository copy.

1. **Recover authoritative feature definitions and golden windows.** Resolve the 71-feature/log semantic gaps before admitting live inputs; if full parity cannot be established, version and retrain a defensible reproducible feature subset.
2. **Verify actual devices and node identity.** After purchase, test ARM64 dependencies, TLS/registered identities, checkpoint golden tensors and scoped WSL2 connectivity on two Pis, then 3–5. Save device logs and important setup screenshots.
3. **Collect independent labelled sessions.** Apply the isolated Kali/IoT plan with owned targets, capture provenance and separate training/development/final sessions. Old heuristic episodes or replay do not establish independence. Compare local/FL before and after learning.
4. **Confirm exploratory findings.** The local/unseen/three-seed/imbalance/HCM priorities are now executed. Additional intervention seeds, independent-session uncertainty and prespecified hierarchical costs remain future studies. Repeated use of the frozen validation creates selection bias; no best model was promoted.

The earlier formal_hcm_v1 task did not implement the local/repeated-seed studies or dashboard; the separate pre_pi_research_v1 milestone now provides that evidence. Preserve both historical bundles. Further experiments require new IDs and unchanged protected tests.

## Future Raspberry Pi clients and isolated Kali Linux IIoT testbed

Planned hardware work is separate from simulation and from the archived Pi inference log. Build real Raspberry Pi Flower clients with verified feature extraction and model schema parity; then measure inference/training latency, memory, communication and energy where instrumentation supports those claims. Save device/OS/runtime versions, topology, commands, timestamped logs and important setup screenshots.

Plan an isolated, authorized Kali Linux IIoT attack testbed to generate controlled traffic, establish scenario/session ground truth, and assess trained models against captured traffic using matching preprocessing. Document isolation, attack schedule, capture provenance, feature parity and limitations before claiming real-world or independent-session performance. Physical clients, live collaborative training and this testbed are **future work**, not completed deliverables evidenced here.

Physical-design deliverable: [docs/pi_kali_fl_testbed_design.md](docs/pi_kali_fl_testbed_design.md) specifies a WSL2 SuperLink, initially two Raspberry Pi SuperNodes expandable to 3–5, isolated Kali traffic, packet/log capture, all-71-feature parity gates (64 network + 7 log), independent labelled sessions, matched local/FL evaluation, formal HCM, TLS/node identity and artifact capture. New independently labelled training-session versions can support explicit continuation rounds; held-out evaluation sessions must remain excluded. The live extractor, physical federation and laboratory attacks remain future work. No network configuration or live attack was started.

Report correction 02: the C4 seed-62 aggregate score was always correct; its per-subtype prose attribution was corrected using predictions. Previous source/report bytes and the first seal remain archived; [errata](results/pre_pi_research_v1/ERRATA_revision_02.md) documents the lineage.
