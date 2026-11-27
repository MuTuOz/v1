#!/usr/bin/env python3
"""Merge target-side evidence into a manifest the orchestrator produced.

The orchestrator can only record what the attacker *tried*; per
docs/kali_lab_deployment_plan.md, "scenario labels come from orchestration
plus target/service evidence, never model predictions." Run something on the
target (service logs, `top`/`vmstat` snapshots, auth.log failed-attempt count,
a resource graph) and record what you observed here.

Usage:
    python3 attach_target_evidence.py --manifest runs/<id>/manifest.json \\
        --run-id dos_syn-flood-port-80_000 \\
        --effect "nginx access log shows 0 successful requests during window; CPU pinned at 98% per vmstat" \\
        --evidence-file /path/to/vmstat_snapshot.txt \\
        --confirmed-family dos
"""
import argparse
import datetime as dt
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--effect", required=True, help="what you observed on the TARGET, in your own words")
    ap.add_argument("--evidence-file", action="append", default=[], help="path to a target-side log/snapshot; repeatable")
    ap.add_argument("--confirmed-family", help="label2 you actually confirmed happened (may differ from intended)")
    ap.add_argument("--ambiguous", action="store_true", help="mark as ambiguous instead of confirmed")
    a = ap.parse_args()

    m = json.loads(a.manifest.read_text())
    run = next((r for r in m["runs"] if r["run_id"] == a.run_id), None)
    if run is None:
        raise SystemExit(f"no run_id {a.run_id} in {a.manifest}; ids present: {[r['run_id'] for r in m['runs']]}")

    run["actual_effect"] = a.effect
    run["target_evidence_files"] = a.evidence_file
    run["ambiguity_flag"] = bool(a.ambiguous)
    if a.confirmed_family:
        run["confirmed_family"] = a.confirmed_family
    run["evidence_attached_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    a.manifest.write_text(json.dumps(m, indent=2))
    print(f"updated {a.run_id} in {a.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
