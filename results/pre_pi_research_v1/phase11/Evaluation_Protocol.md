# Frozen evaluation protocol and denominators

All full-set evaluations contain the same 6,486 validation rows: 3,838 benign and
2,648 attacks. The complete training-derived 84-leaf taxonomy is retained.
Validation observes 28 leaves and seven families; web and 56 leaves have no
validation support. Zero-support labels in reports are not successful evaluation.

## Flat levels

Exact subtype accuracy divides matching leaf IDs by the number of selected
rows. Attack-only subtype accuracy restricts that denominator to true attacks.
Family predictions are the frozen family mapping of the predicted subtype.
Family accuracy uses the same selected rows, including benign on the full set.
Detection recall is true attacks predicted as any attack / true attacks.
Benign FPR is true benign predicted as any attack / true benign; it is undefined
on the attack-only unseen subsets. Precision, recall and F1 per class use the
usual one-vs-rest counts, including wrong predictions into/out of that class.

Primary subtype Macro F1 averages the true observed labels of the selected
subset with `zero_division=0`. Family Macro F1 similarly averages observed true
families. False-positive predictions of absent labels still contribute false
negatives to observed true labels, but absent labels are excluded from that
particular macro mean. Per-class reports also retain all 84/8/2 labels, whose
report macro rows therefore have a different denominator. Attack-only Macro F1
excludes true benign rows, so it does not penalize false attacks on benign rows.
All-empty subsets have null rates, not invented zeros or perfect scores.

## Formal Riehl HCM (unchanged implementation)

For one true root-to-leaf path T and predicted path P, let R be the root, C their
longest shared prefix and z the last node of C. N(v) is the sibling set of v
(empty for root). D1(z) is the set of immediate children. The pinned author's
operational convention, implemented in `scripts/hcm_eval.py`, is:

```text
TP_H = |(T intersection P) minus {R}|
FP_H = |P minus T|
FN_H = |T minus P|
TN_H = |(union over v in C of N(v)) minus T|
       + |D1(z) minus (T union P)|
```

The paper uses the word descendants; the pinned implementation enumerates
immediate children for D1 and siblings for N. We preserve that convention.
The previous formal_hcm_v1 transitive-TN sensitivity analysis remains separate;
no new definition is introduced. Trees/single paths/mandatory leaf predictions
are supported; DAG, multilabel and internal-node predictions are outside scope.

Counts sum over records before micro metrics are calculated:

```text
precision = TP/(TP+FP)                recall = TP/(TP+FN)
F1 = 2TP/(2TP+FP+FN)                 accuracy = (TP+TN)/(TP+TN+FP+FN)
specificity = TN/(TN+FP)             HCM FPR = FP/(FP+TN)
FNR = FN/(TP+FN)
MCC = (TP*TN-FP*FN)/sqrt((TP+FP)(TP+FN)(TN+FP)(TN+FN))
```

Zero denominators give null. The HCM matrix is `[[TP,FN],[FP,TN]]`, consisting
of node contributions, not rows. Root is excluded from TP. Benign has depth one;
an attack leaf has depth three. Thus full-set TP+FN must be
3,838 + 3×2,648 = **11,782** for every model, while the matrix total need not equal
6,486. HCM FPR is not the operational benign FPR. Unobserved training classes
remain in the tree for TN, without implying validation coverage.

The separate five disjoint sample categories are exact correct, correct attack
family/wrong subtype, wrong attack family, attack→benign and benign→attack.
Their counts must sum to the selected sample count, 6,486 on the full set.
They are not formal HCM counts.

## Client-relative support and uncertainty

For each original client, A is globally trained attack subtypes absent from
that client's training labels; B is entirely absent attack families; C is absent
subtypes inside locally observed attack families. A is the disjoint union of B
and C. Masks depend only on frozen training support and true validation labels,
never predictions. All model comparisons for a client use exactly that mask.
Globally absent training labels are a separate category (none in this taxonomy).
Balanced/exclusive reallocations define new supports and therefore new masks.

The three predefined seeds are 42, 52 and 62; standard deviation uses ddof=1.
These repeats quantify training randomness on one split. Overlapping client
subsets and correlated five-second rows are not independent sessions. No row-IID
confidence interval or statistical-significance claim is made. Repeated use of
validation makes the intervention comparisons exploratory.
