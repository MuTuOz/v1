
from pathlib import Path
from collections import Counter
import json
import random

import numpy as np
import pandas as pd
import torch

from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
)

ROOT = Path(__file__).resolve().parents[1]
SPLIT_DIR = ROOT / "data/splits_v2"
CLIENT_DIR = ROOT / "data/fl_clients_v1"
MODELS = ROOT / "models"
RESULTS = ROOT / "results"

MODELS.mkdir(exist_ok=True)
RESULTS.mkdir(exist_ok=True)

SEED = 42
EPOCHS = 15
BATCH_SIZE = 128
LR = 0.001

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.set_num_threads(min(4, torch.get_num_threads()))

CLASSES = [
    "benign", "bruteforce", "ddos", "dos",
    "malware", "mitm", "recon", "web"
]

CLASS_TO_ID = {
    name: i for i, name in enumerate(CLASSES)
}

reference = pd.read_csv(
    CLIENT_DIR / "client_1_train.csv",
    nrows=1
)

FEATURES = [
    c for c in reference.columns
    if c.startswith(("network_", "log_"))
]

assert len(FEATURES) == 71


# FedAvg ile birebir ayni preprocessing.
def prepare(df):
    values = df[FEATURES].to_numpy(dtype=np.float64)

    values = np.nan_to_num(
        values, nan=0.0, posinf=0.0, neginf=0.0
    )

    values = np.clip(values, -1e8, 1e8)
    values = np.sign(values) * np.log1p(np.abs(values))

    return torch.from_numpy(
        values.astype(np.float32)
    )


class MLP(nn.Module):
    def __init__(self):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(71, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 8)
        )

    def forward(self, x):
        return self.net(x)


# Centralized training verisi.
train = pd.read_csv(SPLIT_DIR / "train.csv")

X_train = prepare(train)

y_train_np = (
    train["label2"].map(CLASS_TO_ID).to_numpy()
)

assert not pd.isna(y_train_np).any()

y_train = torch.tensor(
    y_train_np.astype(np.int64),
    dtype=torch.long
)


# Client verilerinin merkezi train ile ayni
# model girdilerini kapsadigini kontrol et.
def row_fingerprints(df):
    data = pd.DataFrame(prepare(df).numpy())

    data[71] = (
        df["label2"]
        .map(CLASS_TO_ID)
        .to_numpy(dtype=np.int64)
    )

    hashes = pd.util.hash_pandas_object(
        data, index=False
    )

    return Counter(hashes.to_numpy().tolist())


client_frames = []
client_seen = {}

for client_id in range(1, 6):
    df = pd.read_csv(
        CLIENT_DIR / f"client_{client_id}_train.csv"
    )

    client_frames.append(df)
    client_seen[client_id] = set(
        df["label2"].unique()
    )

client_combined = pd.concat(
    client_frames, ignore_index=True
)

assert len(client_combined) == len(train), (
    "Client ve centralized veri sayilari farkli."
)

assert (
    row_fingerprints(client_combined)
    == row_fingerprints(train)
), "Client ve centralized model girdileri eslesmiyor."

print("\nTraining pool check: PASSED")


print("\n=== CENTRALIZED MLP CONFIGURATION ===")
print("Training records:", len(train))
print("Epochs:", EPOCHS)
print("Features:", len(FEATURES))
print("Batch size:", BATCH_SIZE)
print("Learning rate:", LR)


# Ayni MLP, ayni loss ve optimizer.
model = MLP()

criterion = nn.CrossEntropyLoss()

optimizer = torch.optim.Adam(
    model.parameters(),
    lr=LR
)

generator = torch.Generator().manual_seed(SEED)

loader = DataLoader(
    TensorDataset(X_train, y_train),
    batch_size=BATCH_SIZE,
    shuffle=True,
    generator=generator
)


# Centralized training.
epoch_history = []

for epoch in range(1, EPOCHS + 1):
    model.train()

    total_loss = 0.0

    for xb, yb in loader:
        optimizer.zero_grad()

        prediction = model(xb)
        loss = criterion(prediction, yb)

        loss.backward()
        optimizer.step()

        total_loss += loss.item() * len(xb)

    avg_loss = total_loss / len(train)

    epoch_history.append({
        "epoch": epoch,
        "train_loss": avg_loss
    })

    print(
        f"Epoch {epoch:02d}/{EPOCHS} | "
        f"Train loss: {avg_loss:.4f}"
    )


# Test verisini yalnizca egitimden sonra kullan.
model.eval()

test = pd.read_csv(
    SPLIT_DIR / "test_episode.csv"
)

X_test = prepare(test)

y_test = (
    test["label2"]
    .map(CLASS_TO_ID)
    .to_numpy()
)

with torch.no_grad():
    predictions = (
        model(X_test)
        .argmax(dim=1)
        .numpy()
    )

labels_in_test = sorted(
    np.unique(y_test).tolist()
)

accuracy = accuracy_score(
    y_test, predictions
)

macro_f1 = f1_score(
    y_test,
    predictions,
    labels=labels_in_test,
    average="macro",
    zero_division=0
)

print("\n=== CENTRALIZED MLP RESULTS ===")
print("Accuracy:", round(accuracy, 4))
print("Macro F1 (test classes):", round(macro_f1, 4))

print(
    classification_report(
        y_test,
        predictions,
        labels=labels_in_test,
        target_names=[
            CLASSES[i] for i in labels_in_test
        ],
        zero_division=0
    )
)


# Client bazinda locally unseen degerlendirmesi.
unseen_rows = []

print("\n=== CENTRALIZED: LOCALLY UNSEEN ===")

for client_id in range(1, 6):
    unseen = set(CLASSES) - client_seen[client_id]

    mask = test["label2"].isin(
        unseen
    ).to_numpy()

    count = int(mask.sum())

    score = (
        accuracy_score(
            y_test[mask],
            predictions[mask]
        )
        if count > 0 else None
    )

    unseen_rows.append({
        "client_id": client_id,
        "unseen_test_samples": count,
        "centralized_unseen_accuracy": score
    })

    print(
        f"Client {client_id} | "
        f"Unseen samples: {count} | "
        f"Centralized accuracy: "
        f"{score:.4f}" if score is not None
        else f"Client {client_id} | No unseen samples"
    )


# Web diagnostic: ayri ve sinirli test.
web = pd.read_csv(
    SPLIT_DIR / "test_web_diagnostic.csv"
)

with torch.no_grad():
    web_predictions = (
        model(prepare(web))
        .argmax(dim=1)
        .numpy()
    )

web_recall = float(
    np.mean(web_predictions == CLASS_TO_ID["web"])
)

print("\n=== WEB DIAGNOSTIC ===")
print("Web samples:", len(web))
print("Web recall:", round(web_recall, 4))
print("(Not an independent episode test)")


# Modeli kaydet.
torch.save(
    {
        "state_dict": model.state_dict(),
        "features": FEATURES,
        "classes": CLASSES,
        "preprocessing": "signed_log1p_clip_1e8",
        "epochs": EPOCHS
    },
    MODELS / "centralized_mlp_v1.pt"
)


# Egitim gecmisi.
pd.DataFrame(epoch_history).to_csv(
    RESULTS / "centralized_mlp_v1_epochs.csv",
    index=False
)


# Client bazli test sonuclari.
pd.DataFrame(unseen_rows).to_csv(
    RESULTS / "centralized_mlp_v1_unseen.csv",
    index=False
)


# Daha sonra hiyerarsik analizde kullanilacak
# gercek ve tahmin edilen aile etiketleri.
prediction_data = pd.DataFrame({
    "true_family": [
        CLASSES[i] for i in y_test
    ],
    "pred_family": [
        CLASSES[i] for i in predictions
    ]
})

for column in ["label3", "label4"]:
    if column in test.columns:
        prediction_data[column] = test[column].values

prediction_data.to_csv(
    RESULTS / "centralized_mlp_v1_predictions.csv",
    index=False
)


# Metrikleri JSON olarak kaydet.
with open(
    RESULTS / "centralized_mlp_v1_metrics.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        {
            "episode_test_accuracy": float(accuracy),
            "episode_test_macro_f1": float(macro_f1),
            "web_diagnostic_recall": web_recall,
            "epochs": EPOCHS,
            "training_records": len(train)
        },
        f,
        indent=2
    )

print("\nCentralized model and results saved.")
