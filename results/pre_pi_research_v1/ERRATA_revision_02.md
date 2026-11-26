# Report correction 02 — per-subtype attribution only

The numerical research artifacts were correct. A sentence in the draft Results
and project status incorrectly attributed all 68 correct C4 subset-C predictions
at seed 62 to `recon_host-disc-udp-ping` and said both missing DDoS subtypes
remained unrecovered. The saved predictions and per-class counts show:

| Flower seed | recon_host-disc-udp-ping (n=144) | ddos_ack-frag-flood-port-1883 (n=12) | ddos_push-ack-flood-port-80 (n=12) | Exact total (n=168) |
|---|---:|---:|---:|---:|
| 42 | 0 | 0 | 0 | 0 |
| 52 | 65 | 0 | 0 | 65 |
| 62 | 60 | 8 | 0 | 68 |

The original aggregate exact accuracies 0, 65/168 and 68/168, their mean
0.2638888888888889, and centralized mean 0.19047619047619047 are unchanged.
The known-family subtype transfer is therefore positive for reconnaissance at
seeds 52/62 and for the ACK-fragment DDoS subtype at seed 62, with small support
and seed variability. The push-ACK subtype remains unrecovered in these runs.

No dataset, split, model, prediction, numerical metric, CSV table or figure was
changed. Current prose and its generator were corrected. The verifier now
recomputes these individual subtype counts directly from each checkpoint's
reproduced validation predictions, in addition to aggregate checks.

The seven affected pre-correction source/report files are preserved byte for
byte under `audit/report_revision_02/original_files/`, with `archive_map.json`.
The original `ARTIFACT_MANIFEST.json`, `verification.json`, environment/freeze
and `audit/source_final.tar.gz` remain unchanged. The original seal is checked
using those archived versions for changed paths and current bytes elsewhere.

Current integrity evidence is `ARTIFACT_MANIFEST_revision_02.json`,
`verification_revision_02.json`, and `audit/source_final_revision_02.tar.gz`.
The read-only `scripts/33_verify_pre_pi.py` automatically uses this newer seal
and additionally verifies preservation of the first sealed version.
