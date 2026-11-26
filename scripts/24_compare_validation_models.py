
from pathlib import Path
import json

import numpy as np
import pandas as pd
import torch

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_fscore_support,
)

from seniorfl.task import (
    ROOT, MLP, FEATURES, CLASSES,
    CLASS_TO_ID, prepare
)

torch.set_num_threads(4)

VAL_PATH = ROOT / "data/validation_v1/validation.csv"
RESULTS = ROOT / "results"
MODELS = ROOT / "models"

df = pd.read_csv(VAL_PATH)

y_series = df["label2"].map(CLASS_TO_ID)
assert y_series.notna().all()

y_true = y_series.to_numpy(dtype=np.int64)
x = prepare(df)

benign_id = CLASS_TO_ID["benign"]
attack_mask = y_true != benign_id
benign_mask = ~attack_mask

observed = sorted(np.unique(y_true).tolist())

model_paths = {
    "centralized": MODELS / "centralized_mlp_val_v1.pt",
    "flower": MODELS / "flower_fedavg_val_v1.pt",
}

predictions = {}
summary = {}
family_records = []


def predict_model(path):
    checkpoint = torch.load(
        path, map_location="cpu", weights_only=True
    )

    assert checkpoint["features"] == FEATURES
    assert checkpoint["classes"] == CLASSES

    model = MLP()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    with torch.inference_mode():
        outputs = []

        for batch in x.split(512):
            outputs.append(
                model(batch).argmax(1).numpy()
            )

    return np.concatenate(outputs)


for name, path in model_paths.items():
    pred = predict_model(path)
    predictions[name] = pred

    accuracy = accuracy_score(y_true, pred)

    macro_f1 = f1_score(
        y_true,
        pred,
        labels=observed,
        average="macro",
        zero_division=0,
    )

    # Detecting an attack is different from
    # identifying its correct family.
    attack_detection_recall = float(
        np.mean(pred[attack_mask] != benign_id)
    )

    attack_family_accuracy = accuracy_score(
        y_true[attack_mask],
        pred[attack_mask],
    )

    benign_false_positive_rate = float(
        np.mean(pred[benign_mask] != benign_id)
    )

    summary[name] = {
        "accuracy": float(accuracy),
        "macro_f1_observed": float(macro_f1),
        "attack_detection_recall": attack_detection_recall,
        "attack_family_accuracy": float(
            attack_family_accuracy
        ),
        "benign_false_positive_rate":
            benign_false_positive_rate,
        "attacks_predicted_as_benign": int(
            np.sum(attack_mask & (pred == benign_id))
        ),
    }

    precision, recall, f1, support = (
        precision_recall_fscore_support(
            y_true,
            pred,
            labels=list(range(len(CLASSES))),
            zero_division=0,
        )
    )

    for i, family in enumerate(CLASSES):
        mask = y_true == i
        count = int(mask.sum())

        family_records.append({
            "model": name,
            "family": family,
            "support": count,
            "precision": (
                float(precision[i]) if count else np.nan
            ),
            "recall": (
                float(recall[i]) if count else np.nan
            ),
            "f1": (
                float(f1[i]) if count else np.nan
            ),
            "predicted_as_benign": (
                int(np.sum(pred[mask] == benign_id))
                if i != benign_id else 0
            ),
            "predicted_wrong_attack_family": (
                int(np.sum(
                    (pred[mask] != i)
                    & (pred[mask] != benign_id)
                ))
                if i != benign_id else 0
            ),
        })


family_df = pd.DataFrame(family_records)

prediction_df = pd.DataFrame({
    "episode_id": df["episode_id"],
    "true_family": df["label2"],
    "true_subtype": df["label4"],
    "centralized_prediction": [
        CLASSES[i] for i in predictions["centralized"]
    ],
    "flower_prediction": [
        CLASSES[i] for i in predictions["flower"]
    ],
})

family_df.to_csv(
    RESULTS / "validation_v1_family_comparison.csv",
    index=False,
)

prediction_df.to_csv(
    RESULTS / "validation_v1_comparison_predictions.csv",
    index=False,
)

(RESULTS / "validation_v1_comparison_summary.json").write_text(
    json.dumps(summary, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\n=== VALIDATION MODEL COMPARISON ===")

for name, metrics in summary.items():
    print(f"\n{name.upper()}")
    for metric, value in metrics.items():
        if isinstance(value, float):
            print(f"  {metric}: {value:.4f}")
        else:
            print(f"  {metric}: {value}")

print("\n=== ATTACK FAMILY RECALL ===")

recall_table = family_df.pivot(
    index="family",
    columns="model",
    values="recall",
)

print(recall_table.round(4).to_string())

print("\n=== ATTACKS PREDICTED AS BENIGN ===")

missed_table = family_df.pivot(
    index="family",
    columns="model",
    values="predicted_as_benign",
)

print(missed_table.to_string())

print("\nSaved comparison files to:", RESULTS)
