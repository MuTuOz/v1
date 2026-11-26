
from pathlib import Path
import json
import random

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report
)

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "data/splits_v2"
RESULTS = ROOT / "results"
MODELS = ROOT / "models"

RESULTS.mkdir(exist_ok=True)
MODELS.mkdir(exist_ok=True)

SEED = 42
EPOCHS = 15
BATCH_SIZE = 128
LR = 0.001

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.set_num_threads(min(4, torch.get_num_threads()))

train = pd.read_csv(SPLITS / "train.csv")
test = pd.read_csv(SPLITS / "test_episode.csv")

FEATURES = [
    c for c in train.columns
    if c.startswith(("network_", "log_"))
]

assert len(FEATURES) == 71


def prepare(df):
    x = df[FEATURES].to_numpy(dtype=np.float64)
    x = np.nan_to_num(
        x, nan=0.0, posinf=0.0, neginf=0.0
    )
    x = np.clip(x, -1e8, 1e8)
    x = np.sign(x) * np.log1p(np.abs(x))
    return torch.from_numpy(x.astype(np.float32))


def get_target(df):
    y = df["label4"].astype("string").str.strip()
    y.loc[df["label2"] == "benign"] = "benign"

    assert y.notna().all()
    assert (y != "").all()

    return y.astype(str).to_numpy()


train_labels = get_target(train)
test_labels = get_target(test)

attack_classes = sorted(
    set(train_labels) - {"benign"}
)

CLASSES = ["benign"] + attack_classes
CLASS_TO_ID = {
    name: i for i, name in enumerate(CLASSES)
}

assert len(attack_classes) == 83
assert set(test_labels).issubset(set(CLASSES))
assert "benign" not in set(
    train_labels[train["label2"] != "benign"]
)

# Parent mapping must come only from training data.
mapping_df = pd.DataFrame({
    "subtype": train_labels,
    "family": train["label2"].astype(str).to_numpy()
})

parent_counts = (
    mapping_df.groupby("subtype")["family"].nunique()
)

assert (parent_counts == 1).all()

FAMILY_OF = (
    mapping_df.drop_duplicates("subtype")
    .set_index("subtype")["family"]
    .to_dict()
)

assert all(
    FAMILY_OF[label] == family
    for label, family in zip(
        test_labels, test["label2"].astype(str)
    )
)

X_train = prepare(train)
X_test = prepare(test)

y_train = torch.tensor(
    [CLASS_TO_ID[x] for x in train_labels],
    dtype=torch.long
)
y_test = np.array(
    [CLASS_TO_ID[x] for x in test_labels]
)


class MLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(71, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, len(CLASSES))
        )

    def forward(self, x):
        return self.net(x)


model = MLP()
optimizer = torch.optim.Adam(model.parameters(), lr=LR)
criterion = nn.CrossEntropyLoss()

generator = torch.Generator().manual_seed(SEED)

loader = DataLoader(
    TensorDataset(X_train, y_train),
    batch_size=BATCH_SIZE,
    shuffle=True,
    generator=generator
)

print("\n=== SUBTYPE MLP CONFIGURATION ===")
print("Training records:", len(train))
print("Test records:", len(test))
print("Output classes:", len(CLASSES))
print("Train attack subtypes:", len(attack_classes))
print("Test attack subtypes:",
      len(set(test_labels) - {"benign"}))

history = []

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

    avg_loss = total_loss / len(train)
    history.append({
        "epoch": epoch,
        "train_loss": avg_loss
    })

    print(
        f"Epoch {epoch:02d}/{EPOCHS} | "
        f"Train loss: {avg_loss:.4f}"
    )


# Evaluate only after training.
model.eval()
with torch.no_grad():
    pred_ids = model(X_test).argmax(1).numpy()

pred_labels = np.array(
    [CLASSES[i] for i in pred_ids]
)

true_families = test["label2"].astype(str).to_numpy()
pred_families = np.array([
    FAMILY_OF[label] for label in pred_labels
])

tested_ids = sorted(set(y_test.tolist()))
tested_names = [CLASSES[i] for i in tested_ids]

subtype_accuracy = accuracy_score(y_test, pred_ids)
subtype_macro_f1 = f1_score(
    y_test, pred_ids,
    labels=tested_ids,
    average="macro",
    zero_division=0
)

family_accuracy = accuracy_score(
    true_families, pred_families
)

family_macro_f1 = f1_score(
    true_families,
    pred_families,
    labels=sorted(set(true_families)),
    average="macro",
    zero_division=0
)

within_family_errors = int(np.sum(
    (true_families == pred_families)
    & (test_labels != pred_labels)
))

attack_to_benign = int(np.sum(
    (true_families != "benign")
    & (pred_families == "benign")
))

benign_to_attack = int(np.sum(
    (true_families == "benign")
    & (pred_families != "benign")
))

cross_attack_family = int(np.sum(
    (true_families != "benign")
    & (pred_families != "benign")
    & (true_families != pred_families)
))

print("\n=== SUBTYPE RESULTS ===")
print("Exact subtype accuracy:", round(subtype_accuracy, 4))
print("Macro F1 (tested classes):",
      round(subtype_macro_f1, 4))
print("Family accuracy:", round(family_accuracy, 4))
print("Family Macro F1:", round(family_macro_f1, 4))

print("\n=== HIERARCHICAL ERROR BREAKDOWN ===")
print("Correct family, wrong subtype:",
      within_family_errors)
print("Attack predicted benign:", attack_to_benign)
print("Benign predicted attack:", benign_to_attack)
print("Wrong attack family:", cross_attack_family)

report = classification_report(
    y_test,
    pred_ids,
    labels=tested_ids,
    target_names=tested_names,
    output_dict=True,
    zero_division=0
)

pd.DataFrame(history).to_csv(
    RESULTS / "subtype_centralized_epochs.csv",
    index=False
)

pd.DataFrame(report).T.to_csv(
    RESULTS / "subtype_centralized_report.csv"
)

predictions = pd.DataFrame({
    "true_family": true_families,
    "pred_family": pred_families,
    "true_subtype": test_labels,
    "pred_subtype": pred_labels
})

if "label3" in test.columns:
    predictions["true_label3"] = test["label3"].values

predictions.to_csv(
    RESULTS / "subtype_centralized_predictions.csv",
    index=False
)

torch.save({
    "state_dict": model.state_dict(),
    "features": FEATURES,
    "classes": CLASSES,
    "family_of": FAMILY_OF,
    "preprocessing": "signed_log1p_clip_1e8",
    "epochs": EPOCHS
}, MODELS / "subtype_centralized_mlp.pt")

metrics = {
    "subtype_accuracy": subtype_accuracy,
    "subtype_macro_f1": subtype_macro_f1,
    "family_accuracy": family_accuracy,
    "family_macro_f1": family_macro_f1,
    "within_family_errors": within_family_errors,
    "attack_to_benign": attack_to_benign,
    "benign_to_attack": benign_to_attack,
    "cross_attack_family": cross_attack_family,
    "tested_classes": len(tested_ids)
}

with open(
    RESULTS / "subtype_centralized_metrics.json",
    "w", encoding="utf-8"
) as f:
    json.dump(metrics, f, indent=2)

print("\nSubtype model and results saved.")
