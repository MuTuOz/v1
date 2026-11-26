
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(
    "/mnt/d/Alperen E/Belgelerim/4. Year/"
    "Güz Dönemi/CS 401/SeniorProject"
)
CLIENT_DIR = ROOT / "data" / "validation_v1"
SPLIT_DIR = ROOT / "data" / "splits_v2"

CLASSES = [
    "benign", "bruteforce", "ddos", "dos",
    "malware", "mitm", "recon", "web"
]
CLASS_TO_ID = {name: i for i, name in enumerate(CLASSES)}

reference = pd.read_csv(
    CLIENT_DIR / "client_1_train.csv", nrows=1
)
FEATURES = [
    col for col in reference.columns
    if col.startswith(("network_", "log_"))
]
assert len(FEATURES) == 71


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


def load_client(client_id, batch_size, round_num):
    df = pd.read_csv(
        CLIENT_DIR / f"client_{client_id}_train.csv"
    )
    x = prepare(df)
    y_ids = df["label2"].map(CLASS_TO_ID)

    assert y_ids.notna().all()

    y = torch.tensor(y_ids.to_numpy(), dtype=torch.long)

    generator = torch.Generator().manual_seed(
        42 + round_num * 100 + client_id
    )

    loader = DataLoader(
        TensorDataset(x, y),
        batch_size=batch_size,
        shuffle=True,
        generator=generator
    )
    return loader, len(df)


def train_local(model, loader, epochs, lr):
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    total_loss = 0.0
    total_samples = 0

    for _ in range(epochs):
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()

            total_loss += loss.item() * len(xb)
            total_samples += len(xb)

    return total_loss / total_samples
