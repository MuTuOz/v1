# SeniorProject working instructions

- Read `references/proposal.docx` and `PROJECT_STATUS.md` before research changes. The proposal defines the academic scope; code, datasets and saved outputs establish what actually exists. Keep completed work, archived evidence and future plans distinct.
- Research question: does federated collaboration help a Non-IID IIoT client recognize attacks absent from its own training data but present at other clients? Compare local-only, federated and centralized models on the same versioned evaluation rows. The initial dataset is DataSense CIC IIoT 2025, using the project's 5-second sample tables.

## Dataset and hierarchy

- Treat `data/raw/`, existing splits, client partitions, models and results as historical evidence. **Never overwrite or delete historical datasets, model weights or results.** Use new experiment names and output paths; do not rerun scripts with fixed historical destinations.
- The current matched comparison uses `data/validation_v1/`: `train.csv` (22,450 rows), five `client_N_train.csv` partitions and `validation.csv` (6,486 rows). Preserve those partitions. Earlier `splits_v1`, `splits_v2` and `fl_clients_v1` experiments have different protocols.
- Hierarchy: detection (`label1`, benign/attack) → family (`label2`: benign, bruteforce, ddos, dos, malware, mitm, recon, web) → subtype (`label4`: benign + 83 attack subtypes). `label3` is additional metadata, not the current subtype target.
- For the 84-class models, derive class IDs and subtype→family mapping from training only: benign is ID 0, attack subtypes are sorted. Verify one family per subtype and checkpoint schema equality. Family predictions come from the predicted subtype's mapping; detection is predicted-family != benign. Distinguish these from the separate 8-class family model.
- Use the saved order of 71 `network_`/`log_` features. Exclude labels, device names, timestamps and episode IDs from model inputs. Match baseline preprocessing: float64, NaN/±Inf→0, clip to ±1e8, signed log1p, float32. Do not silently change architecture, feature order or preprocessing in a matched comparison.

## Leakage, measurements and reproducibility

- Do not access `test_episode.csv` or `test_web_diagnostic.csv` in validation_v1 work. Inspect archived reports instead. Legacy scripts may open these files and overwrite outputs; inspect them before running. Any future held-out evaluation needs an explicitly defined separate scope.
- Fit learned preprocessing and choose training-derived mappings without validation/test information. Use validation for the documented purpose; never select checkpoints or tune on held-out test records. Check partition identity, overlap, label coverage and class supports.
- Episode IDs are heuristic candidate groups, not verified independent sessions. Benign validation is a temporal holdout. Validation covers only 28/84 subtypes and 7/8 families; 56 subtypes and the web family are absent. Never claim full 84-class coverage or independent-session evaluation.
- Back up existing source before editing it. Save exact configuration, seeds and shuffle rules, dependencies, source snapshot/hash, input hashes, weights, commands, logs, failures, metrics, predictions, per-class reports and confusion matrices in a new experiment directory.
- Record important screenshots when a UI, device setup or run state provides evidence; save them with date, experiment ID and caption/context. Preserve original screenshots and report-ready PNG/SVG figures alongside machine-readable artifacts. Never use a screenshot alone as the source of numerical metrics or fabricate one.
- Report actual measurements with denominators and label sets. Separate observed-class Macro F1 from zero-support-inclusive Macro F1. Keep detection recall, attack-only subtype accuracy and benign false-positive rate distinct. Verify the five disjoint hierarchical categories sum to every evaluation row.
- For sample-weighted FedAvg, verify each client's sample count, participation and aggregation weights. Record optimizer-state reset policy and total training exposure. Do not equate a federated round with a centralized optimization epoch.

## Runtime and research scope

- Prefer `/home/seniorfl/seniorproject-fl-venv/bin/python`. Preserve the original `flower_app/` (8 classes); `flower_subtype_app/` is the separate 84-class Flower 1.40.0 app. Packaged apps must resolve external data through explicit `project-root`, not package-relative parent guesses.
- Keep changes within authorized project/Flower/venv directories. No sudo or unrelated system changes. Document sandbox failures; do not change security settings to get around them. Use installed dependencies or supported runtime options within allowed paths.
- Label Flower/Ray runs as **simulation**. An old Raspberry Pi-labelled inference log does not establish physical federated deployment. Real Raspberry Pi Flower clients, isolated Kali Linux IIoT traffic generation and hardware/network measurements require separate implementation and evidence.
- Next priorities, in order: (1) matched 84-class local-only validation_v1 baselines; (2) locally unseen subtype and family evaluation; (3) repeated seeds and class-imbalance experiments; (4) formal hierarchical evaluation. These remain planned until executed and verified. Do not implement them in a documentation-only task.
- Update `PROJECT_STATUS.md` after verified research milestones, linking exact evidence and limitations. Give user-facing completion summaries in Turkish unless requested otherwise.
