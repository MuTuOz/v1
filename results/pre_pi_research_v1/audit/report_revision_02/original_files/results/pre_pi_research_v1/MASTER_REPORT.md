# Pre-Pi research v1 — Master report

## Executive result

Completed a bounded research grid with **44 evaluated model records** (42 newly trained scientific/diagnostic models and 2 frozen historical references), plus a separate two-SuperNode synthetic Linux/TLS smoke. No Raspberry Pi, live attack, production traffic, protected-test access or network reconfiguration was performed. One initial Scapy neighbor-resolution attempt was denied by the sandbox; logs are retained, explicit synthetic MACs and an extraction guard remove that behavior, and offline v2 tests mock/reject network resolution/sending.

The primary research question now has a matched local-only arm. On client-relative missing attack subtypes (A), Flower improves exact subtype accuracy over each local model across the fixed three-seed study. This does **not** imply consistent detection gains, recovery of every missing subtype, superiority over centralized learning, open-set recognition or independent-session generalization.

| client_id | samples | local_only | flower | centralized | flower_minus_local |
|---|---|---|---|---|---|
| 1 | 2192.000000 | 0.000000 | 0.131083 | 0.212591 | 0.131083 |
| 2 | 1955.000000 | 0.000000 | 0.037511 | 0.235465 | 0.037511 |
| 3 | 2528.000000 | 0.000000 | 0.142669 | 0.290876 | 0.142669 |
| 4 | 1210.000000 | 0.000000 | 0.179063 | 0.417355 | 0.179063 |
| 5 | 1987.000000 | 0.000000 | 0.166751 | 0.203993 | 0.166751 |

## Scope, hypotheses and design

H1 (exploratory): collaboration improves client-relative missing-subtype exact accuracy over local-only training. H2: gains differ between entirely missing families (B) and missing subtypes within known families (C). H3: imbalance/heterogeneity/participation interventions have metric-specific trade-offs. These hypotheses and the bounded grid guide descriptive comparisons; no significance or session-independence claim is made.

The academic specification is `references/proposal.docx`. The training pool is fixed at 22,450 rows; validation has 6,486 rows (3,838 benign / 2,648 attacks), 28 observed subtypes and 7 families, with 56 absent subtypes and no web support. Models use 71→64→32→84 with identical class IDs/order and signed-log preprocessing. No validation gradient updates or checkpoint selection occurs.

Reference settings: batch 128, Adam 0.001; 15 local/central epochs vs 15 full FedAvg rounds × one local epoch; seeds 42/52/62. Local and centralized Adam persists; FedAvg resets locally each round. New reference study uses one PyTorch CPU thread. The four-thread diagnostic exactly reproduces the old centralized state and all predictions: {'four_thread_max_state_abs_difference': 0.0, 'four_thread_prediction_mismatches': 0, 'diagnostic_excluded_from_seed_summary': True}. The diagnostic is excluded from seed summaries. Original seed-42 checkpoints and all earlier outputs stay immutable.

Optimizer steps, sample presentations, selected clients and measured serialized ArrayRecord bytes are in `phase05/training_and_payload_budgets.csv`. Those byte counts exclude wire/TLS/configuration/retransmission overhead; no physical communication/energy measurement is claimed.

## Measured results

| mode | client_id | metric | mean | std_ddof1 | seeds |
|---|---|---|---|---|---|
| centralized | global | exact_subtype_accuracy | 0.698170 | 0.010308 | 3 |
| centralized | global | subtype_macro_f1_observed | 0.381088 | 0.008752 | 3 |
| centralized | global | attack_only_subtype_accuracy | 0.277694 | 0.016393 | 3 |
| centralized | global | family_accuracy | 0.850036 | 0.007643 | 3 |
| centralized | global | family_macro_f1_observed | 0.622608 | 0.015285 | 3 |
| centralized | global | attack_detection_recall | 0.775428 | 0.026449 | 3 |
| centralized | global | benign_false_positive_rate | 0.011725 | 0.015186 | 3 |
| centralized | global | hcm_f1 | 0.739160 | 0.007730 | 3 |
| flower_fedavg | global | exact_subtype_accuracy | 0.647189 | 0.013618 | 3 |
| flower_fedavg | global | subtype_macro_f1_observed | 0.126251 | 0.042864 | 3 |
| flower_fedavg | global | attack_only_subtype_accuracy | 0.136203 | 0.033315 | 3 |
| flower_fedavg | global | family_accuracy | 0.780913 | 0.013029 | 3 |
| flower_fedavg | global | family_macro_f1_observed | 0.387896 | 0.063962 | 3 |
| flower_fedavg | global | attack_detection_recall | 0.718907 | 0.009481 | 3 |
| flower_fedavg | global | benign_false_positive_rate | 0.000261 | 0.000261 | 3 |
| flower_fedavg | global | hcm_f1 | 0.663968 | 0.015516 | 3 |

Detailed client A/B/C and per-class results: `phase02/detailed_unseen_hcm.csv`, `per_class_unseen_counts.csv`, `per_class_flower_local_gains.csv`, `paired_seed_comparisons.csv`. Zero-support subsets are null; C is unsupported for clients 3 and 5 in the original allocation. Globally absent training classes are a separate category (none under this frozen 84-class training schema).

Imbalance and Non-IID tables are in [Results draft](phase11/Results.md) and the [experiment index](EXPERIMENT_INDEX.csv). All negative outcomes are retained. Inverse-frequency weighting can sharply degrade benign false alarms/overall classification. No best validation model is promoted; repeated inspection of this validation set creates exploratory selection bias.

## Figures

![Local/global](figures/phase01_local_global.png)

![Unseen exact](figures/phase02_unseen_exact.png)

![Unseen detection](figures/phase02_unseen_detection.png)

![Seeds](figures/phase03_seed_variability.png)

![Imbalance](figures/phase04_imbalance_tradeoffs.png)

![Non-IID](figures/phase05_partition_participation.png)

![Formal HCM](figures/phase06_formal_hcm.png)

![Family](figures/phase06_family_confusions.png)

All figures also have SVG exports. CSV/JSON tables preserve machine precision and explicit supports/denominators. Newly trained model directories include weights/config, history, final predictions, per-class reports, flat matrices, five error categories and HCM counts/metrics. The two historical reference directories point to their original immutable checkpoints through COMPLETE.json; they do not claim a new training history. Full model HCM tables are in phase06/hcm_counts_metrics.csv and .json, and mathematical denominators are in phase11/Evaluation_Protocol.md.

## HCM convention

The existing `scripts/hcm_eval.py` is reused without redefining HCM. Root→Benign and Root→Attack→Family→Subtype are unpadded. TP excludes root; TN follows pinned Riehl author siblings/immediate children. Micro precision/recall/F1 follow summed node contributions. The original 12 tests include all 7056 leaf pairs against the author reference. HCM is not the five sample error categories, and its FPR is not operational benign FPR.

## Hardware, feature and laboratory readiness

[Pi deployment readiness](../../docs/pi_deployment_readiness.md), [live feature compatibility](../../docs/live_feature_compatibility_report.md), [Kali lab plan](../../docs/kali_lab_deployment_plan.md), and `hardware_deployment/` provide the next implementation boundary. The separate hardware app was exercised using two independent Linux SuperNodes over loopback TLS, including untrusted-CA rejection, schema fingerprints, four updates and per-device latency/RSS/payload logs. The final checkpoint-continuation smoke in phase08/loopback_tls_checkpoint_v4 also passes installed Python/schema byte equality and TOML semantic equality. Earlier bookkeeping failures are retained and explained in FAILURES_AND_RESOLUTIONS.md. This is not Raspberry Pi evidence.

The raw-source README confirms fixed windows but delegates detailed formulas to an unavailable docs folder/paper. Publication retrieval failed: 429 on the first consulted route and 403 on the archived direct request. The 53-feature candidate prototype has **zero claims of verified original semantic parity** and explicitly leaves unknown/missing values null. Seven log inputs cannot be reconstructed from packet-only data. Model input is refused until all required semantics/values are verified. Offline v2 uses synthetic fixed-MAC PCAP; dataset validation, offline replay and new live traffic are separate. Dataset network64 ablations do not resolve missing network formulas automatically.

## Reproduction and verification

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python -m unittest discover -s tests -v
/home/seniorfl/seniorproject-fl-venv/bin/python scripts/33_verify_pre_pi.py
/home/seniorfl/seniorproject-fl-venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Original execution order: `28_pre_pi_research.py audit`, `locals`, `study`, then the documented four-thread diagnostic; `29_feature_readiness.py --output-dir results/pre_pi_research_v1/phase09/offline_fixture_v2`; `30_hardware_loopback_smoke.py`; `31_export_hierarchical_comparisons.py`; `32_summarize_pre_pi.py`; test/verification stages. Training stages guard existing experiment folders; do not rerun into historical destinations. Reproduce in a new research root with configuration paths changed consistently; the orchestrator has a fixed v1 output root. Preserve existing models and all data. See [reproduction details](REPRODUCTION.md).

Final software evidence: 32 passing tests, 44 checkpoint/reference inference matches (285,384 validation predictions), 150 new FedAvg rounds / 720 audited client updates, and 255 unchanged historical file hashes with the authorized status update archived. Full artifact/source hashes are in ARTIFACT_MANIFEST.json. The reference simulation FAB also matches current source bytes, with parsed TOML comparison for packaging reformatting; see audit/FAB_SOURCE_AUDIT.json.

Audit inputs, predefined plan, class weights, allocation row identities and hashes are under `audit/`. Every Flower run records commands/FAB installation/logs and actual per-round/per-client quantities. `requirements.freeze.txt`, `environment.json`, source snapshots, `verification.json` and `ARTIFACT_MANIFEST.json` complete provenance. `COMPLETION_CHECKLIST.md` states COMPLETE/PARTIAL boundaries; [background and related work](phase11/Background_and_Related_Work.md), [evaluation definitions](phase11/Evaluation_Protocol.md) and source-backed academic drafts are under `phase11/`.

## Threats and remaining CS402 work


- Heuristic episode IDs and five-second row correlations do not establish independent sessions. Benign temporal separation is not a session split. No row-IID significance tests or session confidence intervals are claimed.
- Validation observes 28/84 subtypes, has a benign majority and no web family. Unseen-support subsets can be small or empty; class-support denominators accompany every score. All 84 classes exist in global training, so this is client-relative transfer, not open-set recognition.
- Repeated use of this frozen validation across multiple interventions creates exploratory selection bias, even with a bounded grid. No best validation model is promoted to deployment. Fresh independently labelled sessions and an untouched evaluation protocol are needed for confirmatory claims.
- Three seeds measure initialization/shuffle variability on one frozen split, not sampling uncertainty or generalization across sessions. One-seed imbalance/partition/network controls cannot establish robust superiority.
- Local and centralized Adam persist, federated Adam resets. Equal sample presentations do not equal optimization trajectories. Partial participation changes exposure; E=2 increases compute. Weighting changes loss scale and local objectives.
- Training-derived global class-frequency metadata is available to weighted local models; do not describe those interventions as completely information-isolated support learning. No raw samples from other clients enter local gradients.
- More balanced/exclusive allocations operate on training rows, not verified sessions; they redefine locally unseen support. Balanced allocation has no client-relative unseen labels in this frozen dataset. Results cannot be compared on identical unseen masks across different allocations.
- HCM partial credit and branch-dependent TNs differ from flat detection/false-alarm metrics. The reference's immediate-child interpretation is explicitly fixed; generalized DAG/multilabel support is not claimed.
- The original four-thread centralized numerical trajectory differs slightly from the fixed-one-thread cohort; a controlled four-thread diagnostic reproduces it exactly. Historical and new artifacts remain distinct.
- Live extraction has 53 candidate feature formulas but zero verified original-dataset semantic parity claims. Eighteen slots lack an implemented definition; packet-only input lacks log data as well. PCAP fixtures are synthetic, not newly captured attacks. Missing inputs are refused rather than silently imputed.
- Two independent Linux SuperNodes, TLS trust rejection and per-device logging were tested only on loopback/x86. No Raspberry Pi execution, ARM64 compatibility, registered-node authentication, energy or physical latency result is claimed. Serialized model record sizes exclude wire/TLS/configuration/retransmission overhead.


Remaining: authoritative source-extractor recovery and golden-window feature parity; ARM64 compatibility and purchased-device checks; CLI-managed node identity registration tests; isolated physical capture/label sessions and confirmatory local-vs-FL before/after training; uncertainty over genuinely independent sessions; additional prespecified seeds for exploratory controls. No automatic attacks, interface changes or physical purchases were made.

## Verified references

- Project proposal: `references/proposal.docx`.
- DataSense official source: [UNB dataset](https://www.unb.ca/cic/datasets/iiot-dataset-2025.html); local `README.pdf`. Publication identified by official source: Firouzi, Dadkhah, Maret and Ghorbani (2025), *Electronics* 14, 4095. The official page counts 50 attack types; this project has 83 scenario/port-specific training label4 attack labels. Do not equate these taxonomic granularities.
- McMahan et al. (2017), [Communication-Efficient Learning of Deep Networks from Decentralized Data](https://proceedings.mlr.press/v54/mcmahan17a.html), PMLR 54, 1273–1282.
- Cui et al. (2019), [Class-Balanced Loss Based on Effective Number of Samples](https://openaccess.thecvf.com/content_CVPR_2019/html/Cui_Class-Balanced_Loss_Based_on_Effective_Number_of_Samples_CVPR_2019_paper.html), CVPR, 9268–9277. We use its effective-number weighting with cross entropy, not a reproduction of image-classification experiments.
- Riehl et al. (2023), [HCM](https://doi.org/10.1093/jrsssc/qlad057); Görtler et al. (2022), [Neo](https://doi.org/10.1145/3491102.3501823). Pinned reference/source evidence is retained under `results/formal_hcm_v1/sources/`.
- Official [Flower TLS](https://flower.ai/docs/framework/how-to-enable-tls-connections.html), [Streamlit testing](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest), [Microsoft WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking). Runtime syntax was also checked against installed 1.40.0 help/source.
