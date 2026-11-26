
from pathlib import Path
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

from seniorfl.task import (
    ROOT, MLP, FEATURES, CLASSES,
    CLASS_TO_ID, prepare
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

def make_labels(df):
    labels = df["label2"].map(CLASS_TO_ID)
    assert labels.notna().all(), "Unknown class labels"
    return torch.tensor(
        labels.to_numpy(dtype=np.int64),
        dtype=torch.long
    )

x_train = prepare(train_df)
y_train = make_labels(train_df)

x_val = prepare(val_df)
y_val = make_labels(val_df)

assert x_train.shape[1] == 71

loader = DataLoader(
    TensorDataset(x_train, y_train),
    batch_size=BATCH_SIZE,
    shuffle=True,
    generator=torch.Generator().manual_seed(SEED),
)

model = MLP()
optimizer = torch.optim.Adam(
    model.parameters(), lr=LR
)
criterion = nn.CrossEntropyLoss()

epoch_records = []

print("\n=== CENTRALIZED MLP VALIDATION V1 ===")
print("Training samples:", len(train_df))
print("Validation samples:", len(val_df))
print("Features:", len(FEATURES))
print("Model parameters:", sum(
    p.numel() for p in model.parameters()
))

# TRAINING
for epoch in range(1, EPOCHS + 1):
    model.train()
    loss_sum = 0.0

    for xb, yb in loader:
        optimizer.zero_grad()

        outputs = model(xb)
        loss = criterion(outputs, yb)

        loss.backward()
        optimizer.step()

        loss_sum += loss.item() * len(xb)

    avg_loss = loss_sum / len(train_df)

    epoch_records.append({
        "epoch": epoch,
        "train_loss": float(avg_loss)
    })

    print(
        f"Epoch {epoch:02d}/{EPOCHS} "
        f"| Train Loss: {avg_loss:.4f}",
        flush=True
    )

# VALIDATION — No episode test access
model.eval()

with torch.no_grad():
    logits = model(x_val)
    predictions = logits.argmax(dim=1).numpy()

y_true = y_val.numpy()

labels_all = list(range(len(CLASSES)))
labels_observed = sorted(np.unique(y_true).tolist())

accuracy = accuracy_score(y_true, predictions)

macro_observed = f1_score(
    y_true, predictions,
    labels=labels_observed,
    average="macro",
    zero_division=0
)

macro_all = f1_score(
    y_true, predictions,
    labels=labels_all,
    average="macro",
    zero_division=0
)

report = classification_report(
    y_true, predictions,
    labels=labels_all,
    target_names=CLASSES,
    output_dict=True,
    zero_division=0
)

cm = confusion_matrix(
    y_true, predictions,
    labels=labels_all
)

# SAVE MODEL
model_path = (
    models_dir / "centralized_mlp_val_v1.pt"
)

torch.save({
    "state_dict": model.state_dict(),
    "features": FEATURES,
    "classes": CLASSES,
    "epochs": EPOCHS,
    "seed": SEED,
    "training_split": "validation_v1/train",
    "preprocessing": "signed_log1p_clip_1e8"
}, model_path)

# SAVE METRICS
metrics = {
    "experiment": "centralized_mlp_val_v1",
    "training_records": len(train_df),
    "validation_records": len(val_df),
    "validation_accuracy": float(accuracy),
    "validation_macro_f1_observed": float(macro_observed),
    "validation_macro_f1_all_8": float(macro_all),
    "epochs": EPOCHS,
    "batch_size": BATCH_SIZE,
    "learning_rate": LR,
    "model_parameters": sum(
        p.numel() for p in model.parameters()
    ),
    "seed": SEED
}

(results_dir / "centralized_mlp_val_v1_metrics.json").write_text(
    json.dumps(metrics, indent=2),
    encoding="utf-8"
)

pd.DataFrame(epoch_records).to_csv(
    results_dir / "centralized_mlp_val_v1_epochs.csv",
    index=False
)

pd.DataFrame(report).T.to_csv(
    results_dir / "centralized_mlp_val_v1_report.csv"
)

pd.DataFrame(
    cm, index=CLASSES, columns=CLASSES
).to_csv(
    results_dir / "centralized_mlp_val_v1_confusion.csv"
)

pd.DataFrame({
    "true_family": [CLASSES[i] for i in y_true],
    "predicted_family": [
        CLASSES[i] for i in predictions
    ],
    "true_subtype": val_df["label4"].values,
    "episode_id": val_df["episode_id"].values,
}).to_csv(
    results_dir / "centralized_mlp_val_v1_predictions.csv",
    index=False
)

print("\n=== CENTRALIZED VALIDATION RESULTS ===")
print("Accuracy:", round(accuracy, 4))
print("Macro F1 (observed):", round(macro_observed, 4))
print("Macro F1 (all 8):", round(macro_all, 4))

# COMPARE AGAINST FLOWER
flower_path = (
    results_dir / "flower_fedavg_val_v1_metrics.json"
)

if flower_path.exists():
    flower = json.loads(
        flower_path.read_text(encoding="utf-8")
    )

    print("\n=== CENTRALIZED vs FLOWER ===")
    print(
        f"{'Metric':<23} {'Centralized':>12} {'Flower':>12}"
    )
    print(
        f"{'Accuracy':<23} "
        f"{accuracy:>12.4f} "
        f"{flower['validation_accuracy']:>12.4f}"
    )
    print(
        f"{'Macro F1 (observed)':<23} "
        f"{macro_observed:>12.4f} "
        f"{flower['validation_macro_f1_observed']:>12.4f}"
    )

print("\nSaved model:", model_path)
print("Saved metrics and reports to:", results_dir)
