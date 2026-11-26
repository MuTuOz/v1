
import json

import numpy as np
import pandas as pd
import torch

from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
)

from seniorfl.task import ROOT, FEATURES, prepare
from seniorfl.subtype_task import (
    SubtypeMLP,
    CLASSES,
    CLASS_TO_ID,
    FAMILY_OF,
    make_labels,
)

SEED = 42
EPOCHS = 15
BATCH_SIZE = 128
LR = 0.001

torch.manual_seed(SEED)
np.random.seed(SEED)
torch.set_num_threads(4)

data_dir = ROOT / "data" / "validation_v1"
results_dir = ROOT / "results"
models_dir = ROOT / "models"

train_df = pd.read_csv(data_dir / "train.csv")
val_df = pd.read_csv(data_dir / "validation.csv")

assert len(train_df) == 22450
assert len(val_df) == 6486

x_train = prepare(train_df)
y_train = make_labels(train_df)

x_val = prepare(val_df)
y_val = make_labels(val_df)

loader = DataLoader(
    TensorDataset(x_train, y_train),
    batch_size=BATCH_SIZE,
    shuffle=True,
    generator=torch.Generator().manual_seed(SEED),
)

model = SubtypeMLP()
optimizer = torch.optim.Adam(
    model.parameters(), lr=LR
)
criterion = nn.CrossEntropyLoss()

print("\n=== CENTRALIZED SUBTYPE TRAINING ===")
print("Training:", len(train_df))
print("Validation:", len(val_df))
print("Features:", len(FEATURES))
print("Classes:", len(CLASSES))
print("Parameters:", sum(
    p.numel() for p in model.parameters()
))

epoch_records = []

# Training
for epoch in range(1, EPOCHS + 1):
    model.train()
    total_loss = 0.0

    for xb, yb in loader:
        optimizer.zero_grad()

        logits = model(xb)
        loss = criterion(logits, yb)

        loss.backward()
        optimizer.step()

        total_loss += loss.item() * len(xb)

    average_loss = total_loss / len(train_df)

    epoch_records.append({
        "epoch": epoch,
        "train_loss": float(average_loss)
    })

    print(
        f"Epoch {epoch:02d}/{EPOCHS} | "
        f"Loss: {average_loss:.4f}",
        flush=True
    )

# Validation (NOT episode test)
model.eval()

with torch.inference_mode():
    prediction_batches = []

    for batch in x_val.split(512):
        prediction_batches.append(
            model(batch).argmax(dim=1).numpy()
        )

    y_pred = np.concatenate(prediction_batches)

y_true = y_val.numpy()

true_subtypes = np.array([
    CLASSES[i] for i in y_true
])
pred_subtypes = np.array([
    CLASSES[i] for i in y_pred
])

true_families = val_df["label2"].to_numpy()
pred_families = np.array([
    FAMILY_OF[label] for label in pred_subtypes
])

attack_mask = true_families != "benign"
benign_mask = ~attack_mask

observed_subtype_ids = sorted(
    np.unique(y_true).tolist()
)

observed_attack_ids = [
    i for i in observed_subtype_ids
    if CLASSES[i] != "benign"
]

observed_families = sorted(
    np.unique(true_families).tolist()
)

# Level 3: Exact subtype
subtype_accuracy = accuracy_score(
    y_true, y_pred
)

subtype_macro_f1 = f1_score(
    y_true, y_pred,
    labels=observed_subtype_ids,
    average="macro",
    zero_division=0
)

attack_subtype_accuracy = accuracy_score(
    y_true[attack_mask],
    y_pred[attack_mask]
)

attack_subtype_macro_f1 = f1_score(
    y_true[attack_mask],
    y_pred[attack_mask],
    labels=observed_attack_ids,
    average="macro",
    zero_division=0
)

# Level 2: Family derived from subtype
family_accuracy = accuracy_score(
    true_families, pred_families
)

family_macro_f1 = f1_score(
    true_families, pred_families,
    labels=observed_families,
    average="macro",
    zero_division=0
)

# Level 1: Attack detection
attack_detection_recall = float(
    np.mean(pred_families[attack_mask] != "benign")
)

benign_false_positive_rate = float(
    np.mean(pred_families[benign_mask] != "benign")
)

# Hierarchical error categories
exact_correct = (
    true_subtypes == pred_subtypes
)

correct_family_wrong_subtype = (
    attack_mask
    & ~exact_correct
    & (true_families == pred_families)
)

attack_as_benign = (
    attack_mask
    & (pred_families == "benign")
)

benign_as_attack = (
    benign_mask
    & (pred_families != "benign")
)

wrong_attack_family = (
    attack_mask
    & (pred_families != "benign")
    & (true_families != pred_families)
)

breakdown = {
    "exact_correct": int(exact_correct.sum()),
    "correct_family_wrong_subtype": int(
        correct_family_wrong_subtype.sum()
    ),
    "attack_predicted_benign": int(
        attack_as_benign.sum()
    ),
    "benign_predicted_attack": int(
        benign_as_attack.sum()
    ),
    "wrong_attack_family": int(
        wrong_attack_family.sum()
    ),
}

assert sum(breakdown.values()) == len(val_df)

metrics = {
    "experiment": "subtype_centralized_val_v1",
    "training_samples": len(train_df),
    "validation_samples": len(val_df),
    "num_classes": len(CLASSES),
    "num_observed_validation_classes": len(
        observed_subtype_ids
    ),
    "exact_subtype_accuracy": float(subtype_accuracy),
    "subtype_macro_f1_observed": float(
        subtype_macro_f1
    ),
    "attack_only_subtype_accuracy": float(
        attack_subtype_accuracy
    ),
    "attack_only_subtype_macro_f1": float(
        attack_subtype_macro_f1
    ),
    "family_accuracy": float(family_accuracy),
    "family_macro_f1_observed": float(
        family_macro_f1
    ),
    "attack_detection_recall": (
        attack_detection_recall
    ),
    "benign_false_positive_rate": (
        benign_false_positive_rate
    ),
    "hierarchical_error_breakdown": breakdown,
    "epochs": EPOCHS,
    "batch_size": BATCH_SIZE,
    "learning_rate": LR,
    "seed": SEED,
}

models_dir.mkdir(parents=True, exist_ok=True)
results_dir.mkdir(parents=True, exist_ok=True)

torch.save({
    "state_dict": model.state_dict(),
    "classes": CLASSES,
    "features": FEATURES,
    "family_of": FAMILY_OF,
    "preprocessing": "signed_log1p_clip_1e8",
    "epochs": EPOCHS,
    "seed": SEED,
    "split": "validation_v1",
}, models_dir / "subtype_centralized_val_v1.pt")

(results_dir / "subtype_centralized_val_v1_metrics.json").write_text(
    json.dumps(metrics, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

pd.DataFrame(epoch_records).to_csv(
    results_dir / "subtype_centralized_val_v1_epochs.csv",
    index=False
)

pd.DataFrame(
    classification_report(
        y_true, y_pred,
        labels=list(range(len(CLASSES))),
        target_names=CLASSES,
        output_dict=True,
        zero_division=0
    )
).T.to_csv(
    results_dir / "subtype_centralized_val_v1_report.csv"
)

pd.DataFrame(
    confusion_matrix(
        y_true, y_pred,
        labels=list(range(len(CLASSES)))
    ),
    index=CLASSES,
    columns=CLASSES
).to_csv(
    results_dir / "subtype_centralized_val_v1_confusion.csv"
)

pd.DataFrame({
    "true_subtype": true_subtypes,
    "predicted_subtype": pred_subtypes,
    "true_family": true_families,
    "predicted_family": pred_families,
    "episode_id": val_df["episode_id"].values,
}).to_csv(
    results_dir / "subtype_centralized_val_v1_predictions.csv",
    index=False
)

print("\n=== CENTRALIZED SUBTYPE VALIDATION ===")
print(f"Exact Subtype Accuracy: {subtype_accuracy:.4f}")
print(f"Subtype Macro F1: {subtype_macro_f1:.4f}")
print(
    f"Attack-only Subtype Accuracy: "
    f"{attack_subtype_accuracy:.4f}"
)
print(f"Family Accuracy: {family_accuracy:.4f}")
print(f"Family Macro F1: {family_macro_f1:.4f}")
print(
    f"Attack Detection Recall: "
    f"{attack_detection_recall:.4f}"
)

print("\n=== HIERARCHICAL ERRORS ===")
for key, value in breakdown.items():
    print(f"{key}: {value}")

print("\nSaved model and reports.")
