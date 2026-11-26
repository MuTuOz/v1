# Failure and correction log

All historical source, data, models and reports were preserved. New failed
attempts are retained rather than removed or relabelled as successful.

| Item | Observed evidence | Resolution and outcome |
|---|---|---|
| Initial offline packet fixture | `logs/feature_readiness.log`, `phase09/blocked_neighbor_resolution.json`; implicit Ethernet MAC lookup attempted neighbor resolution and was denied by sandbox | No escalation or permission changes. Fixed explicit synthetic MACs, reject unspecified MACs before serialization, mock neighbor/send APIs in tests. Canonical successful fixture is `phase09/offline_fixture_v2/`. |
| Publication source | `sources/source_retrieval.json`; archived direct MDPI request returned 403; first consulted route returned 429 | Retain verified UNB bibliographic record and local README. Do not infer unavailable feature formulas or claim source-extractor parity. |
| Centralized numerical reproduction | One-thread new seed-42 result differs slightly from historical four-thread training | Prespecified diagnostic addendum; four-thread diagnostic reproduces every state tensor exactly and all 6,486 predictions. Keep it separate from the three-seed cohort. |
| Checkpoint continuation attempt v2 | `logs/hardware_checkpoint_continuation_v2.log`; two rounds completed, final byte comparison rejected reserialized TOML formatting | Require exact Python/schema byte equality and parsed TOML semantic equality. Preserve v2 without a success verification file. |
| Checkpoint continuation attempt v3 | `logs/hardware_checkpoint_continuation_v3.log`; training/TLS/source checks reached final report, whose local variable shadowed the cryptographic hashes module | Rename the report dictionary. Preserve v3 without a success verification file; fresh v4 passed all stages. |
| Draft narrative | Initial prose overgeneralized seed-42 zero recovery on known-family missing subtypes | Compared per-seed CSVs with rendered figures. C4 is positive at seeds 52/62 (65 and 68 correct of 168); corrected Results/status and added explicit numerical checks to the final verifier. Metrics/predictions were already correct and were not changed. |

The verified continuation evidence is `phase08/loopback_tls_checkpoint_v4/`.
Repeated synthetic process checks are not additional scientific IDS experiments;
they are excluded from the 44-record research index and all accuracy comparisons.
Logs contain temporary credential paths/fingerprints, not archived private keys.

Report revision 02 corrects the later C4 per-subtype attribution as well: seed 62 is 60 reconnaissance + 8 DDoS = 68 exact predictions. The earlier claim of 68 reconnaissance and zero DDoS was incorrect. Numeric artifacts were unchanged; direct prediction-based per-subtype assertions now cover this case. See `ERRATA_revision_02.md`.
