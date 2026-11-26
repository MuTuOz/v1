
import json

import numpy as np
import pandas as pd
import torch

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
)

from flwr.serverapp import ServerApp, Grid
from flwr.serverapp.strategy import FedAvg
from flwr.common import ArrayRecord, ConfigRecord, Context

from seniorfl.task import (
    MLP,
    FEATURES,
    CLASSES,
    CLASS_TO_ID,
    prepare,
    ROOT,
)

app = ServerApp()


@app.main()
def main(grid: Grid, context: Context):
    torch.manual_seed(42)
    torch.set_num_threads(4)

    rounds = int(context.run_config["num-server-rounds"])

    model = MLP()

    print("\n=== FLOWER FEDAVG VALIDATION V1 ===", flush=True)
    print("Rounds:", rounds, flush=True)
    print("Clients: 5", flush=True)
    print("Model: 71 -> 64 -> 32 -> 8", flush=True)
    print("Training: validation_v1/client_N_train.csv", flush=True)

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

    # IMPORTANT:
    # Use validation only. Do not touch test_episode.csv.
    validation_path = (
        ROOT / "data" / "validation_v1" / "validation.csv"
    )

    validation = pd.read_csv(validation_path)

    y_series = validation["label2"].map(CLASS_TO_ID)
    assert y_series.notna().all()

    y_true = y_series.to_numpy(dtype=np.int64)

    with torch.no_grad():
        y_pred = (
            model(prepare(validation))
            .argmax(dim=1)
            .numpy()
        )

    all_labels = list(range(len(CLASSES)))
    observed_labels = sorted(np.unique(y_true).tolist())

    accuracy = accuracy_score(y_true, y_pred)

    macro_f1_observed = f1_score(
        y_true,
        y_pred,
        labels=observed_labels,
        average="macro",
        zero_division=0,
    )

    macro_f1_all = f1_score(
        y_true,
        y_pred,
        labels=all_labels,
        average="macro",
        zero_division=0,
    )

    report = classification_report(
        y_true,
        y_pred,
        labels=all_labels,
        target_names=CLASSES,
        output_dict=True,
        zero_division=0,
    )

    cm = confusion_matrix(
        y_true,
        y_pred,
        labels=all_labels,
    )

    models_dir = ROOT / "models"
    results_dir = ROOT / "results"

    models_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    model_path = (
        models_dir / "flower_fedavg_val_v1.pt"
    )

    metrics_path = (
        results_dir / "flower_fedavg_val_v1_metrics.json"
    )

    torch.save(
        {
            "state_dict": model.state_dict(),
            "features": FEATURES,
            "classes": CLASSES,
            "preprocessing": "signed_log1p_clip_1e8",
            "rounds": rounds,
            "training_split": "validation_v1/train",
        },
        model_path,
    )

    metrics = {
        "experiment": "flower_fedavg_val_v1",
        "training_records": 22450,
        "validation_records": len(validation),
        "validation_accuracy": float(accuracy),
        "validation_macro_f1_observed": float(
            macro_f1_observed
        ),
        "validation_macro_f1_all_8": float(
            macro_f1_all
        ),
        "observed_families": [
            CLASSES[i] for i in observed_labels
        ],
        "rounds": rounds,
        "clients": 5,
        "model_parameters": sum(
            p.numel() for p in model.parameters()
        ),
        "seed": 42,
        "note": (
            "Validation V1 uses attack episode candidates "
            "and a benign temporal holdout. "
            "The web family is absent from validation."
        ),
    }

    metrics_path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    pd.DataFrame(report).T.to_csv(
        results_dir / "flower_fedavg_val_v1_report.csv"
    )

    pd.DataFrame(
        cm, index=CLASSES, columns=CLASSES
    ).to_csv(
        results_dir / "flower_fedavg_val_v1_confusion.csv"
    )

    print("\n=== FLOWER VALIDATION RESULTS ===", flush=True)
    print("Validation samples:", len(validation), flush=True)
    print("Accuracy:", round(accuracy, 4), flush=True)
    print(
        "Macro F1 (observed families):",
        round(macro_f1_observed, 4),
        flush=True,
    )
    print(
        "Macro F1 (all 8 families):",
        round(macro_f1_all, 4),
        flush=True,
    )
    print("Model saved:", model_path, flush=True)
    print("Metrics saved:", metrics_path, flush=True)
