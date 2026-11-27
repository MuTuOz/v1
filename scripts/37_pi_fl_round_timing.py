#!/usr/bin/env python3
"""Per-round timing and byte counters for a finished pi_fl_v1 experiment (v2).

v1 of this script read message_ins/message_res from superlink_state.db; Flower 1.40
purges delivered messages, so those tables were empty and v1 wrote empty tables
(kept as FAILED_v1_message_tables_empty_* in each experiment directory).

v2 sources (all clocks NTP-synchronised; PC/WSL and Pi UTC checked equal at start):
  * server: `task_logs` rows of the ServerApp task in a temporary COPY of
    superlink_state.db. Each round end is the flush timestamp of the log chunk that
    contains "aggregate_train: Received". Log chunks are flushed in batches, so
    these are coarse (flush-granularity) times, not exact event times.
  * clients: modification times of each device's per-round JSON (written at the end of
    local training + 10 warm inference batches on that device). Pi mtimes come from
    `stat` on the Pi (device_2_pi/pi_round_json_mtimes_epoch.txt); PC files are read
    directly from device_1_pc/.
Byte counters: Flower's own run-table bytes_sent/bytes_recv, and Pi wlan0 counter deltas
around `flwr run` (all interface traffic in the window; upper bound).

Writes NEW files only: round_timing_v2.csv and timing_and_bytes_summary_v2.json.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def read_two(p: Path):
    if not p.exists():
        return None
    v = [int(x) for x in p.read_text().split()]
    return v[0], v[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment-id", required=True)
    a = ap.parse_args()
    exp = ROOT / "results/pi_fl_v1" / a.experiment_id
    out_csv, out_json = exp / "round_timing_v2.csv", exp / "timing_and_bytes_summary_v2.json"
    for o in (out_csv, out_json):
        if o.exists():
            raise FileExistsError(o)
    cfg = json.loads((exp / "config.json").read_text())
    with tempfile.TemporaryDirectory() as td:
        for f in exp.glob("superlink_state.db*"):
            shutil.copy2(f, Path(td) / f.name)
        con = sqlite3.connect(Path(td) / "superlink_state.db")
        logs = pd.read_sql("select timestamp, log from task_logs order by timestamp", con)
        run = pd.read_sql("select run_id, bytes_sent, bytes_recv, clientapp_runtime from run", con)
        con.close()
    start_rows = logs[logs.log.str.contains("fraction_evaluate is set")]
    strategy_start = float(start_rows.timestamp.iloc[0]) if len(start_rows) else None
    agg = logs[logs.log.str.contains("aggregate_train: Received")].timestamp.astype(float).tolist()
    rows = []
    for r in range(1, cfg["rounds"] + 1):
        row = {"round": r, "server_aggregate_log_flush_epoch": agg[r - 1] if r - 1 < len(agg) else None}
        prev = (agg[r - 2] if r >= 2 else strategy_start) if r - 1 < len(agg) else None
        row["server_round_seconds_coarse"] = (row["server_aggregate_log_flush_epoch"] - prev) if prev else None
        rows.append(row)
    df = pd.DataFrame(rows)
    # client JSON finish times
    pi_m = exp / "device_2_pi/pi_round_json_mtimes_epoch.txt"
    if pi_m.exists():
        for line in pi_m.read_text().split("\n"):
            if line.strip():
                t, name = line.split(maxsplit=1)
                r = int(re.search(r"round(\d+)\.json", name).group(1))
                df.loc[df["round"] == r, "pi_client2_json_written_epoch"] = float(t)
    pc_dir = exp / "device_1_pc"
    if pc_dir.exists():
        for p in pc_dir.glob("*_round*.json"):
            r = int(re.search(r"round(\d+)\.json", p.name).group(1))
            df.loc[df["round"] == r, "pc_client1_json_written_epoch"] = p.stat().st_mtime
    for col, src in (("pi_client2", "device_2_pi"), ("pc_client1", "device_1_pc")):
        c = f"{col}_json_written_epoch"
        if c in df:
            df[f"{col}_interval_seconds"] = df[c].diff()
            d = exp / src
            tsec = {}
            for p in d.glob("*_round*.json"):
                j = json.loads(p.read_text())
                tsec[int(re.search(r"round(\d+)\.json", p.name).group(1))] = j["training_seconds"]
            df[f"{col}_training_seconds"] = df["round"].map(tsec)
    if {"pi_client2_json_written_epoch", "pc_client1_json_written_epoch"} <= set(df.columns):
        df["pi_finish_minus_pc_finish_seconds"] = df.pi_client2_json_written_epoch - df.pc_client1_json_written_epoch
    df.to_csv(out_csv, index=False)
    pi = exp / "device_2_pi"
    before, after = read_two(pi / "netbytes_wlan0_before_run.txt"), read_two(pi / "netbytes_wlan0_after_run.txt")
    steady = df[df["round"] >= 2]
    summary = {
        "experiment_id": a.experiment_id, "rounds": cfg["rounds"], "num_clients": cfg["num_clients"],
        "server_round_seconds_coarse": df.server_round_seconds_coarse.round(3).tolist(),
        "server_round_seconds_coarse_median_rounds_2_to_N": float(steady.server_round_seconds_coarse.median()),
        "pi_client2_interval_seconds_median_rounds_2_to_N": float(steady.pi_client2_interval_seconds.median())
        if "pi_client2_interval_seconds" in df else None,
        "pi_client2_training_seconds_median": float(df.pi_client2_training_seconds.median())
        if "pi_client2_training_seconds" in df else None,
        "pc_client1_training_seconds_median": float(df.pc_client1_training_seconds.median())
        if "pc_client1_training_seconds" in df else None,
        "flower_run_table": run.to_dict(orient="records"),
        "flower_run_table_note": "SuperLink 1.40 run-level bytes_sent/bytes_recv (all nodes in the run); not split per node",
        "pi_wlan0_counters": None if not (before and after) else {
            "rx_bytes_delta": after[0] - before[0], "tx_bytes_delta": after[1] - before[1],
            "window": "read via SSH immediately before and after `flwr run` on the PC",
            "note": "all wlan0 traffic in the window (SSH, polling/heartbeats, FAB download, TLS); upper bound"},
        "pc_interface_counters": "not measured: WSL2 mirrored-mode eth2 counters read 0/0 (pc_netbytes.txt); Windows-side counters not captured",
        "timing_caveats": ["server times are log-chunk flush timestamps (coarse)",
                           "round 1 includes ClientApp/FAB start-up",
                           "client intervals include ClientApp process start each round (Flower subprocess isolation), CSV load, training, 10 inference batches, transport and polling delay"],
        "source": "scripts/37_pi_fl_round_timing.py v2",
    }
    out_json.write_text(json.dumps(summary, indent=2, default=float))
    print(df.round(3).to_string(index=False))
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
