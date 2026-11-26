# Draft Results

The versioned index contains 44 evaluated model records: 42 newly trained scientific/diagnostic checkpoints plus two immutable historical reference evaluations. The separate synthetic two-node deployment smoke is not a scientific accuracy experiment.

## Primary research result: client-relative absent attack subtypes

| client_id | samples | local_only | flower | centralized | flower_minus_local |
|---|---|---|---|---|---|
| 1 | 2192.000000 | 0.000000 | 0.131083 | 0.212591 | 0.131083 |
| 2 | 1955.000000 | 0.000000 | 0.037511 | 0.235465 | 0.037511 |
| 3 | 2528.000000 | 0.000000 | 0.142669 | 0.290876 | 0.142669 |
| 4 | 1210.000000 | 0.000000 | 0.179063 | 0.417355 | 0.179063 |
| 5 | 1987.000000 | 0.000000 | 0.166751 | 0.203993 | 0.166751 |

Rates are means over exactly three matched seeds. All five local-only models have zero exact accuracy on their own missing subtype sets, whereas Flower is positive for every client in subset A. This is evidence of client-relative subtype transfer under this frozen split, not globally unseen detection. Centralized has higher mean exact accuracy for every client in A and B; the C4 known-family subtype subset is an exception where Flower has the higher mean.

## Missing subtype within a known family (C)

| client_id | samples | local_only | flower | centralized |
|---|---|---|---|---|
| 1 | 72.000000 | 0.000000 | 0.000000 | 0.000000 |
| 2 | 874.000000 | 0.000000 | 0.000000 | 0.002670 |
| 3 | 0.000000 | — | — | — |
| 4 | 168.000000 | 0.000000 | 0.263889 | 0.190476 |
| 5 | 0.000000 | — | — | — |

Subset C is empty for clients 3 and 5. Flower exact accuracy stays zero for clients 1 and 2. For client 4 (168 rows), Flower scores 0, 0.3869047619047619 and 0.40476190476190477 for seeds 42/52/62, respectively: mean 0.2638888888888889 versus centralized mean 0.19047619047619047. The gains come from recon_host-disc-udp-ping (65/144 and 68/144 correct at seeds 52/62); the two missing DDoS subtypes remain unrecovered. This is a seed-sensitive positive result, alongside negative outcomes on C1/C2. Detection gains are mixed and cannot be inferred from exact subtype gains.

## Global models: repeated-seed summary

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

## Imbalance ablations: seed 42

| experiment_id | exact_subtype_accuracy | subtype_macro_f1_observed | attack_only_subtype_accuracy | family_accuracy | family_macro_f1_observed | attack_detection_recall | benign_false_positive_rate | hcm_f1 |
|---|---|---|---|---|---|---|---|---|
| effective_number_centralized_s42 | 0.665125 | 0.364813 | 0.261329 | 0.810515 | 0.569204 | 0.829305 | 0.056279 | 0.705439 |
| effective_number_flower_s42 | 0.633981 | 0.094932 | 0.155589 | 0.714462 | 0.285687 | 0.799094 | 0.035956 | 0.628908 |
| inverse_frequency_centralized_s42 | 0.163583 | 0.338808 | 0.280211 | 0.333488 | 0.387382 | 0.985650 | 0.916884 | 0.361331 |
| inverse_frequency_flower_s42 | 0.611317 | 0.120952 | 0.138595 | 0.708757 | 0.293478 | 0.847432 | 0.062533 | 0.620417 |

Inverse-frequency weighting can greatly increase false alarms and reduce exact accuracy. Effective-number weighting also has trade-offs; neither intervention is assumed to dominate. No model was selected for deployment.

## Non-IID / participation / local epoch ablations

| experiment_id | clients_per_round | local_epochs | exact_subtype_accuracy | subtype_macro_f1_observed | attack_only_subtype_accuracy | family_accuracy | family_macro_f1_observed | attack_detection_recall | benign_false_positive_rate | hcm_f1 |
|---|---|---|---|---|---|---|---|---|---|---|
| balanced_flower_p5_e1_s42 | 5 | 1 | 0.680389 | 0.281124 | 0.234894 | 0.836109 | 0.579519 | 0.770770 | 0.012246 | 0.720549 |
| exclusive_flower_p5_e1_s42 | 5 | 1 | 0.637064 | 0.083379 | 0.111027 | 0.760407 | 0.368833 | 0.632175 | 0.000000 | 0.638416 |
| original_flower_p3_e1_s42 | 3 | 1 | 0.635985 | 0.060207 | 0.109517 | 0.763953 | 0.291720 | 0.744335 | 0.000782 | 0.649622 |
| original_flower_p5_e2_s42 | 5 | 2 | 0.650170 | 0.121865 | 0.143127 | 0.761024 | 0.334840 | 0.705438 | 0.000000 | 0.652881 |

Balanced partitioning improves some scores and eliminates client-relative unseen classes; exclusive-label allocation and partial participation must be interpreted with their own support/exposure. These are one-seed exploratory controls.

## Dataset-only network feature ablation

| experiment_id | features | exact_subtype_accuracy | subtype_macro_f1_observed | attack_only_subtype_accuracy | family_accuracy | family_macro_f1_observed | attack_detection_recall | benign_false_positive_rate | hcm_f1 |
|---|---|---|---|---|---|---|---|---|---|
| network64_centralized_s42 | 64 | 0.700278 | 0.375350 | 0.269260 | 0.853685 | 0.644164 | 0.773792 | 0.002345 | 0.741512 |
| network64_flower_fedavg_s42 | 64 | 0.632593 | 0.063986 | 0.100831 | 0.771354 | 0.321726 | 0.750378 | 0.000521 | 0.652432 |

A 64-feature dataset model is not proof that 64 network features can be reconstructed with identical live semantics. No physical classification results were produced.
