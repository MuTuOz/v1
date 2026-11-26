# Verifier correction 03 — no experiment changes

The revision-02 scientific checks and artifact hashing completed, but its final
self-check failed because `verify_manifest` reused its manifest-path variable
inside the artifact loop. It consequently excluded the last artifact filename
instead of the manifest itself when comparing file sets. The exact failure is
recorded in `audit/report_revision_03/failed_verification.json`.

The manifest data, numerical metrics and checkpoint predictions were not the
cause. The fix keeps `manifest_path` and `artifact_path` separate. A new regression
test constructs a temporary manifest containing two differently named artifacts
and verifies both explicit-path and automatic latest-revision selection. The
complete **33-test** suite passed; evidence is in
`unit_test_results_revision_03.json` and `logs/full_unit_tests_revision_03.log`.

Earlier modified source/provenance documentation is preserved under
`audit/report_revision_03/original_files/`, with `archive_map.json`. No dataset,
model, prediction, numeric report or figure changed. Both prior manifests,
verification records, source archives and report versions remain intact.

Current integrity files are `ARTIFACT_MANIFEST_revision_03.json`,
`verification_revision_03.json`, and `audit/source_final_revision_03.tar.gz`.
The read-only `scripts/33_verify_pre_pi.py` selects this newest seal and verifies
both historical seals using their archived bytes where a report/source changed.
One-time finalization used `--seal-verifier-fix`; it refuses an existing revision-03
seal. This is a reproducibility bookkeeping correction, not a new scientific fit.
