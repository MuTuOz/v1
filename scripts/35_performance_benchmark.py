#!/usr/bin/env python3
"""Non-accuracy performance of the IDS models: inference latency, throughput,
memory, model size and federated communication cost.

Experiment ID: performance_v1. Run the SAME script on the PC (server) and on the
Raspberry Pi (client) so numbers are comparable:

    python scripts/35_performance_benchmark.py --device-label pc_x86
    python scripts/35_performance_benchmark.py --device-label pi5_arm64

Each run writes a NEW directory results/performance_v1/<device-label>_<UTC time>/
and never overwrites. Inputs are training-only rows (balanced allocation CSVs,
or --input-csv) and saved checkpoints; no validation/test file is read. Latency
numbers describe the machine the script ran on and nothing else.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "results/pre_pi_research_v1"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rss_mb() -> float | None:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2**20
    except Exception:  # psutil missing: fall back to /proc
        try:
            for line in open("/proc/self/status"):
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
        except OSError:
            return None
    return None


def device_info() -> dict:
    info = {"platform": platform.platform(), "machine": platform.machine(),
            "python": sys.version.split()[0], "cpu_count": os.cpu_count()}
    try:
        info["pi_model"] = Path("/proc/device-tree/model").read_text().strip("\x00\n")
    except OSError:
        info["pi_model"] = None
    try:
        for line in open("/proc/cpuinfo"):
            if line.lower().startswith("model name"):
                info["cpu_model"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                info["mem_total_mb"] = int(line.split()[1]) / 1024
    except OSError:
        pass
    try:
        t = Path("/sys/class/thermal/thermal_zone0/temp").read_text()
        info["cpu_temp_c_start"] = int(t) / 1000
    except OSError:
        info["cpu_temp_c_start"] = None
    return info


def preprocess(x: np.ndarray) -> np.ndarray:
    x = np.nan_to_num(x.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    x = np.clip(x, -1e8, 1e8)
    return (np.sign(x) * np.log1p(np.abs(x))).astype(np.float32)


def timeit(fn, reps: int, warmup: int) -> dict:
    for _ in range(warmup):
        fn()
    t = []
    for _ in range(reps):
        s = time.perf_counter_ns()
        fn()
        t.append((time.perf_counter_ns() - s) / 1e6)
    t.sort()
    q = lambda p: t[min(len(t) - 1, int(round(p * (len(t) - 1))))]
    return {"reps": reps, "warmup": warmup, "mean_ms": statistics.fmean(t), "median_ms": q(0.5),
            "p95_ms": q(0.95), "p99_ms": q(0.99), "min_ms": t[0], "max_ms": t[-1]}


def bench_mlp(ckpt: Path, X_raw: np.ndarray, feats: list[str], reps: int, warmup: int, threads: int) -> dict:
    import torch
    torch.set_num_threads(threads)
    gc.collect()
    r0 = rss_mb()
    data = torch.load(ckpt, map_location="cpu", weights_only=False)
    from torch import nn
    sd = data["state_dict"]
    n_in = sd["net.0.weight"].shape[1]
    model = nn.Sequential(nn.Linear(n_in, 64), nn.ReLU(), nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 84))
    model.load_state_dict({k.removeprefix("net."): v for k, v in sd.items()})
    model.eval()
    r1 = rss_mb()
    params = sum(p.numel() for p in model.parameters())
    # feature order guard
    if list(data["features"]) != feats[:n_in] and len(data["features"]) == n_in:
        feats = list(data["features"])
    one_raw = X_raw[:1]
    batch_raw = X_raw[:128]
    Xp = torch.from_numpy(preprocess(X_raw))
    one = Xp[:1]
    batch = Xp[:128]
    out = {"checkpoint": str(ckpt.relative_to(ROOT)), "checkpoint_bytes": ckpt.stat().st_size,
           "checkpoint_sha256": sha256(ckpt), "parameters": params,
           "float32_weight_bytes": params * 4, "torch": torch.__version__, "threads": threads,
           "rss_before_load_mb": r0, "rss_after_load_mb": r1}
    with torch.inference_mode():
        out["single_record_model_only"] = timeit(lambda: model(one), reps, warmup)
        out["single_record_preprocess_plus_model"] = timeit(
            lambda: model(torch.from_numpy(preprocess(one_raw))).argmax(1), reps, warmup)
        b = timeit(lambda: model(batch), max(50, reps // 10), warmup)
        b["rows"] = len(batch)
        b["throughput_rows_per_s"] = len(batch) / (b["median_ms"] / 1000)
        out["batch128_model_only"] = b
        full = timeit(lambda: model(Xp), 5, 1)
        full["rows"] = len(Xp)
        full["throughput_rows_per_s"] = len(Xp) / (full["median_ms"] / 1000)
        out["all_rows_model_only"] = full
    out["rss_after_inference_mb"] = rss_mb()
    del batch_raw
    return out


def bench_onnx(path: Path, X_raw: np.ndarray, reps: int, warmup: int) -> dict:
    try:
        import onnxruntime as ort
    except ImportError:
        return {"status": "skipped: onnxruntime not installed"}
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    r0 = rss_mb()
    sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
    r1 = rss_mb()
    inp = sess.get_inputs()[0]
    n = inp.shape[1] if isinstance(inp.shape[1], int) else X_raw.shape[1]
    x = X_raw[:, :n].astype(np.float32)
    one, batch = x[:1], x[:128]
    out = {"model": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path),
           "onnxruntime": ort.__version__, "inputs": n, "rss_before_load_mb": r0, "rss_after_load_mb": r1,
           "note": "family RF on raw features as exported by scripts/07_export_onnx.py; input semantics not re-verified here"}
    out["single_record"] = timeit(lambda: sess.run(None, {inp.name: one}), reps, warmup)
    b = timeit(lambda: sess.run(None, {inp.name: batch}), max(50, reps // 10), warmup)
    b["rows"] = len(batch)
    b["throughput_rows_per_s"] = len(batch) / (b["median_ms"] / 1000)
    out["batch128"] = b
    return out


def communication_table() -> pd.DataFrame:
    """Federated communication from saved Flower logs (application payload only)."""
    rows = []
    idx = pd.read_csv(PRE / "EXPERIMENT_INDEX.csv")
    for r in idx[idx["mode"] == "flower_fedavg"].itertuples():
        d = ROOT / r.artifact_dir
        th = d / "training_history.csv"
        if not th.exists():
            continue
        h = pd.read_csv(th)
        m = json.loads((d / "metrics.json").read_text())
        cr = pd.read_csv(d / "client_rounds.csv") if (d / "client_rounds.csv").exists() else None
        up, down = h["uplink_serialized_array_bytes"].sum(), h["downlink_serialized_array_bytes"].sum()
        per_update = int(cr["serialized_array_bytes"].median()) if cr is not None else None
        rows.append({
            "experiment_id": r.experiment_id, "partition": r.partition, "loss": r.loss, "seed": r.seed,
            "features": r.features, "clients_per_round": r.clients_per_round, "local_epochs": r.local_epochs,
            "rounds": len(h), "bytes_per_client_update": per_update,
            "uplink_bytes_per_round_median": float(h["uplink_serialized_array_bytes"].median()),
            "uplink_bytes_total": int(up), "downlink_bytes_total": int(down),
            "total_mb": (up + down) / 1e6,
            "client_train_seconds_per_round_median": float(cr["training_seconds"].median()) if cr is not None else None,
            "client_rss_mb_median": float(cr["rss_bytes"].median() / 2**20) if cr is not None else None,
            "attack_detection_recall": m.get("attack_detection_recall"),
            "family_accuracy": m.get("family_accuracy"), "exact_subtype_accuracy": m.get("exact_subtype_accuracy"),
            "benign_false_positive_rate": m.get("benign_false_positive_rate"),
            "detection_recall_per_total_mb": (m.get("attack_detection_recall") or 0) / ((up + down) / 1e6),
        })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device-label", required=True, help="e.g. pc_x86, pi4_arm64, pi5_arm64")
    ap.add_argument("--checkpoint", default="models/subtype_flower_val_v1.pt")
    ap.add_argument("--extra-checkpoints", nargs="*", default=["models/subtype_centralized_val_v1.pt"])
    ap.add_argument("--onnx", default="models/family_rf_5sec.onnx")
    ap.add_argument("--input-csv", default=str(PRE / "audit/allocations/balanced/client_1_train.csv"),
                    help="training-only rows used purely as realistic feature vectors")
    ap.add_argument("--rows", type=int, default=2000)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--warmup", type=int, default=200)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--out-root", default="results/performance_v1")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / args.out_root / f"{args.device_label}_{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    feats = json.loads((PRE / "phase01/ref_local_c1_s42/config.json").read_text())["features"]
    inp = Path(args.input_csv)
    df = pd.read_csv(inp, nrows=args.rows, low_memory=False)
    X_raw = df[feats].to_numpy(np.float64)
    res = {"experiment_id": "performance_v1", "device_label": args.device_label, "utc": stamp,
           "device": device_info(), "input_csv": str(inp), "input_sha256": sha256(inp),
           "rows_loaded": len(df), "command": " ".join([sys.executable] + sys.argv),
           "script_sha256": sha256(Path(__file__)),
           "scope": "single-device inference/memory measurement; not wire-level, not energy, not accuracy"}
    res["mlp"] = []
    for ck in [args.checkpoint] + list(args.extra_checkpoints):
        p = ROOT / ck
        if p.exists():
            res["mlp"].append(bench_mlp(p, X_raw, feats, args.reps, args.warmup, args.threads))
    if args.onnx and (ROOT / args.onnx).exists():
        res["onnx_rf"] = bench_onnx(ROOT / args.onnx, X_raw, args.reps, args.warmup)
    comm = communication_table()
    comm.to_csv(out / "communication_from_saved_flower_runs.csv", index=False)
    n_train = 22450
    res["centralized_raw_upload_reference"] = {
        "rows": n_train, "features": 71,
        "float32_feature_bytes": n_train * 71 * 4,
        "note": "bytes to ship the 22,450 training feature vectors once as float32 (no labels/headers/compression)",
    }
    try:
        res["device"]["cpu_temp_c_end"] = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    except OSError:
        pass
    res["runtime_seconds"] = time.time() - t0
    (out / "benchmark.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({"out": str(out.relative_to(ROOT)),
                      "mlp_single_record_median_ms": [m["single_record_preprocess_plus_model"]["median_ms"] for m in res["mlp"]],
                      "mlp_batch128_rows_per_s": [m["batch128_model_only"]["throughput_rows_per_s"] for m in res["mlp"]]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
