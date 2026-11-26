"""Export measured HCM/family/support tables without fitting or protected-test IO."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/pre_pi_research_v1"
sys.path.insert(0, str(ROOT / "pre_pi_app"))
import pandas as pd
from researchfl.common import CLASSES, FAMILY_OF, dump
from researchfl.evaluation import masks_for_support


def main():
    index = pd.read_csv(OUT / "EXPERIMENT_INDEX.csv")
    hcm_rows, family_rows, structured = [], [], []
    for row in index.itertuples():
        folder = ROOT / row.artifact_dir
        m = json.loads((folder / "metrics.json").read_text())
        contributions = pd.read_csv(folder / "sample_hcm.csv")
        assert contributions.sum().to_dict() == m["hcm_counts"]
        assert m["hcm_counts"]["tp"] + m["hcm_counts"]["fn"] == 11782
        metadata = {"experiment_id": row.experiment_id, "mode": row.mode, "seed": row.seed,
                    "client_id": None if pd.isna(row.client_id) else int(row.client_id),
                    "partition": row.partition, "loss": row.loss, "features": row.features,
                    "phase": row.phase, "samples": m["samples"]}
        hcm_rows.append({**metadata, **{"hcm_" + k: v for k, v in m["hcm_counts"].items()},
                         **{"hcm_" + k: v for k, v in m["hcm_metrics"].items()}})
        structured.append({**metadata, "counts": m["hcm_counts"], "metrics": m["hcm_metrics"],
                           "sample_error_categories": m["hierarchical_errors"]})
        report = pd.read_csv(folder / "family_report.csv", index_col=0)
        families = ["benign"] + sorted(set(FAMILY_OF.values()) - {"benign"})
        for family in families:
            entry = report.loc[family]
            family_rows.append({**metadata, "family": family, "precision": float(entry.precision),
                                "recall": float(entry.recall), "f1": float(entry["f1-score"]),
                                "support": int(entry.support),
                                "status": "observed" if entry.support > 0 else "unsupported_no_validation_samples"})
    pd.DataFrame(hcm_rows).to_csv(OUT / "phase06/hcm_counts_metrics.csv", index=False)
    dump(OUT / "phase06/hcm_counts_metrics.json", {
        "definition": "Unchanged scripts/hcm_eval.py; tree/SPL/mandatory leaf; root excluded; immediate-child/sibling TN",
        "denominator": "Summed node contributions; TP+FN=11782 on the full fixed validation, not 6486",
        "models": structured})
    family = pd.DataFrame(family_rows)
    family.to_csv(OUT / "phase06/all_family_metrics.csv", index=False)
    comparison = family.loc[(family.seed == 42) & family.phase.isin([1, 3, 4]) &
                            ~family.experiment_id.str.startswith(("historical_", "diagnostic_"))]
    comparison.to_csv(OUT / "phase04/per_family_comparison.csv", index=False)
    val = pd.read_csv(ROOT / "data/validation_v1/validation.csv", usecols=["label4"])
    global_training = pd.read_csv(ROOT / "data/validation_v1/train.csv", usecols=["label4"])
    assert set(global_training.label4) == set(CLASSES)
    rows = []
    for client in range(1, 6):
        local = set(pd.read_csv(ROOT / f"data/validation_v1/client_{client}_train.csv", usecols=["label4"]).label4)
        known_families = {FAMILY_OF[s] for s in local} - {"benign"}
        a = set(CLASSES) - {"benign"} - local
        b = {s for s in a if FAMILY_OF[s] not in known_families}
        c = a - b
        masks = masks_for_support(local, val.label4)
        for subset, eligible in zip(masks, [a, b, c]):
            selected = val.loc[masks[subset], "label4"]
            rows.append({"client_id": client, "subset": subset, "training_absent_eligible_subtypes": len(eligible),
                         "validation_observed_subtypes": selected.nunique(), "validation_samples": len(selected),
                         "eligible_subtypes_without_validation_support": len(eligible - set(selected)),
                         "status": "evaluated" if len(selected) else "unsupported_empty_subset"})
    pd.DataFrame(rows).to_csv(OUT / "phase02/client_unseen_support.csv", index=False)
    print(f"Exported {len(hcm_rows)} model HCM records, {len(family_rows)} family rows, {len(rows)} support rows")


if __name__ == "__main__":
    main()
