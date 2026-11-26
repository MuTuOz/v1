
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
    classification_report,
    f1_score,
)

ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "data/fl_clients_v1"
SPLIT_DIR = ROOT / "data/splits_v2"
MODELS = ROOT / "models"
RESULTS = ROOT / "results"

MODELS.mkdir(exist_ok=True)
RESULTS.mkdir(exist_ok=True)

SEED = 42
ROUNDS = 15
LOCAL_EPOCHS = 1
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
CLASS_TO_ID = {name: i for i, name in enumerate(CLASSES)}

reference = pd.read_csv(
    CLIENT_DIR / "client_1_train.csv",
    nrows=1
)

FEATURES = [
    c for c in reference.columns
    if c.startswith(("network_", "log_"))
]

assert len(FEATURES) == 71

# Onceki local MLP ile ayni preprocessing.
def prepare(df):
    values = df[FEATURES].to_numpy(dtype=np.float64)
    values = np.nan_to_num(
        values, nan=0.0, posinf=0.0, neginf=0.0
    )
    values = np.clip(values, -1e8, 1e8)
    values = np.sign(values) * np.log1p(np.abs(values))
    return torch.from_numpy(values.astype(np.float32))


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


# Her client yalnizca kendi dosyasini okur.
clients = []

for client_id in range(1, 6):
    df = pd.read_csv(
        CLIENT_DIR / f"client_{client_id}_train.csv"
    )

    x = prepare(df)
    y = torch.tensor(
        df["label2"].map(CLASS_TO_ID).to_numpy(),
        dtype=torch.long
    )

    clients.append({
        "id": client_id,
        "x": x,
        "y": y,
        "size": len(df),
        "seen": set(df["label2"].unique())
    })

TOTAL = sum(c["size"] for c in clients)

print("\n=== FEDAVG CONFIGURATION ===")
print("Clients:", len(clients))
print("Training records:", TOTAL)
print("Rounds:", ROUNDS)
print("Local epochs per round:", LOCAL_EPOCHS)
print("Features:", len(FEATURES))


# Ortak global model.
global_model = MLP()
criterion = nn.CrossEntropyLoss()

round_history = []

for round_num in range(1, ROUNDS + 1):

    # Her client ayni global agirliklardan baslar.
    global_weights = {
        key: value.detach().clone()
        for key, value in global_model.state_dict().items()
    }

    # Server uzerindeki agirlikli toplam.
    aggregated_weights = {
        key: torch.zeros_like(value)
        for key, value in global_weights.items()
    }

    total_loss = 0.0

    for client in clients:

        local_model = MLP()
        local_model.load_state_dict(global_weights)
        local_model.train()

        optimizer = torch.optim.Adam(
            local_model.parameters(),
            lr=LR
        )

        generator = torch.Generator().manual_seed(
            SEED + round_num * 100 + client["id"]
        )

        loader = DataLoader(
            TensorDataset(client["x"], client["y"]),
            batch_size=BATCH_SIZE,
            shuffle=True,
            generator=generator
        )

        client_loss = 0.0

        for _ in range(LOCAL_EPOCHS):
            for xb, yb in loader:

                optimizer.zero_grad()

                prediction = local_model(xb)
                loss = criterion(prediction, yb)

                loss.backward()
                optimizer.step()

                client_loss += loss.item() * len(xb)

        # FedAvg: veri sayisina gore agirlikli ortalama.
        weight = client["size"] / TOTAL

        for key, value in local_model.state_dict().items():
            aggregated_weights[key].add_(
                value, alpha=weight
            )

        total_loss += (
            client_loss / (LOCAL_EPOCHS * client["size"])
        ) * client["size"]

    # Bir sonraki turun global modeli.
    global_model.load_state_dict(aggregated_weights)

    avg_loss = total_loss / TOTAL

    round_history.append({
        "round": round_num,
        "weighted_train_loss": avg_loss
    })

    print(
        f"Round {round_num:02d}/{ROUNDS} | "
        f"Weighted train loss: {avg_loss:.4f}"
    )


# Yalnizca egitim tamamlandiktan sonra test et.
global_model.eval()

test = pd.read_csv(SPLIT_DIR / "test_episode.csv")
X_test = prepare(test)
y_test = test["label2"].map(CLASS_TO_ID).to_numpy()

with torch.no_grad():
    predictions = global_model(X_test).argmax(dim=1).numpy()

labels_in_test = sorted(np.unique(y_test).tolist())

accuracy = accuracy_score(y_test, predictions)
macro_f1 = f1_score(
    y_test,
    predictions,
    labels=labels_in_test,
    average="macro",
    zero_division=0
)

print("\n=== GLOBAL FEDAVG RESULTS ===")
print("Accuracy:", round(accuracy, 4))
print("Macro F1 (test classes):", round(macro_f1, 4))

print(
    classification_report(
        y_test,
        predictions,
        labels=labels_in_test,
        target_names=[CLASSES[i] for i in labels_in_test],
        zero_division=0
    )
)

# Client bazinda locally unseen basarisi.
rows = []

print("\n=== GLOBAL MODEL: LOCALLY UNSEEN ===")

for client in clients:

    unseen = set(CLASSES) - client["seen"]

    mask = test["label2"].isin(unseen).to_numpy()
    count = int(mask.sum())

    score = (
        accuracy_score(y_test[mask], predictions[mask])
        if count > 0 else None
    )

    rows.append({
        "client_id": client["id"],
        "unseen_test_samples": count,
        "global_unseen_accuracy": score
    })

    print(
        f"Client {client['id']} | "
        f"Unseen samples: {count} | "
        f"Global accuracy: {score:.4f}"
    )


# Web icin ayri, daha zayif tanilama testi.
web = pd.read_csv(
    SPLIT_DIR / "test_web_diagnostic.csv"
)

with torch.no_grad():
    web_pred = global_model(
        prepare(web)
    ).argmax(dim=1).numpy()

web_id = CLASS_TO_ID["web"]
web_recall = float(np.mean(web_pred == web_id))

print("\n=== WEB DIAGNOSTIC ===")
print("Web samples:", len(web))
print("Web recall:", round(web_recall, 4))
print("(Not an independent episode test)")


# Sonuclari sakla.
torch.save(
    {
        "state_dict": global_model.state_dict(),
        "features": FEATURES,
        "classes": CLASSES,
        "preprocessing": "signed_log1p_clip_1e8",
        "rounds": ROUNDS,
        "local_epochs": LOCAL_EPOCHS
    },
    MODELS / "fedavg_mlp_v1.pt"
)

pd.DataFrame(round_history).to_csv(
    RESULTS / "fedavg_v1_rounds.csv",
    index=False
)

pd.DataFrame(rows).to_csv(
    RESULTS / "fedavg_v1_unseen.csv",
    index=False
)

with open(
    RESULTS / "fedavg_v1_metrics.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        {
            "episode_test_accuracy": accuracy,
            "episode_test_macro_f1": macro_f1,
            "web_diagnostic_recall": web_recall,
            "rounds": ROUNDS,
            "local_epochs": LOCAL_EPOCHS
        },
        f,
        indent=2
    )

print("\nFedAvg model and results saved.")
