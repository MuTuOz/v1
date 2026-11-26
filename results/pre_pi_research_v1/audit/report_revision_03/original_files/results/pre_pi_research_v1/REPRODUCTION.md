# Reproduction and artifact guide

The v1 bundle is completed evidence. Training destinations are exclusive and
must not be reused. The saved source archive, exact environment freeze,
configuration JSONs, data hashes, allocation manifests and histories define the
run. The original historical references remain in `models/` and are hash-bound
by each reference `COMPLETE.json` and the preservation audit.

## Read-only validation and demonstration

From the SeniorProject root:

```bash
/home/seniorfl/seniorproject-fl-venv/bin/python scripts/33_verify_pre_pi.py
/home/seniorfl/seniorproject-fl-venv/bin/python -m unittest discover -s tests -v
/home/seniorfl/seniorproject-fl-venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

The verifier repeats checkpoint inference and numerical/hash checks without
training or rewriting reports. Unit tests use fixtures and saved artifacts;
Python bytecode caches are excluded from the seal. Do not redirect their output
into an already sealed log. The browser demo command binds loopback only.

## Original execution recipe (fresh workspace only)

The orchestrator deliberately fixes `results/pre_pi_research_v1/` relative to
its project root. For a fresh reproduction, create a separate project checkout
under an authorized directory; restore the source snapshot, copy the proposal,
AGENTS instructions, original schema/apps and pinned HCM test reference. Make
only the seven allowlisted immutable CSVs available (`train.csv`, five
`client_N_train.csv`, `validation.csv`), plus the two historical checkpoints.
Do not copy/link the protected test splits. Feature-header auditing additionally
needs the original README and the two raw 5-second CSV headers. Use the recorded
Python environment or reproduce its versions in a new user-owned venv.

Bootstrap fresh `audit/`, `logs/`, `figures/`, `sources/` and `phase01/` through
`phase11/` directories. Record a preservation manifest/source backup before
running. The following commands describe the executed order; they are not a
request to rerun them in the completed current workspace:

```bash
python scripts/28_pre_pi_research.py audit
python scripts/28_pre_pi_research.py locals
python scripts/28_pre_pi_research.py study
# The four-thread diagnostic was a separate declared addendum:
python - <<'PY'
import runpy
m = runpy.run_path('scripts/28_pre_pi_research.py')
m['fit'](m['config']('diagnostic_centralized_threads4_s42', 3, 'centralized', train_threads=4))
m['aggregate']()
PY
python scripts/29_feature_readiness.py --output-dir results/pre_pi_research_v1/phase09/offline_fixture_v2
python scripts/31_export_hierarchical_comparisons.py
python scripts/32_summarize_pre_pi.py
```

The audit writes the predefined grid before fits. Each Flower experiment saves
its exact CLI commands and run-config TOML; the launch record is authoritative.
The coordinator uses loopback port 39102 and a dedicated authorized Flower home.
Do not run simultaneous reproductions against the same port/home. Source/data
paths derive from the fresh project root, not a packaged-app parent directory.

The optional physical preparation smoke requires its own fresh output/home:

```bash
python scripts/30_hardware_loopback_smoke.py --output-dir results/pre_pi_research_v1/phase08/NEW_SMOKE --flower-home /home/seniorfl/.flwr/NEW_SMOKE --initial-checkpoint models/subtype_flower_val_v1.pt
```

It starts only local Linux processes with synthetic rows and ephemeral TLS
credentials. It is not Raspberry Pi evidence and does not run live capture or
attacks. The unit tests, health checks, source retrieval records, manuscript
drafts and final seal are separate provenance steps. `33_verify_pre_pi.py --seal`
is a **one-time finalization for this audited bundle**, not a generic bootstrap
command; it expects the documented v1 evidence and refuses an existing seal.

## Where to find measurements

- `EXPERIMENT_INDEX.csv`: 44 full-validation model records and artifact paths.
- `phase02/`: A/B/C masks, supports, per-class gains and matched seed comparisons.
- `phase03/`: all per-class results, per-seed checkpoints and mean/sample-SD tables.
- `phase04/per_family_comparison.csv`: observed support, recall/F1 and weighting trade-offs.
- `phase05/`: allocation/participation experiments and actual update/presentation/payload budgets.
- `phase06/`: full formal HCM counts/metrics and family comparison tables.
- `phase07/`: dashboard health and demo instructions; `figures/`: PNG/SVG pairs.
- `phase08/`: separate synthetic process tests; v4 is the final checkpoint-continuation evidence.
- `phase09/`: canonical offline fixture v2, parity gaps/drift and dataset-only network64 ablations.
- `phase11/`: background, Methods, Results, formal definitions, threats and presentation outline.

No confidence interval treats correlated five-second rows as independent
sessions. No current command uses protected test metrics for selection. Future
experiments and physical captures require new IDs, new outputs and explicit
session/feature acceptance criteria.

## Report revision 02 and current integrity record

A final per-subtype check corrected the C4 seed-62 narrative: 68 exact predictions consist of 60 reconnaissance and 8 DDoS, not 68 reconnaissance. All predictions, metrics, checkpoints and figures are unchanged. Previous report/source bytes are preserved under `audit/report_revision_02/`; the original seal, verification and source archive are retained. The current seal is [ARTIFACT_MANIFEST_revision_02.json](ARTIFACT_MANIFEST_revision_02.json), with [verification_revision_02.json](verification_revision_02.json) and `audit/source_final_revision_02.tar.gz`. The read-only verifier automatically selects the current revision and also verifies the original seal against unchanged/archived bytes. See [errata](ERRATA_revision_02.md).

The documented correction was finalized once using `python scripts/33_verify_pre_pi.py --seal-correction`. This preserves the original seal and refuses an existing correction seal.
