"""Baseline-compatible model, schema and data transformation.

The project root is explicit, because a FAB is installed outside the source tree.
No dataset is read at import time. Only the seven allowlisted CSVs can be loaded.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

SCHEMA = json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))
FEATURES = SCHEMA["features"]
CLASSES = SCHEMA["classes"]
FAMILY_OF = SCHEMA["family_of"]
CLASS_TO_ID = {name: i for i, name in enumerate(CLASSES)}
DEFAULTS = {"num-server-rounds": 15, "local-epochs": 1, "batch-size": 128,
            "learning-rate": 0.001, "seed": 42, "project-root": SCHEMA["project_root"]}
CLIENT_SIZES = {1: 4430, 2: 6216, 3: 2901, 4: 5103, 5: 3800}
ALLOWED_CSVS = {"train.csv", "validation.csv"} | {f"client_{i}_train.csv" for i in CLIENT_SIZES}


def project_root(config=None):
    root = Path((config or {}).get("project-root", DEFAULTS["project-root"])).resolve()
    if not (root / "data/validation_v1/train.csv").is_file():
        raise FileNotFoundError(f"Set project-root to the external project/data root: {root}")
    return root


def read_split(root, filename):
    if filename not in ALLOWED_CSVS:
        raise ValueError(f"Dataset is outside this experiment's allowlist: {filename}")
    return pd.read_csv(Path(root) / "data/validation_v1" / filename)


def prepare(df):
    values = df[FEATURES].to_numpy(dtype=np.float64)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    values = np.clip(values, -1e8, 1e8)
    values = np.sign(values) * np.log1p(np.abs(values))
    return torch.from_numpy(values.astype(np.float32))


def make_labels(df):
    labels = df["label4"].map(CLASS_TO_ID)
    if labels.isna().any():
        raise ValueError("Unknown subtype in training-derived class mapping")
    return torch.tensor(labels.to_numpy(), dtype=torch.long)


class SubtypeMLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(71, 64), nn.ReLU(), nn.Linear(64, 32),
                                 nn.ReLU(), nn.Linear(32, 84))

    def forward(self, x):
        return self.net(x)


@lru_cache(maxsize=5)
def client_tensors(root, client_id):
    df = read_split(root, f"client_{client_id}_train.csv")
    if len(df) != CLIENT_SIZES[client_id]:
        raise ValueError("Client partition size changed")
    return prepare(df), make_labels(df)


def train_local(model, root, client_id, round_num, config):
    seed = int(config["seed"]) + 100 * round_num + client_id
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    x, y = client_tensors(str(root), client_id)
    loader = DataLoader(TensorDataset(x, y), batch_size=int(config["batch-size"]),
                        shuffle=True, generator=torch.Generator().manual_seed(seed))
    model.train()
    # Adam is freshly initialized for each client in each round, as in the 8-class app.
    optimizer = torch.optim.Adam(model.parameters(), lr=float(config["learning-rate"]))
    criterion = nn.CrossEntropyLoss()
    loss_sum = 0.0
    seen = 0
    for _ in range(int(config["local-epochs"])):
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.detach()) * len(xb)
            seen += len(xb)
    return loss_sum / seen, len(x)
