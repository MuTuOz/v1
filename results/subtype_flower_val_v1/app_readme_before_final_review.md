# 84-class Flower validation_v1 experiment

This isolated application preserves `flower_app/` and the existing centralized
baseline. Read `results/subtype_flower_val_v1_summary.md` for measured results and
limitations once the run completes.

Use `/home/seniorfl/seniorproject-fl-venv/bin/python
scripts/26_run_flower_subtype_val_v1.py --stage all` from the project root.
The audit stage requires the pre-edit source backup and preservation manifest.
Outputs are append-only at experiment level: an existing audit/model/evaluation
causes an error. A new independent run needs distinct output/model names and a
new preservation manifest, rather than reusing historical paths.

`flwr run flower_subtype_app local-simulation --stream` builds/installs the FAB.
The existing WSL Flower local-simulation connection must specify five SuperNodes,
Ray and one CPU per client. The CLI wrapper checks for the final checkpoint.
External data and outputs resolve through `project-root`, never a parent of the
installed package. Override this setting explicitly when moving the project.
The default path is recorded in `pyproject.toml` and packaged `schema.json`.
Only train.csv, five client training CSVs and validation.csv are allowlisted.

Every round requires all five clients and verifies each sample count and the
actual Flower weighted aggregation. Client Adam state resets every round.
The final model is evaluated once; no validation-based checkpoint selection.
Macro F1 primarily averages over 28 observed ground-truth subtypes (27 attack
subtypes), and 7 observed families. The 84-class CSV classification report also
contains a zero-support-inclusive macro average, which is a distinct statistic.
