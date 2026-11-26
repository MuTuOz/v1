# Sources inspected for formal_hcm_v1

Local search on 2026-10-25 found the project proposal and no Riehl/Neo papers.
The following primary records and author sources were consulted. Downloaded
files are research evidence, not new project code; authorship remains with the
original authors. `retrieval.json` records URLs, retrieval time, failures and
SHA-256 values. `riehl_commit.json` pins the author implementation.

1. Kevin Riehl, Michael Neunteufel and Martin Hemberg (2023).
   **Hierarchical confusion matrix for classification performance evaluation**.
   *Journal of the Royal Statistical Society Series C: Applied Statistics*,
   72(5), 1394–1412. Published online 3 July 2023.
   [DOI](https://doi.org/10.1093/jrsssc/qlad057),
   [publisher](https://academic.oup.com/jrsssc/article/72/5/1394/7217007),
   [author preprint](https://arxiv.org/abs/2306.09461).
   The downloaded PDF is arXiv **2306.09461v1**, 15 June 2023, eight pages;
   the final journal record was checked separately. Relevant definitions:
   journal §4.1 Eq. (4), §4 Eq. (3), Figure 4a; preprint §IV-A, pp. 5–6.

2. [Author reference implementation](https://github.com/DerKevinRiehl/HierarchicalConfusionMatrix),
   commit **2256f4c24b813ffb752a53e20a8092ec7b1e3ac3**.
   Pinned [HierarchicalConfusion.py](https://github.com/DerKevinRiehl/HierarchicalConfusionMatrix/blob/2256f4c24b813ffb752a53e20a8092ec7b1e3ac3/hierarchical_confusion_matrix/HierarchicalConfusion.py).
   Inspected `getHierarchicalConfusion_Tree_SPL_MLNP`,
   `getHierarchical_TrueNegative`, `getNeighbors`, `getDescendants`, and
   `determineHierarchicalConfusionMatrix`; saved unchanged as
   `riehl_reference.py`. Tests execute this reviewed snapshot as an independent
   comparator, without installing an unpinned PyPI HCM package.

3. Jochen Görtler, Fred Hohman, Dominik Moritz, Kanit Wongsuphasawat, Donghao Ren,
   Rahul Nair, Marc Kirchner and Kayur Patel (2022).
   **Neo: Generalizing Confusion Matrix Visualization to Hierarchical and
   Multi-Output Labels**. *CHI ’22*.
   [DOI](https://doi.org/10.1145/3491102.3501823),
   [arXiv 2110.12536v2](https://arxiv.org/abs/2110.12536v2),
   [Apple publication record](https://machinelearning.apple.com/research/generalizing-confusion-matrix),
   [author code repository](https://github.com/apple-aiml-research/ml-hierarchical-confusion-matrix).
   Downloaded PDF: v2, 17 February 2022, thirteen pages. Relevant design:
   §4 normalization/hierarchical labels and §5.4 multilevel visualization.
   Used for visualization design only; no Neo software build or full system
   reproduction is claimed.

## Operational interpretation and source caveats

The Riehl text calls D the descendants of a node. The pinned implementation's
`getDescendants` enumerates immediate graph successors, and `getNeighbors`
enumerates siblings sharing a direct parent. The primary evaluator reproduces
that implementation and the three published tree examples. A separate variant
changes only D to transitive descendants to expose the effect on TN-dependent
metrics; it is explicitly labelled sensitivity, not the primary reference HCM.
The Table 2 FNR numerator typo is not propagated: use FN/(TP+FN).

The downloaded Riehl README examples provide expected TP/TN/FP/FN values. All
7,056 project leaf pairs are checked against the unchanged pinned reference,
in addition to hand-derived small-tree tests. This evidence supports the
tree/single-path/leaf-only scope; it does not validate a generalized DAG or
multilabel evaluator.

The publisher HTML was readable through the verified browser publication
record, but direct local retrieval returned HTTP 403. An attempted Neo author
page URL returned 404; the verified Apple/arXiv publications replaced it.
Both failures are retained in `retrieval.json`. No security restrictions were
modified. Bibliographic fields above come from the verified primary records,
not third-party summaries.

Deployment design sources, consulted 2026-10-25: official
[Flower communication](https://flower.ai/docs/framework/main/en/ref-flower-network-communication.html),
[TLS](https://flower.ai/docs/framework/how-to-enable-tls-connections.html),
[SuperNode authentication](https://flower.ai/docs/framework/how-to-authenticate-supernodes.html),
and [Microsoft WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking).
Online Flower docs describe the current documentation version; the physical
design explicitly requires checking flags against a selected pinned runtime.
