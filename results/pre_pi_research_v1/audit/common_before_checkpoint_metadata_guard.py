import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

SCHEMA = json.loads(Path(__file__).with_name("schema.json").read_text())
CLASSES = SCHEMA["classes"]
FEATURES = SCHEMA["features"]
FAMILY_OF = SCHEMA["family_of"]
CLASS_TO_ID = {s: i for i, s in enumerate(CLASSES)}


def dump(path, value):
    path = Path(path)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(df, features=FEATURES):
    x = df[list(features)].to_numpy(np.float64)
    x = np.nan_to_num(x, nan=0., posinf=0., neginf=0.)
    x = np.clip(x, -1e8, 1e8)
    return torch.from_numpy((np.sign(x) * np.log1p(np.abs(x))).astype(np.float32))


def labels(df):
    y = df.label4.map(CLASS_TO_ID)
    if y.isna().any():
        raise ValueError("Unknown training-derived subtype")
    return torch.tensor(y.to_numpy(np.int64))


class MLP(nn.Module):
    def __init__(self, inputs=71):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(inputs, 64), nn.ReLU(), nn.Linear(64, 32),
                                 nn.ReLU(), nn.Linear(32, 84))

    def forward(self, x):
        return self.net(x)


def class_weights(counts, method):
    if method == "unweighted":
        return None
    n = np.asarray(counts, dtype=float)
    if len(n) != 84 or np.any(n <= 0):
        raise ValueError("Weights require positive global training supports for all 84 classes")
    if method == "unweighted":
        return None
    if method == "inverse_frequency":
        w = 1. / n
    elif method == "effective_number":
        beta = .999
        w = (1 - beta) / (-np.expm1(n * np.log(beta)))
    else:
        raise ValueError(method)
    return torch.tensor(w / w.mean(), dtype=torch.float32)


def train_epochs(model, df, config, seed, epochs, *, weights=None):
    """Accepts only the caller's authorized training partition; no validation IO."""
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    x, y = prepare(df, config["features"]), labels(df)
    loader = DataLoader(TensorDataset(x, y), batch_size=config["batch_size"], shuffle=True,
                        generator=torch.Generator().manual_seed(seed))
    optimizer = torch.optim.Adam(model.parameters(), lr=config["learning_rate"])
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    records = []
    start = time.perf_counter()
    for epoch in range(1, epochs + 1):
        model.train(); total = 0.; seen = 0; steps = 0
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward(); optimizer.step()
            total += float(loss.detach()) * len(xb); seen += len(xb); steps += 1
        records.append({"epoch": epoch, "loss": total / seen, "examples": seen,
                        "optimizer_steps": steps, "elapsed_seconds": time.perf_counter() - start})
    return records


def save_checkpoint(path, model, config, **metadata):
    if Path(path).exists():
        raise FileExistsError(path)
    torch.save({"state_dict": model.state_dict(), "features": config["features"],
                "classes": CLASSES, "family_of": FAMILY_OF,
                "preprocessing": "signed_log1p_clip_1e8", "config": config, **metadata}, path)


def train_path(root, config, client_id=None):
    """Only frozen train or versioned training-only allocation files are accepted."""
    root = Path(root).resolve()
    if client_id is None:
        return root / "data/validation_v1/train.csv"
    if client_id not in range(1, 6):
        raise ValueError("Client ID must be 1..5")
    if config["partition"] == "original":
        return root / "data/validation_v1" / f"client_{client_id}_train.csv"
    if config["partition"] not in ["balanced", "exclusive"]:
        raise ValueError("Unknown allocation")
    return root / "results/pre_pi_research_v1/audit/allocations" / config["partition"] / f"client_{client_id}_train.csv"
