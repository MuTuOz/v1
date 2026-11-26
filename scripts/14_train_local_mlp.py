import sys
from pathlib import Path
import random
import numpy as np
import pandas as pd
import torch


from torch import nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.metrics import classification_report, accuracy_score

ROOT = Path(__file__).resolve().parents[1]

CLIENT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1

if CLIENT_ID not in range(1, 6):
    raise ValueError("Client ID 1 ile 5 arasinda olmali.")

TRAIN_PATH = ROOT / f"data/fl_clients_v1/client_{CLIENT_ID}_train.csv"
TEST_PATH = ROOT / "data/splits_v2/test_episode.csv"
OUTPUT = ROOT / f"models/local_mlp_client{CLIENT_ID}.pt"

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

CLASSES = [
    "benign", "bruteforce", "ddos", "dos",
    "malware", "mitm", "recon", "web"
]

class_to_id = {name: i for i, name in enumerate(CLASSES)}

train = pd.read_csv(TRAIN_PATH)
test = pd.read_csv(TEST_PATH)

features = [
    c for c in train.select_dtypes(include="number").columns
    if c.startswith(("network_", "log_"))
]

assert len(features) == 71

# Her client icin ayni sabit donusum.
# Global egitim verisinden scaler ogrenmiyoruz.
def prepare_features(df):
    values = df[features].to_numpy(dtype=np.float64)
    values = np.nan_to_num(
        values, nan=0.0, posinf=0.0, neginf=0.0
    )
    values = np.clip(values, -1e8, 1e8)

    # Buyuk sayilari sikistir, isaretini koru.
    values = np.sign(values) * np.log1p(np.abs(values))
    return values.astype(np.float32)

X_train = torch.from_numpy(prepare_features(train))
y_train = torch.tensor(
    train["label2"].map(class_to_id).to_numpy(),
    dtype=torch.long
)

X_test = torch.from_numpy(prepare_features(test))
y_test = test["label2"].map(class_to_id).to_numpy()

loader = DataLoader(
    TensorDataset(X_train, y_train),
    batch_size=128,
    shuffle=True
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

model = MLP()
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
criterion = nn.CrossEntropyLoss()

print("\n=== LOCAL CLIENT 1 TRAINING ===")
print("Training samples:", len(train))
print("Test samples:", len(test))
print("Local classes:", sorted(train["label2"].unique()))

# Ilk deneme: 15 epoch
for epoch in range(15):
    model.train()
    running_loss = 0.0

    for xb, yb in loader:
        optimizer.zero_grad()

        output = model(xb)
        loss = criterion(output, yb)

        loss.backward()
        optimizer.step()

        running_loss += loss.item() * len(xb)

    print(
        f"Epoch {epoch+1:02d}/15 | "
        f"Loss: {running_loss / len(train):.4f}"
    )

# Ortak testte degerlendir.
model.eval()

with torch.no_grad():
    logits = model(X_test)
    predictions = logits.argmax(dim=1).numpy()

print("\n=== LOCAL MODEL PERFORMANCE ===")
print(
    classification_report(
        y_test,
        predictions,
        labels=sorted(np.unique(y_test).tolist()),
        target_names=[
        CLASSES[i] for i in sorted(np.unique(y_test).tolist())
        ],
        zero_division=0
    )
)

# Client 1'in gordugu/gormedigi siniflar
seen = set(train["label2"].unique())

seen_mask = test["label2"].isin(seen).to_numpy()
unseen_mask = ~seen_mask

print("\n=== SEEN vs LOCALLY UNSEEN ===")
print("Seen samples:", seen_mask.sum())
print("Unseen samples:", unseen_mask.sum())

for name, mask in [
    ("Seen", seen_mask),
    ("Locally unseen", unseen_mask)
]:
    if mask.sum() > 0:
        score = accuracy_score(
            y_test[mask],
            predictions[mask]
        )
        print(f"{name} accuracy: {score:.4f}")

# Modeli kaydet
torch.save(
    {
        "state_dict": model.state_dict(),
        "features": features,
        "classes": CLASSES,
        "preprocessing": "signed_log1p_clip_1e8"
    },
    OUTPUT
)

print("\nModel saved:", OUTPUT)
