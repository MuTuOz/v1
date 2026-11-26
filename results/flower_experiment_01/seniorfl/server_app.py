
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from sklearn.metrics import accuracy_score, f1_score
from flwr.serverapp import ServerApp, Grid
from flwr.serverapp.strategy import FedAvg
from flwr.common import ArrayRecord, ConfigRecord, Context

from seniorfl.task import (
    MLP, FEATURES, CLASSES, CLASS_TO_ID, prepare,
    ROOT, SPLIT_DIR
)

app = ServerApp()


@app.main()
def main(grid: Grid, context: Context):
    torch.manual_seed(42)
    torch.set_num_threads(4)

    rounds = int(context.run_config["num-server-rounds"])
    model = MLP()

    print("\n=== FLOWER FEDAVG ===", flush=True)
    print("Rounds:", rounds, flush=True)
    print("Clients: 5", flush=True)
    print("Model: 71 -> 64 -> 32 -> 8", flush=True)

    strategy = FedAvg(
        fraction_train=1.0,
        fraction_evaluate=0.0,
        min_train_nodes=5,
        min_available_nodes=5,
    )

    result = strategy.start(
        grid=grid,
        initial_arrays=ArrayRecord(model.state_dict()),
        train_config=ConfigRecord({}),
        num_rounds=rounds,
    )

    model.load_state_dict(
        result.arrays.to_torch_state_dict()
    )
    model.eval()

    # Test yalnizca egitim tamamlandiktan sonra.
    test = pd.read_csv(SPLIT_DIR / "test_episode.csv")
    y_test = test["label2"].map(CLASS_TO_ID).to_numpy()

    with torch.no_grad():
        preds = model(prepare(test)).argmax(1).numpy()

    test_labels = sorted(np.unique(y_test).tolist())

    accuracy = accuracy_score(y_test, preds)
    macro_f1 = f1_score(
        y_test, preds,
        labels=test_labels,
        average="macro",
        zero_division=0
    )

    print("\n=== FLOWER FINAL RESULTS ===", flush=True)
    print("Accuracy:", round(accuracy, 4), flush=True)
    print("Macro F1:", round(macro_f1, 4), flush=True)

    models_dir = ROOT / "models"
    results_dir = ROOT / "results"
    models_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)

    torch.save({
        "state_dict": model.state_dict(),
        "features": FEATURES,
        "classes": CLASSES,
        "preprocessing": "signed_log1p_clip_1e8",
        "rounds": rounds,
    }, models_dir / "flower_fedavg_mlp_v1.pt")

    with open(
        results_dir / "flower_fedavg_v1_metrics.json",
        "w", encoding="utf-8"
    ) as f:
        json.dump({
            "episode_test_accuracy": float(accuracy),
            "episode_test_macro_f1": float(macro_f1),
            "rounds": rounds,
            "clients": 5
        }, f, indent=2)

    print("\nFlower model and metrics saved.", flush=True)
