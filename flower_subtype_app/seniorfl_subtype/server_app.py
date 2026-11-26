"""Flower FedAvg with strict full-participation and aggregation checks."""
import hashlib
import json
import time

import numpy as np
import pandas as pd
import torch
from flwr.common import ArrayRecord, ConfigRecord, Context
from flwr.serverapp import Grid, ServerApp
from flwr.serverapp.strategy import FedAvg

from .task import CLIENT_SIZES, CLASSES, DEFAULTS, FAMILY_OF, FEATURES, SCHEMA, SubtypeMLP, project_root

app = ServerApp()


class AuditedFedAvg(FedAvg):
    def __init__(self, out):
        super().__init__(fraction_train=1.0, fraction_evaluate=0.0, min_train_nodes=5,
                         min_available_nodes=5, weighted_by_key="num-examples")
        self.out = out
        self.rounds = []
        self.clients = []

    def aggregate_train(self, server_round, replies):
        replies = list(replies)
        if len(replies) != 5 or any(m.has_error() for m in replies):
            raise RuntimeError(f"Round {server_round}: all five successful replies required")
        replies.sort(key=lambda m: int(m.content["metrics"]["client-id"]))
        ids = [int(m.content["metrics"]["client-id"]) for m in replies]
        if ids != list(CLIENT_SIZES):
            raise RuntimeError(f"Repeated/missing client partitions: {ids}")
        states = []
        weights = []
        losses = []
        for m, cid in zip(replies, ids):
            metrics = m.content["metrics"]
            count = int(metrics["num-examples"])
            if count != CLIENT_SIZES[cid]:
                raise RuntimeError("Sample-count weight does not match partition")
            states.append(m.content["arrays"].to_torch_state_dict())
            weights.append(count / 22450)
            losses.append(float(metrics["train_loss"]))
            self.clients.append({"round": server_round, "client_id": cid,
                                 "num_examples": count, "aggregation_weight": count / 22450,
                                 "train_loss": losses[-1]})
        arrays, metrics = super().aggregate_train(server_round, replies)
        actual = arrays.to_torch_state_dict()
        max_error = 0.0
        for key, tensor in actual.items():
            reference = sum(s[key].double() * w for s, w in zip(states, weights))
            error = float((tensor.double() - reference).abs().max())
            max_error = max(max_error, error)
            torch.testing.assert_close(tensor.double(), reference, rtol=1e-6, atol=1e-7)
        weighted_loss = float(np.dot(losses, weights))
        if not np.isclose(metrics["train_loss"], weighted_loss, rtol=1e-12):
            raise RuntimeError("Weighted training loss mismatch")
        digest = hashlib.sha256(b"".join(t.numpy().tobytes() for t in actual.values())).hexdigest()
        self.rounds.append({"round": server_round, "clients": 5, "total_examples": 22450,
                            "weighted_train_loss": weighted_loss,
                            "aggregation_max_abs_error": max_error, "weights_sha256": digest})
        pd.DataFrame(self.rounds).to_csv(self.out / "rounds.csv", index=False)
        pd.DataFrame(self.clients).to_csv(self.out / "client_rounds.csv", index=False)
        return arrays, metrics


@app.main()
def main(grid: Grid, context: Context):
    config = {**DEFAULTS, **context.run_config}
    if any(config[k] != DEFAULTS[k] for k in DEFAULTS if k != "project-root"):
        raise ValueError("This experiment requires the exact preregistered settings")
    root = project_root(config)
    out = root / "results/subtype_flower_val_v1"
    model_path = root / "models/subtype_flower_val_v1.pt"
    if model_path.exists() or (out / "rounds.csv").exists():
        raise FileExistsError("Existing experiment output; use a new run directory to rerun")
    if not (out / "data_audit.json").is_file():
        raise RuntimeError("Run scripts/26_run_flower_subtype_val_v1.py --stage audit first")
    torch.set_num_threads(1)
    torch.manual_seed(int(config["seed"]))
    np.random.seed(int(config["seed"]))
    torch.use_deterministic_algorithms(True)
    model = SubtypeMLP()
    start = time.perf_counter()
    strategy = AuditedFedAvg(out)
    result = strategy.start(grid=grid, initial_arrays=ArrayRecord(model.state_dict()),
                            train_config=ConfigRecord(config), num_rounds=15, timeout=180)
    if len(strategy.rounds) != 15:
        raise RuntimeError("Incomplete training")
    model.load_state_dict(result.arrays.to_torch_state_dict())
    torch.save({"state_dict": model.state_dict(), "features": FEATURES, "classes": CLASSES,
                "family_of": FAMILY_OF, "preprocessing": SCHEMA["preprocessing"],
                "rounds": 15, "local_epochs": 1, "seed": 42, "split": "validation_v1",
                "config": config, "optimizer_reset_each_round": True}, model_path)
    (out / "training_execution.json").write_text(json.dumps({
        "status": "complete", "rounds_completed": 15, "client_updates": 75,
        "training_wall_seconds": time.perf_counter() - start,
        "model": str(model_path), "config": config}, indent=2), encoding="utf-8")
    print(f"Saved final 84-class model: {model_path}", flush=True)
