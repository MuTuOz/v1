# subtype_sensitivity_v1 — Sensitivity of cyber-event detection to attack subtypes and Non-IIDness

Date: 2026-11-26. Script: [`scripts/34_subtype_sensitivity_analysis.py`](../../scripts/34_subtype_sensitivity_analysis.py).
Provenance (command, package versions, script and every input SHA-256): [provenance.json](provenance.json).

Advisor requests addressed (meeting notes): *"sensitivity analysis of cyber event detection based on
attack sub-types and non-IIDness"*, *"why do differences arise between subtypes — we do not have normal
distributions — analyse from both mitigation and detection perspectives"*, with the example tree
ddos → http → flood, ddos → icmp → flood / frag flood.

## Scope and what was NOT done

* **Post-hoc only.** No model was trained and no inference was run. Inputs are the saved validation
  predictions of all 44 indexed `pre_pi_research_v1` models (44 × 6,486 = 285,384 prediction rows,
  identical to the count re-verified in `verification_revision_03.json`).
* Feature-distribution statistics use **training rows only** (the 22,450-row validation_v1 training set,
  read from the training-only balanced allocation CSVs; the script asserts 22,450 rows and per-subtype
  counts equal to the original client support table). Validation features and the protected test files
  were not read.
* Validation covers 27 attack subtypes (+ benign) and 7/8 families; web and 56 subtypes are absent.
  Many validation subtypes come from one candidate episode (12–438 rows), so rows are correlated and
  per-subtype rates are **descriptive**, not independent-sample estimates. Seed SD (ddof=1, 3 seeds)
  is training-seed variability only.
* The mitigation mapping ([docs/mitigation_mapping_v1.csv](../../docs/mitigation_mapping_v1.csv)) is an
  **analyst-defined heuristic** for discussion, not an empirically validated playbook. Edit it and re-run
  the script into a new output directory to test another mapping.

## Decision levels

The 84-class model predicts a subtype; every coarser decision is derived from it. Besides the existing
detection / family / exact-subtype levels, two intermediate levels were added because the advisor's tree
has a *technique* layer between family and subtype:

| Level | Definition (true vs predicted) | Example counted as correct |
|---|---|---|
| Detection | predicted family ≠ benign | any attack label for an attack row |
| **Mitigation action** | same response category in the mapping | `ddos_http-flood-port-80` → `dos_http-flood-port-554` (both: L7 connection protection) |
| Mitigation strict | same action **and** scope (single source / distributed / internal compromised device) | as above is *wrong* (dos vs ddos scope) |
| Family | `label2` equal | |
| Mechanism | technique without family prefix | `ddos_icmp-flood` ↔ `dos_icmp-flood` |
| Technique | subtype without `-port-N` | `ddos_http-flood-port-80` ↔ `ddos_http-flood-port-1883` |
| Exact subtype | `label4` equal | |

## Result 1 — subtype errors are mostly *operationally cheap*, family/scope errors are not

Rates on the 2,648 validation attack rows, mean ± SD over seeds 42/52/62 ([decision_level_summary.csv](decision_level_summary.csv)):

| Arm | Detection | Mitigation action | Mitigation strict | Family | Technique | Exact subtype |
|---|---:|---:|---:|---:|---:|---:|
| Centralized | 0.7754 ± 0.0264 | 0.7163 ± 0.0002 | 0.6490 ± 0.0069 | 0.6497 ± 0.0065 | 0.2975 ± 0.0218 | 0.2777 ± 0.0164 |
| Flower FedAvg | 0.7189 ± 0.0095 | 0.4752 ± 0.0300 | 0.4580 ± 0.0242 | 0.4637 ± 0.0318 | 0.1411 ± 0.0384 | 0.1362 ± 0.0333 |
| Local client 1 | 0.6840 ± 0.0637 | 0.1864 ± 0.0019 | 0.1191 ± 0.0049 | 0.1225 ± 0.0047 | 0.1130 ± 0.0012 | 0.1062 ± 0.0028 |
| Local client 2 | 0.7638 ± 0.0355 | 0.4304 ± 0.0067 | 0.4304 ± 0.0067 | 0.4304 ± 0.0067 | 0.1522 ± 0.0046 | 0.1522 ± 0.0046 |
| Local client 3 | 0.6855 ± 0.0173 | 0.0149 ± 0.0070 | 0.0149 ± 0.0070 | 0.0149 ± 0.0070 | 0.0021 ± 0.0013 | 0.0021 ± 0.0013 |
| Local client 4 | 0.7633 ± 0.0028 | 0.5427 ± 0.0052 | 0.4622 ± 0.0029 | 0.4682 ± 0.0040 | 0.1284 ± 0.0085 | 0.1071 ± 0.0059 |
| Local client 5 | 0.7034 ± 0.0383 | 0.2685 ± 0.0095 | 0.1788 ± 0.0097 | 0.1883 ± 0.0021 | 0.1488 ± 0.0129 | 0.1338 ± 0.0097 |

(Detection and exact-subtype columns reproduce the attack-only values already in `PROJECT_STATUS.md`.)

Reading: for the centralized model, exact subtype accuracy is 0.28 but the predicted subtype would
trigger the *right mitigation action* for 0.72 of attack rows; most remaining exact-subtype errors are
port or dos/ddos confusions inside the same response category. For Flower the step from detection
(0.72) to mitigation action (0.48) is large: Flower more often assigns a detected attack to a *different
response category* (e.g. both Mirai subtypes: detection 0.665 / 0.787 but mitigation and family 0.000,
see per-subtype table). Local-only models detect attacks at similar rates (0.68–0.76) but almost never
choose the right response for attacks absent from their own data.

Per-subtype, per-arm tables: [per_subtype_reference_summary.csv](per_subtype_reference_summary.csv)
(heatmaps: [centralized](figures/subtype_level_heatmap_centralized.png), [Flower](figures/subtype_level_heatmap_flower_fedavg.png)).
Subtypes that are weak at **detection** for every arm: `mitm_arp-spoofing` (centralized 0.068, Flower 0.000),
`bruteforce_dictionary-ssh` (0.222 / 0.011), `bruteforce_dictionary-telnet` (0.467 / 0.117),
`recon_host-disc-tcp-ack-ping` (0.516 / 0.505). These are low-volume, benign-looking attacks;
they are a detection problem, not a subtype-granularity problem.

## Result 2 — locally unseen attacks: collaboration changes the response, not just the label

Each local model and the two global models scored on the same rows, split by whether the subtype (and
its family) occurs in that client's own training data ([client_seen_unseen_summary.csv](client_seen_unseen_summary.csv);
rows = client × subtype × seed cells, row-weighted):

| Subtype status at the client | Rows | Arm | Detection | Mitigation action | Family | Exact |
|---|---:|---|---:|---:|---:|---:|
| unseen subtype, unseen family | 26,274 | local-only | 0.685 | 0.051 | 0.000 | 0.000 |
| | | Flower | 0.703 | 0.447 | 0.437 | 0.140 |
| | | centralized | 0.767 | 0.697 | 0.636 | 0.290 |
| unseen subtype, known family | 3,342 | local-only | 0.718 | 0.709 | 0.666 | 0.000 |
| | | Flower | 0.704 | 0.658 | 0.638 | 0.040 |
| | | centralized | 0.713 | 0.707 | 0.672 | 0.031 |
| locally seen subtype | 10,104 | local-only | 0.811 | 0.766 | 0.742 | 0.394 |
| | | Flower | 0.765 | 0.487 | 0.476 | 0.159 |
| | | centralized | 0.817 | 0.770 | 0.677 | 0.328 |

For attacks whose whole family is new to a client, local-only detection is already 0.685 (an anomaly is
still flagged) but the response is almost always wrong (0.051); Flower raises the correct-response
rate to 0.447. For subtypes the client *has* seen, Flower is worse than the local model (0.487 vs 0.766
mitigation action) — the federated model loses client-specific knowledge. This is the trade-off to
discuss, not a general ranking.

## Result 3 — Non-IIDness sensitivity

**Partition level** (Flower, seed 42, 5 clients, 15 rounds, identical 22,450 training rows, only the
client allocation changes; [partition_sensitivity_global.csv](partition_sensitivity_global.csv),
[figure](figures/partition_sensitivity.png)):

| Allocation | mean client JS divergence (bits) | subtypes per client | Detection | Mitigation action | Family | Exact | Benign FPR |
|---|---:|---:|---:|---:|---:|---:|---:|
| balanced (IID-like) | 0.0001 | 84.0 | 0.7708 | 0.6986 | 0.6163 | 0.2349 | 0.0122 |
| original | 0.2354 | 20.4 | 0.7270 | 0.4483 | 0.4354 | 0.1137 | 0.0005 |
| exclusive | 0.2569 | 17.6 | 0.6322 | 0.4233 | 0.4131 | 0.1110 | 0.0000 |

All attack-side rates fall monotonically as Non-IIDness increases, while benign FPR also falls (the
more Non-IID models are more conservative). One seed per allocation; differences are a single-run
observation, not a tested effect.

**Subtype level** (27 validation attack subtypes; Spearman rank correlation, which needs no normality
assumption; [nonid_gap_spearman.csv](nonid_gap_spearman.csv), [figure](figures/nonid_spread_vs_gap.png)).
In the original partition every validation subtype is held by exactly one or two clients. Subtypes
split across two clients have a *larger* Flower-minus-centralized deficit: exact subtype ρ = −0.389
(p = 0.045), mitigation action ρ = −0.524 (p = 0.005) against the number of holding clients. These
split subtypes are mostly dos/ddos twins of the same TCP/UDP flood held by different clients, which is
consistent with conflicting client updates being averaged, but n = 27, rows are correlated and no
multiple-comparison correction was applied: treat it as an exploratory pattern.

Loss-weighting interaction (seed 42, [loss_weighting_per_subtype_s42.csv](loss_weighting_per_subtype_s42.csv)):
inverse-frequency weighting lifts detection of the weak subtypes (centralized `mitm_arp-spoofing`
0.025 → 0.932, `bruteforce_dictionary-ssh` 0.200 → 1.000; Flower `mitm_arp-spoofing` 0.000 → 0.924)
but family-level correctness for them barely changes, and the global benign FPR cost is documented in
phase 4 of pre_pi_research_v1.

## Result 4 — why subtypes differ: distributions are not normal, and "separable" ≠ "generalizable"

**Normality** ([feature_normality_training.csv](feature_normality_training.csv), [figure](figures/normality_rejection.png)):
Shapiro–Wilk per (subtype, feature) on training rows after the model's signed-log1p transform,
52 subtypes with ≥ 20 rows, at most 500 rows each, Benjamini–Hochberg over 3,069 non-constant tests:
**99.2 % reject normality (q < 0.05)**; median |skew| 1.76, median excess kurtosis 3.02; 623 further
(subtype, feature) cells are constant. Consequences for the analysis: means/SDs and t-tests/ANOVA
are not appropriate summaries; this study therefore uses KS statistics, Spearman ranks and a
classifier two-sample test, all distribution-free.

**Sibling separability on training data** ([sibling_pair_separability_training.csv](sibling_pair_separability_training.csv)):
157 sibling pairs (same technique on another port: 75; same mechanism dos vs ddos: 77; the advisor's
ddos example tree: 5). A random forest separating each pair under 5-fold CV reaches median balanced
accuracy 0.99 — but only 8 pairs have ≥ 2 candidate episodes per class so that whole episodes can be
held out (StratifiedGroupKFold); for those the median drops to **0.86**. For the advisor's tree:

| Pair | rows | KS-dominant features (top) | C2ST balanced acc. |
|---|---|---|---:|
| ddos_http-flood-port-80 vs ddos_icmp-flood | 72 / 24 | window-size_min, tcp-flags_avg, ip-flags | 0.993 |
| ddos_http-flood-port-80 vs ddos_icmp-frag-flood | 72 / 312 | ip-flags_avg/std, tcp-flags-ack_count, ports | 0.947 |
| ddos_icmp-flood vs ddos_icmp-frag-flood | 24 / 312 | ports_src/dst_count, tcp-flags-ack/psh_count | 0.976 |
| ddos_icmp-flood vs dos_icmp-flood | 24 / 36 | time-delta_avg/std, packets_all_count | 0.924 |
| ddos_icmp-frag-flood vs dos_icmp-frag-flood | 312 / 312 | payload-length_avg, packet-size_std | 0.982 |

(icmp subtypes have no validation rows, so their validation behaviour cannot be measured.)

**Validation confusions between siblings** ([sibling_pair_validation_confusion.csv](sibling_pair_validation_confusion.csv)),
3 seeds pooled: centralized predicts `ddos_synonymousip-flood-port-80` as its dos twin in 0.889 of rows,
`ddos_syn-flood-port-80` as `dos_syn-flood-port-554` in 0.861, `dos_tcp-flood-port-80` as
`ddos_tcp-flood-port-80` in 0.394 — although those pairs are 0.86–1.00 separable on training rows.

Interpretation offered for discussion (not a proven cause): within one candidate episode the 5-second
windows are near-duplicates, so a pair can look perfectly separable in training because each subtype
was recorded in a different session (different rates/TTL/timing), not because the attack technique has
a stable signature. On a new episode the model falls back to the features shared by the mechanism, so
dos/ddos and port variants collapse. The differences between subtypes therefore come from three
sources visible in the data: (1) heavy-tailed, non-normal, partly constant features; (2) one or very
few episodes per subtype (session fingerprint vs technique signature); (3) whether the subtype's
mechanism twin lives at another client (Non-IID split).

## Files

| File | Content |
|---|---|
| per_subtype_reference_per_seed.csv / _summary.csv | per arm × subtype × seed rates at all 7 levels + 4 error categories |
| client_subtype_seen_unseen_per_seed.csv | client × subtype × seed, local vs Flower vs centralized |
| subtype_nonid_indicators.csv | training support, holding clients, max client share, normalized entropy |
| partition_sensitivity_*.csv | original / balanced / exclusive Flower runs |
| nonid_gap_spearman.csv | all 32 Spearman tests (not only significant ones) |
| feature_normality_training.csv | every Shapiro–Wilk test with BH q |
| sibling_pair_*.csv | KS, C2ST and validation sibling-confusion tables |
| figures/*.png, *.svg | report-ready figures |
| summary.json, provenance.json | key numbers; command, versions, hashes |

Runtime 330 s on the cloud container (4 vCPU, Python 3.13.18, pandas 3.0.x, scipy, scikit-learn).
Analysis environment differs from the training venv (`/home/seniorfl/...`, Python 3.12.3); this
matters only for the RF-based C2ST numbers, not for the prediction-based tables.
