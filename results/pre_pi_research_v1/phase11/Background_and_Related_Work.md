# Draft background, motivation and related work

Industrial IoT devices can observe different workloads and attack types. A local
classifier may therefore have no training examples for a subtype observed at
another client. The project proposal asks whether collaboration improves that
client's recognition of such attacks. The present study operationalizes this as
client-relative missing-training-support evaluation, with identical validation
rows for local-only, federated and centralized predictors. It does not introduce
an open-set detector or establish independent physical-session generalization.

The proposal's CS401 deliverables are an auditable dataset/split review, baseline
models, heterogeneous-client and participation studies, hierarchical evaluation,
a Streamlit demonstration and repeatable experiment artifacts. The current
software bundle provides those components within the frozen validation protocol.
Physical Pi/Kali work is prepared separately; the software evidence cannot stand
in for hardware deployment or new laboratory-session results.

## Verified related work and use in this project

- **DataSense CIC IIoT 2025.** The [official UNB dataset publication page](https://www.unb.ca/cic/datasets/iiot-dataset-2025.html)
  identifies Firouzi, Dadkhah, Maret and Ghorbani (2025), *DataSense: A Real-Time
  Sensor-Based Benchmark Dataset for Attack Analysis in IIoT with Multi-Objective
  Feature Selection*, *Electronics* 14, 4095. The project's training files supply
  83 attack `label4` values, some scenario/port specific, plus benign; this is not
  identical granularity to the official page's 50 attack-type description. The
  local README delegates full feature definitions to external documentation.
  Publication retrieval was unsuccessful (429 on the first consulted route,
  403 on the archived direct request); original extractor semantics remain a gap.
- **FedAvg.** [McMahan et al. (2017)](https://proceedings.mlr.press/v54/mcmahan17a.html),
  *Communication-Efficient Learning of Deep Networks from Decentralized Data*,
  PMLR 54, 1273–1282, is the basis for selected-client sample-count aggregation.
  This project uses actual Flower 1.40.0 execution and audits update counts,
  participation and weighted tensors. Its local optimizer is Adam, so these runs
  are not a reproduction of every optimizer/data setting in that paper.
- **Class imbalance.** [Cui et al. (2019)](https://openaccess.thecvf.com/content_CVPR_2019/html/Cui_Class-Balanced_Loss_Based_on_Effective_Number_of_Samples_CVPR_2019_paper.html),
  *Class-Balanced Loss Based on Effective Number of Samples*, CVPR, 9268–9277,
  motivates the prespecified effective-number weighting, beta=0.999. We apply
  the training-derived weights to cross entropy and compare them with unweighted
  and inverse-frequency controls. No improvement or transfer of their original
  image-classification measurements is assumed.
- **Formal HCM.** [Riehl, Neunteufel and Hemberg (2023)](https://doi.org/10.1093/jrsssc/qlad057),
  *Hierarchical confusion matrix for classification performance evaluation*,
  JRSS Series C 72(5), 1394–1412, supplies the mathematical evaluator. The pinned
  author's tree/SPL/mandatory-leaf implementation at commit
  `2256f4c24b813ffb752a53e20a8092ec7b1e3ac3` fixes the operational TN convention.
  The unchanged project module is checked against all 7,056 leaf pairs.
- **Visualization.** [Görtler et al. (2022)](https://doi.org/10.1145/3491102.3501823),
  *Neo: Generalizing Confusion Matrix Visualization to Hierarchical and
  Multi-Output Labels*, CHI '22, motivates distinct levels, conditional
  normalization and explicit zero-support views. It is not the source of Riehl
  TP/TN/FP/FN, and no full Neo implementation is claimed.

Archived primary-source retrieval metadata is in `../sources/`; the pinned
Riehl/Neo papers and reference code remain under `results/formal_hcm_v1/sources/`
from the project root. No unverified citation or physical measurement is used.

## Contribution supported by current evidence

The deliverable is an executable matched local/federated/centralized framework,
three client-relative unseen support definitions, a bounded three-seed study,
controlled imbalance/partition interventions, one consistent hierarchical
evaluation protocol, and an artifact-driven dashboard. Results include negative
outcomes and the inability to recover some known-family missing subtypes. These
are descriptive findings for one frozen split, not a claim of novelty,
publication readiness or deployment efficacy. See Methods, Results and Threats
to Validity for exact budgets, measurements and limitations.
