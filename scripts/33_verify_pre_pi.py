"""Read-only scientific/integrity verification; --seal creates the final bundle once.

Only frozen training/validation files are read. No training, capture or external
network activity occurs. Historical test splits are deliberately outside scope.
"""
import argparse
import ast
from collections import Counter
import datetime as dt
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import random
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/pre_pi_research_v1"
sys.path.insert(0, str(ROOT / "pre_pi_app"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import pandas as pd
from PIL import Image
import torch
from sklearn.metrics import classification_report, confusion_matrix
from researchfl.common import CLASSES, CLASS_TO_ID, FAMILY_OF, FEATURES, MLP, dump, prepare, sha, train_path
from researchfl.evaluation import hcm_lookup, masks_for_support, score


def equal(a, b, location):
    """Compare JSON metric structures, including explicitly undefined values."""
    if isinstance(a, dict):
        assert a.keys() == b.keys(), (location, a.keys(), b.keys())
        for key in a:
            equal(a[key], b[key], f"{location}.{key}")
    elif isinstance(a, float):
        assert b is not None and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), (location, a, b)
    else:
        assert a == b, (location, a, b)


def scientific_checks():
    index = pd.read_csv(OUT / "EXPERIMENT_INDEX.csv")
    assert len(index) == 44 and index.experiment_id.is_unique
    train = pd.read_csv(ROOT / "data/validation_v1/train.csv")
    val = pd.read_csv(ROOT / "data/validation_v1/validation.csv")
    assert (len(train), len(val), val.label4.nunique()) == (22450, 6486, 28)
    assert set(train.label4) == set(CLASSES)
    assert [x for x in train if x.startswith(("network_", "log_"))] == FEATURES
    assert train.groupby("label4").label2.nunique().max() == 1
    assert train.drop_duplicates("label4").set_index("label4").label2.to_dict() == FAMILY_OF
    keys = list(train.columns[:8])
    assert not train.duplicated(keys).any()
    assert not set(map(tuple, train[keys].to_numpy())) & set(map(tuple, val[keys].to_numpy()))
    assert not set(train.loc[train.label2 != "benign", "episode_id"]) & set(val.loc[val.label2 != "benign", "episode_id"])
    clients = [pd.read_csv(train_path(ROOT, {"partition": "original"}, c)) for c in range(1, 6)]
    joined = pd.concat(clients, ignore_index=True).sort_values(keys).reset_index(drop=True)
    ordered = train.sort_values(keys).reset_index(drop=True)
    assert joined[keys].equals(ordered[keys])
    torch.testing.assert_close(prepare(joined), prepare(ordered), rtol=0, atol=0)
    partition_sizes = {"original": {i: len(d) for i, d in enumerate(clients, 1)}}
    support = {("original", i): set(d.label4) for i, d in enumerate(clients, 1)}
    for name in ["balanced", "exclusive"]:
        folder = OUT / "audit/allocations" / name
        allocation = pd.read_csv(folder / "allocation_manifest.csv")
        assert sorted(allocation.global_train_row.tolist()) == list(range(22450))
        assert not allocation.global_train_row.duplicated().any()
        partition_sizes[name] = {}
        for client in range(1, 6):
            rows = allocation.loc[allocation.client_id == client, "global_train_row"].tolist()
            actual = pd.read_csv(folder / f"client_{client}_train.csv")
            expected = train.iloc[rows].reset_index(drop=True)
            assert actual[keys].equals(expected[keys]), (name, client)
            torch.testing.assert_close(prepare(actual), prepare(expected), rtol=0, atol=0)
            support[name, client] = set(actual.label4)
            partition_sizes[name][client] = len(actual)
        assert sum(partition_sizes[name].values()) == 22450
    y = val.label4.map(CLASS_TO_ID).to_numpy(np.int64)
    truth_families = val.label2.to_numpy()
    families = ["benign"] + sorted(set(FAMILY_OF.values()) - {"benign"})
    input_cache = {}
    metrics_checked = predictions_checked = inferred_models = fedavg_rounds = fedavg_updates = 0
    by_id = {}
    for row in index.itertuples():
        folder = ROOT / row.artifact_dir
        c = json.loads((folder / "config.json").read_text())
        complete = json.loads((folder / "COMPLETE.json").read_text())
        assert c["experiment_id"] == row.experiment_id and complete["status"] == "complete"
        assert c["class_counts"] == [int((train.label4 == s).sum()) for s in CLASSES]
        pred = pd.read_csv(folder / "predictions.csv")
        assert len(pred) == 6486
        np.testing.assert_array_equal(pred.validation_row, np.arange(6486))
        np.testing.assert_array_equal(pred.true_subtype_id, y)
        np.testing.assert_array_equal(pred.true_subtype, val.label4)
        np.testing.assert_array_equal(pred.true_family, val.label2)
        np.testing.assert_array_equal(pred.episode_id, val.episode_id)
        p = pred.predicted_subtype_id.to_numpy(np.int64)
        np.testing.assert_array_equal(pred.predicted_subtype, np.asarray(CLASSES)[p])
        pf = np.array([FAMILY_OF[s] for s in pred.predicted_subtype])
        np.testing.assert_array_equal(pred.predicted_family, pf)
        measured = score(y, p, ROOT)
        equal(measured, json.loads((folder / "metrics.json").read_text()), row.experiment_id)
        assert sum(measured["hierarchical_errors"].values()) == 6486
        assert measured["hcm_counts"]["tp"] + measured["hcm_counts"]["fn"] == 11782
        contributions = pd.read_csv(folder / "sample_hcm.csv")
        np.testing.assert_array_equal(contributions.to_numpy(), hcm_lookup(str(ROOT))[y, p])
        assert contributions.sum().to_dict() == measured["hcm_counts"]
        for level, t, pr, labs in [
            ("subtype", y, p, list(range(84))),
            ("family", truth_families, pf, families),
            ("detection", (truth_families != "benign").astype(int), (pf != "benign").astype(int), [0, 1]),
        ]:
            cm = pd.read_csv(folder / f"{level}_confusion.csv", index_col=0)
            np.testing.assert_array_equal(cm.to_numpy(), confusion_matrix(t, pr, labels=labs))
            assert int(cm.to_numpy().sum()) == 6486
            report = pd.read_csv(folder / f"{level}_report.csv", index_col=0)
            assert int(report.iloc[:len(labs)].support.sum()) == 6486
            names = CLASSES if level == "subtype" else (families if level == "family" else ["benign", "attack"])
            expected_report = pd.DataFrame(classification_report(t, pr, labels=labs, target_names=names,
                                                                output_dict=True, zero_division=0)).T
            np.testing.assert_allclose(report.loc[names].to_numpy(), expected_report.loc[names].to_numpy(), atol=1e-12)
        checkpoint = ROOT / complete["source_checkpoint"] if "source_checkpoint" in complete else folder / "model.pt"
        assert sha(checkpoint) == complete["checkpoint_sha256"]
        if "prediction_sha256" in complete:
            assert sha(folder / "predictions.csv") == complete["prediction_sha256"]
        data = torch.load(checkpoint, map_location="cpu", weights_only=True)
        assert data["classes"] == CLASSES and data["family_of"] == FAMILY_OF
        assert data["features"] == c["features"]
        expected_features = FEATURES if row.features == 71 else [f for f in FEATURES if f.startswith("network_")]
        assert data["features"] == expected_features
        torch.set_num_threads(c.get("train_threads", 1))
        model = MLP(row.features)
        model.load_state_dict(data["state_dict"])
        model.eval()
        feature_key = tuple(data["features"])
        if feature_key not in input_cache:
            input_cache[feature_key] = prepare(val, data["features"])
        with torch.inference_mode():
            inferred = np.concatenate([model(batch).argmax(1).numpy() for batch in input_cache[feature_key].split(512)])
        np.testing.assert_array_equal(inferred, p, err_msg=row.experiment_id)
        inferred_models += 1
        predictions_checked += len(p)
        by_id[row.experiment_id] = p
        history_path = folder / "training_history.csv"
        if history_path.exists():
            h = pd.read_csv(history_path)
            assert len(h) == 15
            if row.mode == "flower_fedavg":
                cr = pd.read_csv(folder / "client_rounds.csv")
                identities = json.loads((folder / "client_identity_audit.json").read_text())
                assert set(map(int, identities)) == set(range(1, 6))
                assert len(cr) == c["rounds"] * c["clients_per_round"]
                for round_no in range(1, 16):
                    records = cr.loc[cr["round"] == round_no].sort_values("client_id")
                    selected = sorted(random.Random(c["seed"] + 1000 * round_no).sample(list(range(1, 6)), c["clients_per_round"]))
                    assert records.client_id.tolist() == selected
                    counts = np.array([partition_sizes[c["partition"]][i] for i in selected])
                    np.testing.assert_array_equal(records["num-examples"], counts)
                    np.testing.assert_allclose(records.aggregation_weight, counts / counts.sum(), rtol=1e-12)
                    np.testing.assert_array_equal(records.examples_seen, counts * c["local_epochs"])
                    expected_steps = np.ceil(counts / c["batch_size"]).astype(int) * c["local_epochs"]
                    np.testing.assert_array_equal(records.optimizer_steps, expected_steps)
                    hr = h.loc[h["round"] == round_no].iloc[0]
                    assert hr.clients == len(selected) and hr.selected_training_samples == counts.sum()
                    assert hr.optimizer_steps == expected_steps.sum()
                    assert hr.examples_seen == counts.sum() * c["local_epochs"]
                    assert hr.aggregation_max_abs_error < 1e-6
                    assert hr.uplink_serialized_array_bytes == records.serialized_array_bytes.sum()
                assert data["optimizer_steps"] == int(h.optimizer_steps.sum())
                assert data["examples_seen"] == int(h.examples_seen.sum())
                fedavg_rounds += len(h)
                fedavg_updates += len(cr)
            else:
                cid = c["client_id"] if row.mode == "local_only" else None
                path = train_path(ROOT, c, cid)
                n = partition_sizes[c["partition"]][cid] if cid else len(train)
                assert (h.examples == n).all()
                assert (h.optimizer_steps == math.ceil(n / c["batch_size"])).all()
                assert data["training_sha256"] == sha(path)
                assert data["optimizer_steps"] == int(h.optimizer_steps.sum())
        for key in ["exact_subtype_accuracy", "subtype_macro_f1_observed", "attack_only_subtype_accuracy",
                    "family_accuracy", "family_macro_f1_observed", "attack_detection_recall", "benign_false_positive_rate", "hcm_f1"]:
            assert math.isclose(getattr(row, key), measured[key], abs_tol=1e-12)
        metrics_checked += 1
    # Recompute every stored client-relative subset with the same frozen masks.
    detailed = pd.read_csv(OUT / "phase02/detailed_unseen_hcm.csv")
    for row in detailed.itertuples():
        mask = masks_for_support(support[row.partition, row.client_id], val.label4)[row.subset]
        m = score(y[mask], by_id[row.experiment_id][mask], ROOT)
        assert row.samples == m["samples"] and row.observed_subtypes == m["observed_subtypes"]
        for key in ["exact_subtype_accuracy", "family_accuracy", "attack_detection_recall", "hcm_f1"]:
            actual = getattr(row, key)
            assert pd.isna(actual) if m[key] is None else math.isclose(actual, m[key], abs_tol=1e-12)
        for key, value in m["hcm_counts"].items():
            assert getattr(row, "hcm_" + key) == value
    reference = index[index.experiment_id.str.startswith("ref_")]
    assert len(reference) == 21
    for _, group in reference.groupby(["mode", "client_id"], dropna=False):
        assert sorted(group.seed.tolist()) == [42, 52, 62]
    summary = pd.read_csv(OUT / "phase03/repeated_seed_summary_tidy.csv")
    for row in summary.itertuples():
        g = reference.loc[reference["mode"] == row.mode]
        if row.client_id != "global":
            g = g.loc[g.client_id == int(row.client_id)]
        assert len(g) == 3
        assert math.isclose(row.mean, g[row.metric].mean(), abs_tol=1e-12)
        assert math.isclose(row.std_ddof1, g[row.metric].std(ddof=1), abs_tol=1e-12)
    diagnostic = json.loads((OUT / "audit/numeric_reproduction.json").read_text())
    assert diagnostic["four_thread_max_state_abs_difference"] == 0
    assert diagnostic["four_thread_prediction_mismatches"] == 0
    assert diagnostic["diagnostic_excluded_from_seed_summary"]
    # Match the headline to all three per-seed observations, not only the mean.
    paired = pd.read_csv(OUT / "phase02/paired_seed_comparisons.csv")
    principal = paired.loc[(paired.subset == "A_unseen_subtype") & (paired.metric == "exact_subtype_accuracy")]
    assert len(principal) == 15 and (principal.local_only == 0).all()
    assert (principal.flower > principal.local_only).all()
    known = paired.loc[(paired.subset == "C_unseen_subtype_known_family") & (paired.metric == "exact_subtype_accuracy")]
    c4 = known.loc[known.client_id == 4].sort_values("seed")
    np.testing.assert_allclose(c4.flower, [0, 65/168, 68/168], atol=1e-12)
    assert (known.loc[known.client_id.isin([1, 2]), "flower"] == 0).all()
    assert known.loc[known.client_id.isin([3, 5]), "flower"].isna().all()
    np.testing.assert_allclose(c4.centralized, [22/168, 36/168, 38/168], atol=1e-12)
    # Verify the narrative's per-subtype attribution from predictions themselves.
    c4mask = masks_for_support(support["original", 4], val.label4)["C_unseen_subtype_known_family"]
    subtypes = ["ddos_ack-frag-flood-port-1883", "ddos_push-ack-flood-port-80", "recon_host-disc-udp-ping"]
    for seed, expected in [(42, [0, 0, 0]), (52, [0, 0, 65]), (62, [8, 0, 60])]:
        prediction = by_id[f"ref_flower_s{seed}"]
        actual = [int(((prediction == y) & c4mask & (y == CLASS_TO_ID[s])).sum()) for s in subtypes]
        assert actual == expected, (seed, actual, expected)
    return {"evaluated_model_records": metrics_checked, "checkpoint_inference_matches": inferred_models,
            "validation_predictions_reproduced": predictions_checked, "matched_reference_arms": 7,
            "predefined_seeds": [42, 52, 62], "fedavg_rounds_audited": fedavg_rounds,
            "fedavg_client_updates_audited": fedavg_updates, "unseen_subset_rows_recomputed": len(detailed),
            "training_allocations_verified": ["original", "balanced", "exclusive"],
            "historical_reference_evaluations": 2, "new_scientific_and_diagnostic_checkpoints": 42}


def source_files():
    candidates = []
    for directory in ["pre_pi_app", "dashboard", "live_pipeline", "hardware_deployment"]:
        candidates.extend((ROOT / directory).rglob("*"))
    candidates.extend(ROOT / "scripts" / name for name in ["28_pre_pi_research.py", "29_feature_readiness.py",
                      "30_hardware_loopback_smoke.py", "31_export_hierarchical_comparisons.py", "32_summarize_pre_pi.py", "33_verify_pre_pi.py", "hcm_eval.py"])
    candidates.extend((ROOT / "tests").glob("test*.py"))
    candidates.extend(ROOT / name for name in ["AGENTS.md", "PROJECT_STATUS.md", "references/proposal.docx",
                      "docs/pi_deployment_readiness.md", "docs/live_feature_compatibility_report.md", "docs/kali_lab_deployment_plan.md"])
    return sorted({p for p in candidates if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"})


def preservation_checks():
    before = json.loads((OUT / "audit/preservation_before.json").read_text())
    changed = []
    for name, digest in before.items():
        assert Path(name).name not in {"test_episode.csv", "test_web_diagnostic.csv"}
        if sha(ROOT / name) != digest:
            changed.append(name)
    assert changed == ["PROJECT_STATUS.md"], changed
    assert sha(OUT / "audit/PROJECT_STATUS_before.md") == before["PROJECT_STATUS.md"]
    return {"historical_files_unchanged": len(before) - 1, "authorized_status_update": changed,
            "status_before_archived": True, "AGENTS_unchanged": True,
            "protected_test_files_outside_read_scope": True,
            "old_manifests_preserved": "Historical manifests retain their original PROJECT_STATUS hash; current mutable status is versioned separately."}


def artifact_checks():
    pngs = list((OUT / "figures").glob("*.png"))
    svgs = list((OUT / "figures").glob("*.svg"))
    assert len(pngs) == len(svgs) == 11
    for p in pngs:
        with Image.open(p) as im:
            im.verify()
    for p in svgs:
        ET.parse(p)
    for path in source_files():
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=str(path))
    jsons = list(OUT.rglob("*.json"))
    for p in jsons:
        json.loads(p.read_text(), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    tests_path = OUT / "unit_test_results_revision_03.json"
    tests = json.loads(tests_path.read_text())
    assert tests["status"] == "passed" and tests["tests_run"] >= 33
    assert not tests["failures"] and not tests["errors"] and not tests["skipped"]
    dashboard = json.loads((OUT / "phase07/server_health.json").read_text())
    assert dashboard["status"] == "passed" and dashboard["http_status"] == 200
    hardware = json.loads((OUT / "phase08/loopback_tls_smoke/verification.json").read_text())
    assert hardware["status"] == "passed" and hardware["successful_updates"] == 4
    assert hardware["tls_enabled"] and hardware["untrusted_ca_rejected"]
    assert not hardware["raspberry_pi_execution"] and not hardware["private_keys_archived"]
    continued = json.loads((OUT / "phase08/loopback_tls_checkpoint_v4/verification.json").read_text())
    assert continued["status"] == "passed" and continued["successful_updates"] == 4
    assert continued["initial_checkpoint_sha256"] == sha(ROOT / "models/subtype_flower_val_v1.pt")
    assert continued["packaged_sources_equal_current_source"] and continued["untrusted_ca_rejected"]
    for name, digest in continued["packaged_source_sha256"].items():
        assert sha(ROOT / "hardware_deployment/app" / name) == digest
    parity = json.loads((OUT / "phase09/offline_fixture_v2/feature_parity_report.json").read_text())
    assert parity["candidate_implemented"] == 53 and parity["original_dataset_semantics_verified_features"] == 0
    assert parity["status"] == "PARTIAL"
    assert "refused" in parity["model_input_guard_result"]
    for name in ["MASTER_REPORT.md", "COMPLETION_CHECKLIST.md", "EXPERIMENT_INDEX.csv",
                 "phase11/Background_and_Related_Work.md", "phase11/Evaluation_Protocol.md", "phase11/Methods.md", "phase11/Results.md",
                 "phase11/Threats_to_Validity.md", "phase11/Presentation_Outline.md", "phase07/DEMO.md"]:
        assert (OUT / name).stat().st_size > 100, name
    hcm = pd.read_csv(OUT / "phase06/hcm_counts_metrics.csv")
    assert len(hcm) == 44 and ((hcm.hcm_tp + hcm.hcm_fn) == 11782).all()
    assert len(pd.read_csv(OUT / "phase06/all_family_metrics.csv")) == 352
    assert len(pd.read_csv(OUT / "phase02/client_unseen_support.csv")) == 15
    for seal_name, archive_name in [("ARTIFACT_MANIFEST.json", "report_revision_02"),
                                     ("ARTIFACT_MANIFEST_revision_02.json", "report_revision_03")]:
        revision = OUT / "audit" / archive_name / "archive_map.json"
        if revision.exists():
            archived = {entry["original_path"]: entry for entry in json.loads(revision.read_text())["files"]}
            original = json.loads((OUT / seal_name).read_text())["files"]
            for name, record in original.items():
                historical = ROOT / (archived[name]["archived_path"] if name in archived else name)
                assert historical.stat().st_size == record["bytes"] and sha(historical) == record["sha256"], ("Historical sealed version lost", seal_name, name)
    return {"png_figures_verified": len(pngs), "svg_figures_verified": len(svgs),
            "json_files_parsed": len(jsons), "unit_tests": tests["tests_run"], "dashboard_health": "passed",
            "two_process_tls_smoke": "passed", "checkpoint_continuation_tls_smoke": "passed",
            "feature_parity_status": "PARTIAL"}


def capture_provenance():
    freeze = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    with (OUT / "requirements.freeze.txt").open("x") as f:
        f.write(freeze)
    dump(OUT / "environment.json", {"python": sys.version, "executable": sys.executable,
         "platform": platform.platform(), "machine": platform.machine(), "cpu_count": __import__("os").cpu_count(),
         "packages": {n: importlib.metadata.version(n) for n in ["flwr", "ray", "torch", "numpy", "pandas", "scikit-learn", "matplotlib", "streamlit", "scapy", "psutil", "pytest"]},
         "freeze_note": "Machine-specific evidence, not a portable ARM lockfile; no system packages installed.",
         "reference_cpu_threads": 1, "historical_reproduction_diagnostic_threads": 4})
    with tarfile.open(OUT / "audit/source_final.tar.gz", "x:gz") as archive:
        for p in source_files():
            archive.add(p, arcname=str(p.relative_to(ROOT)))


def manifest_files(manifest_name="ARTIFACT_MANIFEST.json"):
    paths = [p for p in OUT.rglob("*") if p.is_file() and p != OUT / manifest_name and "__pycache__" not in p.parts]
    return sorted(set(paths + source_files()))


def latest_manifest():
    for name in ["ARTIFACT_MANIFEST_revision_03.json", "ARTIFACT_MANIFEST_revision_02.json", "ARTIFACT_MANIFEST.json"]:
        candidate = OUT / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No sealed manifest")


def verify_manifest(path=None):
    manifest_path = path or latest_manifest()
    manifest = json.loads(manifest_path.read_text())
    for name, record in manifest["files"].items():
        artifact_path = ROOT / name
        assert artifact_path.stat().st_size == record["bytes"] and sha(artifact_path) == record["sha256"], name
    actual = {str(p.relative_to(ROOT)) for p in manifest_files(manifest_path.name)}
    assert actual == set(manifest["files"]), ("Manifest file set changed", actual ^ set(manifest["files"]))
    return len(actual)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seal", action="store_true", help="Create provenance, verification and manifest once; refuses existing final bundle")
    p.add_argument("--seal-correction", action="store_true", help="Seal documented report correction 02 without replacing the original seal/environment")
    p.add_argument("--seal-verifier-fix", action="store_true", help="Seal verifier regression fix 03 while preserving earlier versions")
    args = p.parse_args()
    assert sum([args.seal, args.seal_correction, args.seal_verifier_fix]) <= 1
    creating = args.seal or args.seal_correction or args.seal_verifier_fix
    revision_id = "03" if args.seal_verifier_fix else "02"
    is_revision = args.seal_correction or args.seal_verifier_fix
    manifest_path = OUT / (f"ARTIFACT_MANIFEST_revision_{revision_id}.json" if is_revision else "ARTIFACT_MANIFEST.json")
    verification_path = OUT / (f"verification_revision_{revision_id}.json" if is_revision else "verification.json")
    if is_revision:
        assert (OUT / "ARTIFACT_MANIFEST.json").exists() and (OUT / "audit/report_revision_02/archive_map.json").exists()
        if args.seal_verifier_fix:
            assert (OUT / "ARTIFACT_MANIFEST_revision_02.json").exists() and (OUT / "audit/report_revision_03/archive_map.json").exists()
        assert not manifest_path.exists() and not verification_path.exists(), "Correction already sealed"
    elif args.seal:
        assert not (OUT / "ARTIFACT_MANIFEST.json").exists() and not (OUT / "verification.json").exists(), "Already sealed"
    else:
        assert (OUT / "ARTIFACT_MANIFEST.json").exists(), "Final seal has not been created"
        print(f"Manifest verified: {verify_manifest()} files", flush=True)
    report = {"status": "passed", "verified_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "scientific": scientific_checks(), "preservation": preservation_checks(), "artifacts": artifact_checks(),
              "restrictions": {"no_training_in_verifier": True, "no_protected_test_access": True,
                               "no_external_network_activity": True}}
    if creating:
        if is_revision:
            with tarfile.open(OUT / f"audit/source_final_revision_{revision_id}.tar.gz", "x:gz") as archive:
                for source in source_files():
                    archive.add(source, arcname=str(source.relative_to(ROOT)))
            report["report_correction"] = {"revision": revision_id, "numeric_metrics_predictions_unchanged": True,
                "reason": "C4 attribution corrected in 02; manifest self-exclusion variable fix and regression test in 03",
                "earlier_sealed_versions_preserved": True}
        else:
            capture_provenance()
        dump(verification_path, report)
        files = {str(p.relative_to(ROOT)): {"sha256": sha(p), "bytes": p.stat().st_size} for p in manifest_files(manifest_path.name)}
        dump(manifest_path, {"created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
             "scope": "All versioned research artifacts and selected final source/docs; excludes self and Python bytecode caches",
             "files": files})
        print(f"Sealed and verified: {verify_manifest(manifest_path)} files", flush=True)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
