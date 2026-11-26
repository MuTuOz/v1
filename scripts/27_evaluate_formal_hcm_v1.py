"""Post-hoc Riehl HCM evaluation of immutable validation_v1 predictions.

No training, model inference, raw training data or held-out tests are used.
Default outputs are immutable; use --output-dir for a separate repetition.
Run --mode seal after documentation updates, then --mode verify (read-only).
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile

import numpy as np
import pandas as pd

from hcm_eval import Counts, metrics, project_hierarchy

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "results/formal_hcm_v1"
BUNDLE = ROOT / "results/subtype_flower_val_v1"
PREDICTIONS = {"centralized": BUNDLE / "centralized_recomputed_predictions.csv",
               "flower_fedavg": BUNDLE / "fedavg_predictions.csv"}
METRICS = {"centralized": BUNDLE / "centralized_recomputed_metrics.json",
           "flower_fedavg": BUNDLE / "fedavg_metrics.json"}
SCHEMA_PATH = ROOT / "flower_subtype_app/seniorfl_subtype/schema.json"
VALIDATION = ROOT / "data/validation_v1/validation.csv"
COUNT_KEYS = ("tp", "tn", "fp", "fn")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, obj):
    with path.open("x", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary_path(out):
    return out.with_name(out.name + "_summary.md")


def sum_counts(rows):
    return Counts(*(int(rows[k].sum()) for k in COUNT_KEYS))


def summarize(rows):
    counts = sum_counts(rows)
    return {"samples": len(rows), "counts": counts.to_dict(), "metrics": metrics(counts),
            "hcm_decision_total": sum(counts.values())}


def matrix_frame(df, true_col, pred_col, labels):
    positions = {name: i for i, name in enumerate(labels)}
    a = np.zeros((len(labels), len(labels)), dtype=np.int64)
    np.add.at(a, ([positions[s] for s in df[true_col]], [positions[s] for s in df[pred_col]]), 1)
    return pd.DataFrame(a, index=pd.Index(labels, name="actual"),
                        columns=pd.Index(labels, name="predicted"))


def category(true_subtype, pred_subtype, true_family, pred_family):
    if true_subtype == pred_subtype:
        return "exact_correct"
    if true_family == "benign":
        return "benign_predicted_attack"
    if pred_family == "benign":
        return "attack_predicted_benign"
    if true_family == pred_family:
        return "correct_family_wrong_subtype"
    return "wrong_attack_family"


def evaluate(out, sources):
    out.mkdir(parents=True, exist_ok=True)
    if (out / "comparison.json").exists() or summary_path(out).exists():
        raise FileExistsError("Existing evaluation/report: choose a new --output-dir")
    schema = read_json(SCHEMA_PATH)
    tree, leaves = project_hierarchy(schema)
    if len(leaves) != 84 or len(tree.children) != 93:
        raise ValueError("Unexpected project hierarchy")
    ref = sources / "riehl_reference.py"
    retrieval = read_json(sources / "retrieval.json")
    record = next(r for r in retrieval["records"] if r["file"] == ref.name)
    if sha(ref) != record["sha256"]:
        raise ValueError("Author reference source hash mismatch")
    # Include real tests and exhaustive 84² differential verification in this run.
    test_cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_formal_hcm.py", "-v"]
    test = subprocess.run(test_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out / "unit_tests.log").write_text(test.stdout)
    if test.returncode:
        raise RuntimeError("HCM unit tests failed; see unit_tests.log")
    val = pd.read_csv(VALIDATION, usecols=["label1", "label2", "label4", "episode_id"])
    if len(val) != 6486 or val.label4.nunique() != 28 or val.label2.nunique() != 7:
        raise ValueError("Validation coverage changed")
    if val.label4.map(schema["family_of"]).tolist() != val.label2.tolist():
        raise ValueError("Ground-truth taxonomy mismatch")
    classes = schema["classes"]
    grouped_classes = ["benign"] + sorted(classes[1:], key=lambda c: (schema["family_of"][c], c))
    family_labels = ["benign"] + sorted(set(schema["family_of"].values()) - {"benign"})
    all_pairs = {}
    pair_rows = []
    for actual in classes:
        for predicted in classes:
            c = tree.contribution(leaves[actual], leaves[predicted])
            transitive = tree.contribution(leaves[actual], leaves[predicted], transitive_sensitivity=True)
            all_pairs[actual, predicted] = c, transitive.tn
            pair_rows.append({"actual_subtype": actual, "predicted_subtype": predicted,
                              **c.to_dict(), "tn_transitive_sensitivity": transitive.tn})
    pd.DataFrame(pair_rows).to_csv(out / "all_7056_leaf_pair_contributions.csv", index=False)
    coverage = pd.DataFrame({"subtype": classes, "family": [schema["family_of"][s] for s in classes],
                             "validation_support": [int((val.label4 == s).sum()) for s in classes],
                             "leaf_depth": [len(tree.paths[leaves[s]]) - 1 for s in classes]})
    coverage.to_csv(out / "class_coverage.csv", index=False)
    write_json(out / "hierarchy.json", {"root": tree.root, "nodes": len(tree.children),
               "leaves": len(leaves), "edges": [[p, c] for c, p in tree.parents.items()],
               "class_to_leaf": leaves, "allocation_paths": {s: tree.paths[n] for s, n in leaves.items()}})
    inputs = [SCHEMA_PATH, VALIDATION, *PREDICTIONS.values(), *METRICS.values(),
              sources / "riehl_reference.py", sources / "riehl_commit.json", sources / "retrieval.json"]
    input_hashes = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    write_json(out / "config.json", {"experiment": "formal_hcm_v1", "type": "post-hoc evaluation; no new training",
               "scope": "tree / single path / mandatory leaf prediction",
               "primary_tn": "author reference: sibling union + immediate children at common-path terminal",
               "sensitivity_tn": "transitive descendants at common-path terminal; not primary reference HCM",
               "root_in_tp": False, "benign_depth": 1, "attack_leaf_depth": 3,
               "aggregation": "sum sample HCM counts, then binary formulas (micro)",
               "zero_denominator": "null", "taxonomy_pruned_for_coverage": False,
               "validation_samples": 6486, "observed_leaf_classes": 28, "absent_leaf_classes": 56,
               "source_commit": read_json(sources / "riehl_commit.json")["commit"],
               "input_sha256": input_hashes, "test_command": test_cmd,
               "seed": None, "seed_note": "Deterministic evaluation of existing seed-42 model predictions",
               "sources_dir": str(sources), "output_dir": str(out)})
    comparison = {}
    matrices = {}
    crosschecks = {}
    for model, pred_path in PREDICTIONS.items():
        df = pd.read_csv(pred_path)
        if len(df) != len(val) or df.validation_row.tolist() != list(range(len(val))):
            raise ValueError("Prediction row IDs do not align with validation")
        for pc, vc in [("true_subtype", "label4"), ("true_family", "label2"), ("episode_id", "episode_id")]:
            if df[pc].tolist() != val[vc].tolist():
                raise ValueError(f"Prediction/validation mismatch in {model}: {pc}")
        for prefix in ["true", "predicted"]:
            labels = df[f"{prefix}_subtype"].tolist()
            if any(s not in leaves for s in labels):
                raise ValueError("Unknown predicted class")
            if [schema["family_of"][s] for s in labels] != df[f"{prefix}_family"].tolist():
                raise ValueError("Prediction family mapping mismatch")
            if [classes[i] for i in df[f"{prefix}_subtype_id"]] != labels:
                raise ValueError("Prediction class ID mismatch")
        rows = df[["validation_row", "true_subtype", "predicted_subtype", "true_family", "predicted_family", "episode_id"]].copy()
        counts = [all_pairs[t, p] for t, p in zip(df.true_subtype, df.predicted_subtype)]
        for k in COUNT_KEYS:
            rows[k] = [getattr(c, k) for c, _ in counts]
        rows["tn_transitive_sensitivity"] = [n for _, n in counts]
        rows["legacy_error_category"] = [category(*args) for args in zip(df.true_subtype, df.predicted_subtype, df.true_family, df.predicted_family)]
        if rows.legacy_error_category.tolist() != df.hierarchical_category.tolist():
            raise ValueError("Legacy categories changed")
        rows.to_csv(out / f"{model}_sample_hcm.csv", index=False)
        overall = summarize(rows)
        attack_only = summarize(rows[rows.true_family != "benign"])
        sensitivity = Counts(overall["counts"]["tp"], int(rows.tn_transitive_sensitivity.sum()),
                             overall["counts"]["fp"], overall["counts"]["fn"])
        result = {"all_validation": overall, "attack_truth_only": attack_only,
                  "transitive_tn_sensitivity_not_primary": {"counts": sensitivity.to_dict(), "metrics": metrics(sensitivity)}}
        write_json(out / f"{model}_hcm_metrics.json", result)
        comparison[model] = result
        for grouping, labels in [("true_family", family_labels), ("true_subtype", grouped_classes)]:
            records = []
            for label in labels:
                subset = rows[rows[grouping] == label]
                s = summarize(subset)
                records.append({grouping: label, "samples": s["samples"], **s["counts"], **s["metrics"]})
            pd.DataFrame(records).to_csv(out / f"{model}_hcm_by_{grouping}.csv", index=False)
        legacy = rows.legacy_error_category.value_counts().to_dict()
        saved = read_json(METRICS[model])
        if legacy != saved["hierarchical_error_breakdown"]:
            raise ValueError("Legacy count totals differ")
        pd.DataFrame([{"category": label, "sample_count": len(g), **sum_counts(g).to_dict()}
                      for label, g in rows.groupby("legacy_error_category")]).to_csv(out / f"{model}_legacy_categories_with_hcm.csv", index=False)
        correct = int((df.true_subtype == df.predicted_subtype).sum())
        if correct / 6486 != saved["exact_subtype_accuracy"]:
            raise ValueError("Flat subtype accuracy does not reproduce saved metric")
        # Riehl TP+FN is the true path depth summed over examples: 3838 + 3*2648.
        if overall["counts"]["tp"] + overall["counts"]["fn"] != 11782:
            raise ValueError("True allocation-path depth identity failed")
        df["true_detection"] = np.where(df.true_family == "benign", "benign", "attack")
        df["predicted_detection"] = np.where(df.predicted_family == "benign", "benign", "attack")
        matrices[model] = {}
        for level, labels, tc, pc in [("detection", ["benign", "attack"], "true_detection", "predicted_detection"),
                                       ("family", family_labels, "true_family", "predicted_family"),
                                       ("subtype", grouped_classes, "true_subtype", "predicted_subtype")]:
            matrix = matrix_frame(df, tc, pc, labels)
            matrices[model][level] = matrix
            matrix.to_csv(out / f"{model}_{level}_confusion_counts.csv")
            matrix.div(matrix.sum(axis=1).replace(0, np.nan), axis=0).to_csv(out / f"{model}_{level}_row_normalized.csv")
            if int(matrix.to_numpy().sum()) != 6486:
                raise ValueError("Multi-resolution confusion sample total failed")
        # Reaggregate all 84 leaves to recover each displayed upper-level matrix.
        leaf_cm = matrices[model]["subtype"]
        regrouped = leaf_cm.groupby(lambda s: schema["family_of"][s]).sum()
        regrouped = regrouped.T.groupby(lambda s: schema["family_of"][s]).sum().T
        pd.testing.assert_frame_equal(regrouped.reindex(index=family_labels, columns=family_labels),
                                      matrices[model]["family"], check_names=False)
        c = overall["counts"]
        pd.DataFrame([[c["tp"], c["fn"]], [c["fp"], c["tn"]]],
                     index=["actual_positive", "actual_negative"],
                     columns=["predicted_positive", "predicted_negative"]).to_csv(out / f"{model}_formal_hcm_2x2.csv")
        crosschecks[model] = {"aligned_validation_rows": len(df), "flat_accuracy_reproduced": True,
                             "legacy_categories_reproduced": True, "legacy_category_total": sum(legacy.values()),
                             "tp_plus_fn_equals_true_path_depth_sum": c["tp"] + c["fn"],
                             "hcm_decision_total": overall["hcm_decision_total"],
                             "family_matrix_recovers_from_subtype_matrix": True}
    write_json(out / "comparison.json", comparison)
    pd.DataFrame([{"model": model, "population": pop, **comparison[model][pop]["counts"],
                    **comparison[model][pop]["metrics"]} for model in comparison
                   for pop in ["all_validation", "attack_truth_only"]]).to_csv(out / "comparison.csv", index=False)
    pd.DataFrame([{"metric": k, "centralized": comparison["centralized"]["all_validation"]["metrics"][k],
                    "flower_fedavg": comparison["flower_fedavg"]["all_validation"]["metrics"][k],
                    "flower_minus_centralized": comparison["flower_fedavg"]["all_validation"]["metrics"][k] - comparison["centralized"]["all_validation"]["metrics"][k]}
                  for k in metrics(Counts(1, 1, 1, 1))]).to_csv(out / "metric_differences.csv", index=False)
    write_json(out / "validation_checks.json", {"models": crosschecks, "unit_tests_passed": True,
               "exhaustive_author_reference_leaf_pairs": 7056,
               "validation_data_read": "validation.csv metadata only",
               "training_data_or_test_sets_read": False, "model_inference_or_training_executed": False})
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
    (out / "requirements.freeze.txt").write_text(freeze.stdout)
    write_json(out / "environment.json", {"python": sys.version, "executable": sys.executable,
               "platform": platform.platform(), "packages": {n: importlib.metadata.version(n) for n in
                 ["numpy", "pandas", "matplotlib", "networkx", "pypdf"]},
               "utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    features = schema["features"]
    pd.DataFrame([{"index": i, "feature": f, "source_type": "application/device log" if f.startswith("log_") else "packet capture",
                   "parity_status": "future: requires extraction definition and golden-window verification"}
                  for i, f in enumerate(features)]).to_csv(out / "future_testbed_feature_parity_inventory.csv", index=False)
    figures(out, comparison, matrices, coverage, schema)
    interactive(out, matrices, schema)
    make_report(out, comparison, schema)
    print(json.dumps(comparison, indent=2), flush=True)


def figures(out, comparison, matrices, coverage, schema):
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/seniorproject-formal-hcm-matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.patches import Rectangle
    plt.rcParams.update({"font.size": 10, "svg.fonttype": "none"})

    def save(fig, name):
        fig.tight_layout()
        for ext in ["png", "svg"]:
            fig.savefig(out / f"{name}.{ext}", dpi=190, bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))
    for ax, model in zip(axes, comparison):
        c = comparison[model]["all_validation"]["counts"]
        a = np.array([[c["tp"], c["fn"]], [c["fp"], c["tn"]]])
        ax.imshow(a, cmap="Blues", norm=Normalize(0, max(a.max(), 1)))
        for i, j, name in [(0, 0, "TP_H"), (0, 1, "FN_H"), (1, 0, "FP_H"), (1, 1, "TN_H")]:
            ax.text(j, i, f"{name}\n{a[i,j]:,}", ha="center", va="center", fontsize=14,
                    color="white" if a[i,j] > a.max() * .55 else "black")
        ax.set_xticks([0, 1], ["Positive", "Negative"]); ax.set_yticks([0, 1], ["Positive", "Negative"])
        ax.set(xlabel="Predicted decision", ylabel="Actual decision", title=model)
    fig.suptitle("Formal Riehl HCM: node/decision contributions, not sample counts", fontsize=12)
    save(fig, "formal_hcm_counts")
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    for row, model in enumerate(comparison):
        for col, level in enumerate(["detection", "family"]):
            ax = axes[row, col]; cm = matrices[model][level]
            a = cm.to_numpy(); support = a.sum(axis=1)
            norm = np.divide(a, support[:, None], out=np.full(a.shape, np.nan), where=support[:, None] != 0)
            cmap = plt.get_cmap("Blues").copy(); cmap.set_bad("#dddddd")
            ax.imshow(np.ma.masked_invalid(norm), cmap=cmap, vmin=0, vmax=1)
            labels = cm.columns.tolist()
            ax.set_xticks(range(len(cm)), labels, rotation=40, ha="right")
            ax.set_yticks(range(len(cm)), [f"{s} (n={n})" for s, n in zip(labels, support)])
            for i in range(len(cm)):
                for j in range(len(cm)):
                    text = f"{a[i,j]}\n{norm[i,j]:.1%}" if support[i] else "N/A"
                    ax.text(j, i, text, ha="center", va="center", fontsize=8 if col else 11,
                            color="white" if support[i] and norm[i,j] > .55 else "black")
            ax.set(title=f"{model}: {level}", xlabel="Predicted", ylabel="Actual")
    fig.suptitle("Neo-inspired multiresolution view: counts and P(predicted | actual)\nEach panel sums to 6,486 samples; grey = no actual support", fontsize=12)
    save(fig, "neo_detection_family")
    fig, axes = plt.subplots(1, 2, figsize=(25, 11), sharey=True)
    for ax, model in zip(axes, comparison):
        cm = matrices[model]["subtype"]; cm = cm.loc[cm.sum(axis=1) > 0]
        norm = cm.div(cm.sum(axis=1), axis=0)
        ax.imshow(norm, vmin=0, vmax=1, cmap="Blues", aspect="auto")
        ax.set_xticks(range(84), cm.columns, rotation=90, fontsize=5)
        ax.set_yticks(range(len(cm)), [f"{s} (n={int(n)})" for s, n in zip(cm.index, cm.sum(axis=1))], fontsize=7)
        for axis, labels in [("x", list(cm.columns)), ("y", list(cm.index))]:
            last = None
            for i, subtype in enumerate(labels):
                family = schema["family_of"][subtype]
                if last is not None and last != family:
                    (ax.axvline if axis == "x" else ax.axhline)(i - .5, color="#444444", lw=.8)
                last = family
        ax.set(title=model, xlabel="Predicted subtype: all 84, grouped by family", ylabel="Actual subtype: 28 observed")
    fig.suptitle("Neo-inspired leaf view: P(predicted subtype | actual subtype)\n56 zero-support actual rows omitted; every predicted class retained; family boundaries shown")
    save(fig, "neo_grouped_subtypes")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    labels = ["precision", "recall", "f1", "accuracy", "mcc"]
    for ax, pop in zip(axes, ["all_validation", "attack_truth_only"]):
        x = np.arange(len(labels))
        for offset, model in [(-.2, "centralized"), (.2, "flower_fedavg")]:
            bars = ax.bar(x + offset, [comparison[model][pop]["metrics"][k] for k in labels], .4, label=model)
            ax.bar_label(bars, fmt="%.3f", fontsize=8)
        ax.set_xticks(x, labels, rotation=15); ax.set_ylim(0, 1.1); ax.legend(fontsize=8)
        ax.set(title=pop, ylabel="HCM metric (micro, 0–1)")
    save(fig, "hierarchical_metric_comparison")
    families = sorted(set(schema["family_of"].values()) - {"benign"})
    fig, ax = plt.subplots(figsize=(15, 6)); ax.set_xlim(-1, 7); ax.set_ylim(-.3, 3.9); ax.axis("off")
    def box(x, y, text, color="#e7f0f8", width=1):
        ax.add_patch(Rectangle((x-width/2, y-.25), width, .5, facecolor=color, edgecolor="#444"))
        ax.text(x, y, text, ha="center", va="center", fontsize=9)
    box(3, 3.4, "Root"); box(1, 2.4, "Benign\nn=3,838", width=1.4); box(4, 2.4, "Attack\nn=2,648", width=1.4)
    ax.plot([3,1], [3.15,2.65], color="#666"); ax.plot([3,4], [3.15,2.65], color="#666")
    for i, family in enumerate(families):
        group = coverage[coverage.family == family]
        n = int(group.validation_support.sum()); observed = int((group.validation_support > 0).sum())
        ax.plot([4,i], [2.15,1.65], color="#888"); box(i, 1.4, f"{family}\nn={n}", color="#dddddd" if not n else "#e7f0f8")
        ax.plot([i,i], [1.15,.65], color="#888")
        box(i, .4, f"{len(group)} subtypes\n{observed} observed", width=1.05)
    ax.text(3, -.1, "Benign is a depth-1 leaf; attack subtypes are depth-3 leaves. No padding nodes.\nAll 84 leaves remain in the HCM taxonomy, including the 56 absent from validation.", ha="center", fontsize=10)
    ax.set_title("Evaluation taxonomy and actual validation support (subtype leaves grouped for display)")
    save(fig, "hierarchy_coverage")


def interactive(out, matrices, schema):
    """Small offline drilldown, inspired by Neo; not an implementation of Neo."""
    payload = {m: {level: {"labels": list(cm.columns), "counts": cm.to_numpy().tolist()}
                   for level, cm in levels.items()} for m, levels in matrices.items()}
    html = '''<!doctype html><meta charset="utf-8"><title>HCM validation exploration</title>
<style>body{font:15px system-ui;margin:24px}select{margin:8px}table{border-collapse:collapse}th,td{padding:7px;border:1px solid #ccc;font-size:12px}th{max-width:150px;word-break:break-word}#wrap{max-height:75vh;overflow:auto}td{min-width:50px;text-align:center}</style>
<h1>Validation confusion explorer</h1><p>Neo-inspired level selection and conditioning; a separate diagnostic from the formal Riehl 2×2 HCM. No external scripts or network requests.</p>
<label>Model<select id="model"><option>centralized</option><option>flower_fedavg</option></select></label>
<label>Level<select id="level"><option>family</option><option>detection</option><option>subtype</option></select></label>
<label>Values<select id="norm"><option value="row">P(predicted | actual)</option><option value="count">Counts</option><option value="joint">Joint P(actual,predicted)</option></select></label>
<label>Actual-family filter<select id="family"><option value="all">All</option>FAMILIES</select></label>
<p id="note"></p><div id="wrap"></div><script>const data=PAYLOAD;const families=MAPPING;
const ids=['model','level','norm','family'];const get=id=>document.getElementById(id);function render(){const m=get('model').value,l=get('level').value,n=get('norm').value,f=get('family').value,d=data[m][l];let rows=d.counts.map((a,i)=>({a,label:d.labels[i]}));
if(f!=='all'&&l!=='detection')rows=rows.filter(r=>(l==='family'?r.label:families[r.label])===f);let total=rows.reduce((s,r)=>s+r.a.reduce((a,b)=>a+b,0),0);let t=document.createElement('table'),header=t.insertRow();let corner=document.createElement('th');corner.textContent='Actual ↓ / Predicted →';header.append(corner);d.labels.forEach(v=>{let h=document.createElement('th');h.textContent=v;header.append(h)});
rows.forEach(r=>{let row=t.insertRow(),h=document.createElement('th'),support=r.a.reduce((a,b)=>a+b,0);h.textContent=r.label+' (n='+support+')';row.append(h);r.a.forEach(v=>{let c=row.insertCell(),p=n==='row'?(support?v/support:null):n==='joint'?(total?v/total:null):v;c.textContent=p===null?'N/A':n==='count'?v:(100*p).toFixed(2)+'%';c.title='Count: '+v;c.style.background=p===null?'#ddd':`rgba(30,110,190,${n==='count'?(total?v/total:0):p})`;})});get('wrap').replaceChildren(t);get('note').textContent='Displayed actual support: '+total+'. Row normalization retains all predicted columns; joint normalization conditions on the selected actual subset. Zero-support rows are N/A. Detection ignores family filter.';}
ids.forEach(id=>get(id).addEventListener('change',render));render();</script>'''
    options = "".join(f'<option>{f}</option>' for f in ["benign"] + sorted(set(schema["family_of"].values()) - {"benign"}))
    html = html.replace("FAMILIES", options).replace("PAYLOAD", json.dumps(payload)).replace("MAPPING", json.dumps(schema["family_of"]))
    (out / "confusion_explorer.html").write_text(html, encoding="utf-8")


def make_report(out, comparison, schema):
    prefix = out.name
    lines = ["# Formal Riehl HCM — validation_v1", "", "## Kapsam ve kaynaklar", "",
      "Bu çalışma, mevcut 84 sınıflı Merkezi ve Flower FedAvg modellerinin kayıtlı 6.486 doğrulama tahminlerinin sonradan değerlendirmesidir. Eğitim ve model çıkarımı çalıştırılmadı. Yalnız `data/validation_v1/validation.csv` etiket/episode metadata'sı, kayıtlı tahminler ve eğitimden türetilmiş şema okundu. Korunan test kümeleri açılmadı.", "",
      "Riehl, Neunteufel ve Hemberg (2023), *Hierarchical confusion matrix for classification performance evaluation*, JRSS Series C 72(5), 1394–1412, [DOI](https://doi.org/10.1093/jrsssc/qlad057), §4.1 Denklem (4) ve §4 Denklem (3). Yerelde makale yoktu; [yayıncı kaydı](https://academic.oup.com/jrsssc/article/72/5/1394/7217007), [arXiv ön baskısı](https://arxiv.org/abs/2306.09461) ve [yazar kodu](https://github.com/DerKevinRiehl/HierarchicalConfusionMatrix) incelendi. Kod commit'i: `2256f4c24b813ffb752a53e20a8092ec7b1e3ac3`. PDF, incelenen referans kodu, URL ve SHA-256 kayıtları `sources/` altında saklandı. Yayıncı HTML doğrudan indirmesi 403 verdi; doğrulanmış web kaydı ve arXiv PDF kullanıldı.", "",
      "Görtler ve diğerleri (2022), *Neo: Generalizing Confusion Matrix Visualization to Hierarchical and Multi-Output Labels*, CHI ’22, [DOI](https://doi.org/10.1145/3491102.3501823), [arXiv v2](https://arxiv.org/abs/2110.12536v2), [Apple yayın kaydı](https://machinelearning.apple.com/research/generalizing-confusion-matrix). Neo, çok seviyeli matrislerin gösterimi ve normalizasyonu için dayanak alındı; Riehl'in TP/TN/FP/FN tanımlarının kaynağı değildir. Buradaki statik ve çevrimdışı görseller Neo'dan esinlenir; Neo sisteminin tam uygulaması oldukları iddia edilmez.", "",
      "## Hiyerarşi ve varsayımlar", "", "```text", "Root", "├── Benign (yaprak)", "└── Attack", "    └── 7 saldırı ailesi", "        └── 83 saldırı alt türü (yapraklar)", "```", "",
      "Toplam 93 düğüm, 92 kenar ve 84 yaprak vardır. Problem ağaç / tek tahmin yolu / zorunlu yaprak tahminidir (T, SPL, MLNP). Benign yolu 1, saldırı yaprağı yolu 3 kenardır; benign için yapay aile/alt tür düğümü eklenmez. Kök TP sayılmaz. Tüm 84 eğitim sınıfı hiyerarşide tutulur; doğrulamada görülmeyen sınıflar budanmaz. DAG, çok etiketli ve iç düğümde duran tahminler bu uygulamanın kapsamı dışındadır.", "",
      "## Matematiksel tanımlar", "",
      "T gerçek kök→yaprak yolu, P tahmin yolu, C ortak en uzun başlangıç yolu, z bu ortak yolun son düğümü ve R kök olsun. N(v) kardeş düğümlerdir. Yazar koduyla uyumlu D₁(z) doğrudan çocuklar kümesidir. Her örnek için:", "",
      "- TP_H = |(T ∩ P) \\ {R}|", "- FP_H = |P \\ T|", "- FN_H = |T \\ P|", "- TN_H = |(⋃[v∈C] N(v)) \\ T| + |D₁(z) \\ (T ∪ P)|", "",
      "Denklem (3) uyarınca dört sayı örnekler üzerinden ayrı ayrı toplanır. Ana sonuçlar bu toplamların mikro ölçütleridir: precision=TP/(TP+FP), recall=TP/(TP+FN), F1=2TP/(2TP+FP+FN), accuracy=(TP+TN)/(TP+TN+FP+FN), specificity=TN/(TN+FP), FPR=FP/(FP+TN), FNR=FN/(TP+FN), MCC=(TP·TN−FP·FN)/√((TP+FP)(TP+FN)(TN+FP)(TN+FN)). Tanımsız paydalar JSON null / boş CSV hücresidir. Makale Tablo 2'de FNR'nin payında görünen FP yazım hatası taşınmadı; FN kullanılır.", "",
      "**TN yorumunun sınırı:** Makale metni D için ‘descendants’ sözcüğünü kullanırken, sabitlenen yazar kodunun `getDescendants` fonksiyonu yalnız `graph.neighbors` (doğrudan çocuklar) döndürür; `getNeighbors` kardeşleri döndürür. Ana sonuç yazar kodu ve Şekil 4a'nın (3,5,0,0), (2,4,1,1), (1,2,2,2) örnekleriyle eşleşen bu operasyonel yorumu izler. Bütün geçişli alt düğümleri TN saymak aynı sayıları vermez. Belirsizlik gizlenmedi: sadece D₁ yerine geçişli D⁺ kullanan ayrı TN duyarlılık sonucu JSON'da saklandı; bu varyant ana Riehl referans sonucu değildir. TP/FP/FN ve precision/recall/F1 bu değişiklikten etkilenmez.", "",
      "HCM 2×2 düzeni `[[TP_H,FN_H],[FP_H,TN_H]]`: satır gerçek karar, sütun tahmin edilen karar. Bunlar örnek sayısı değil, örneklerin düğüm/karar katkılarıdır. TP+TN+FP+FN toplamının 6.486 olması beklenmez; TP+FN tüm modellerde gerçek yol uzunlukları toplamı olan **3838 + 3×2648 = 11782** olmalıdır.", "",
      "Mevcut beş ayrık örnek hata kategorisi ayrı bir teşhis özetidir ve formal HCM değildir. `*_legacy_categories_with_hcm.csv` bu ayrımı koruyarak kategori içindeki HCM katkılarını gösterir. Düz alt tür doğruluğu ve önceki sınıf Makro F1 de HCM ölçütleriyle değiştirilmedi.", "",
      "## Sonuçlar", "", "HCM sayımları ve mikro ölçütleri (0–1 ölçeği):", "", "| Ölçüt | Merkezi | Flower FedAvg |", "|---|---:|---:|"]
    for k in COUNT_KEYS:
        lines.append(f'| {k.upper()}_H | {comparison["centralized"]["all_validation"]["counts"][k]} | {comparison["flower_fedavg"]["all_validation"]["counts"][k]} |')
    for k in metrics(Counts(1,1,1,1)):
        lines.append(f'| HCM {k} | {comparison["centralized"]["all_validation"]["metrics"][k]:.12f} | {comparison["flower_fedavg"]["all_validation"]["metrics"][k]:.12f} |')
    lines += ["", "Tam hassasiyetli sayılar `comparison.json` ve `comparison.csv` içinde. Yalnız gerçek saldırı örnekleri (n=2648) için ek tanı:", "", "| HCM ölçütü | Merkezi | Flower FedAvg |", "|---|---:|---:|"]
    for k in ["precision", "recall", "f1"]:
        lines.append(f'| {k} | {comparison["centralized"]["attack_truth_only"]["metrics"][k]:.12f} | {comparison["flower_fedavg"]["attack_truth_only"]["metrics"][k]:.12f} |')
    lines += ["", "Bu saldırı alt kümesi, benign örneklerdeki yanlış alarmları içermez; tam doğrulama sonuçlarının yerine geçmez. HCM recall, düz saldırı tespit recall'u değildir. Kısa benign ve uzun saldırı yolları farklı pozitif karar sayısı üretir; yüksek aile dal sayıları TN'yi etkiler. HCM accuracy/specificity bu nedenle düz kayıt doğruluğu veya operasyonel yanlış alarm oranıyla eşanlamlı değildir.", "",
      "## Görseller", "", f"![Hiyerarşi]({prefix}/hierarchy_coverage.png)", "", f"![Formal HCM]({prefix}/formal_hcm_counts.png)", "", f"![Çok seviyeli matris]({prefix}/neo_detection_family.png)", "", f"![HCM karşılaştırması]({prefix}/hierarchical_metric_comparison.png)", "",
      f"[Alt tür matrisi]({prefix}/neo_grouped_subtypes.png): 28 gerçek sınıf × 84 tahmin sınıfı, aile sınırları gösterilir. [Çevrimdışı gezgin]({prefix}/confusion_explorer.html) model, seviye, gerçek aile filtresi ve normalizasyon seçer; dış ağa istek yapmaz. Her seviyedeki sayım matrisi aynı 6486 örneği toplar. Satır normalizasyonu P(tahmin|gerçek), toplam normalizasyon P(gerçek,tahmin) verir. Desteksiz web satırı N/A'dır; görsel olarak sıfır başarı gibi yorumlanmaz. Bütün statik şekiller PNG ve SVG'dir.", "",
      "## Testler ve tutarlılık", "",
      "El hesabına dayalı testler: tam saldırı tahmini, tam benign tahmini, doğru aile/yanlış alt tür, yanlış saldırı ailesi, saldırı→benign ve benign→saldırı. Ayrıca makalenin Şekil 4a örnekleri, TN'nin tüm off-path düğümler olmadığının kontrolü, metrik/tanımsız payda kontrolleri ve geçersiz hiyerarşi/tahmin reddi var. **84×84 = 7056 olası yaprak çifti** sabitlenen yazar koduyla birebir karşılaştırılır. Log: `unit_tests.log`.", "",
      "Tahmin satırları, ID'ler, aile eşlemesi ve episode metadata'sı doğrulamayla hizalandı; eski alt tür doğruluğu ve beş kategori sayısı aynen yeniden üretildi. Aile matrisi alt tür matrisinden tekrar birleştirilerek kontrol edildi. Her örneğin HCM katkıları, bütün yaprak çifti tablosu, aile/alt tür destekleri ve metrikleri CSV'dedir. `validation_checks.json`, son `verification.json` ve SHA-256 manifesti sayısal/bütünlük kontrollerini kaydeder.", "",
      "## Sınırlılıklar ve yorum", "",
      "- Doğrulama yalnız 28/84 alt tür ve 7/8 aileyi kapsar; **56 sınıf ve web ailesi yoktur**. Tam hiyerarşinin TN hesabında tutulmaları, bu sınıfların test edildiği anlamına gelmez.",
      "- Episode ID'leri sezgisel aday gruplardır; bağımsız oturum kanıtı değildir. Benign zamansal holdout'tur. Bağımsız oturum değerlendirmesi veya tam 84 sınıf kapsamı iddia edilmez.",
      "- Tek tohumlu önceki modellerin sabit tahminleri kullanıldı. Yeni yerel modeller, tekrarlı tohumlar, sınıf dengesizliği müdahaleleri veya istatistiksel anlamlılık analizi yapılmadı.",
      "- HCM kısmi doğru yolları ödüllendirir; benign çoğunluğu ve ağaç şekli toplamlara etki eder. TP/FP/FN/F1 ile birlikte düz saldırı recall'u, benign FPR ve sınıf raporlarını okumak gerekir. Bu sonuçlar doğrudan dağıtım güvenliği veya genellenebilir üstünlük kanıtı değildir.",
      "- Ana TN yazar referansının doğrudan çocuk yorumudur; geçişli alt düğüm duyarlılığı ayrı raporlandı. Kapsam T/SPL/MLNP'dir; genelleştirilmiş DAG/çok etiket HCM testi yapılmadı.",
      "- Flower sonuçları simülasyondan gelir. Bu görevde Raspberry Pi, Kali VM, canlı saldırı, trafik yakalama veya ağ ayarı çalıştırılmadı. Gelecek tasarım `docs/pi_kali_fl_testbed_design.md` içindedir.", "",
      "## Yeniden üretim", "", "```bash", "/home/seniorfl/seniorproject-fl-venv/bin/python -m unittest discover -s tests -p 'test_formal_hcm.py' -v", "/home/seniorfl/seniorproject-fl-venv/bin/python scripts/27_evaluate_formal_hcm_v1.py --mode verify", "# Ayrı sonuç dizinine yeni değerlendirme (mevcut sonuçlar korunur):", "/home/seniorfl/seniorproject-fl-venv/bin/python scripts/27_evaluate_formal_hcm_v1.py --output-dir results/formal_hcm_v1_repeat", "```", "",
      "Yeni değerlendirme yalnız kayıtlı girdileri okur; aynı hedefte önceki değerlendirmeyi ezmez. `--mode seal` son kaynak/belge arşivini ve manifesti bir kez oluşturur; `--mode verify` salt okunurdur. İndirilen kaynaklar, URL/commit/hash kaydı, tam bağımlılık dökümü ve çalıştırma yapılandırması sonuç dizinindedir. PROJECT_STATUS.md değişmeden önce yedeği alındı; diğer eski kaynak/veri/model/sonuçların hash'leri korunma manifestiyle denetlenir.", ""]
    position = lines.index("## Görseller")
    lines[position:position] = interpretation_tables(comparison)
    with summary_path(out).open("x", encoding="utf-8") as f:
        f.write("\n".join(lines))


def interpretation_tables(comparison):
    lines = ["## TN yorumuna duyarlılık", "",
             "Aşağıdaki alternatif yalnız ortak yolun son düğümündeki D₁ kümesini geçişli D⁺ ile değiştirir; kardeşlik tanımı sabittir. Ana sonuç değildir. Bu farkın accuracy/MCC üzerindeki etkisi, TN yorumunun niçin açıkça sabitlendiğini gösterir.", "",
             "| Model | Ana TN | Geçişli TN (duyarlılık) | Ana accuracy | Geçişli accuracy |", "|---|---:|---:|---:|---:|"]
    for model, result in comparison.items():
        primary = result["all_validation"]
        other = result["transitive_tn_sensitivity_not_primary"]
        lines.append(f'| {model} | {primary["counts"]["tn"]} | {other["counts"]["tn"]} | {primary["metrics"]["accuracy"]:.12f} | {other["metrics"]["accuracy"]:.12f} |')
    lines += ["", "## El hesabı test örnekleri", "",
              "Küçük test ağacında Root→Benign ve Root→Attack→{A,B} vardır; A'nın iki, B'nin üç alt türü bulunur. Sıra (TP,TN,FP,FN) olarak:", "",
              "| Gerçek → tahmin | TP | TN | FP | FN |", "|---|---:|---:|---:|---:|",
              "| a1 → a1 | 3 | 3 | 0 | 0 |", "| benign → benign | 1 | 1 | 0 | 0 |",
              "| a1 → a2 (aynı aile) | 2 | 2 | 1 | 1 |", "| a1 → b1 (farklı aile) | 1 | 1 | 2 | 2 |",
              "| a1 → benign | 0 | 0 | 1 | 3 |", "| benign → a1 | 0 | 0 | 3 | 1 |", "",
              "Bu tablo gerçek deney sayıları değildir; formal tanımların birim testindeki el hesabıdır. Kaynak künyeleri ve erişim kayıtları: `sources/REFERENCES.md`, `sources/references.bib`, `sources/retrieval.json`.", ""]
    return lines


def seal(out):
    if (out / "artifact_manifest.json").exists():
        raise FileExistsError("Artifact manifest already sealed")
    before_path = out / "preservation_before.json"
    before = read_json(before_path) if before_path.exists() else {}
    changed = [n for n, h in before.items() if sha(ROOT / n) != h]
    if set(changed) - {"PROJECT_STATUS.md"}:
        raise RuntimeError(f"Historical artifacts changed: {changed}")
    content_checks = verify_content(out)
    source_files = [ROOT / "scripts/hcm_eval.py", Path(__file__).resolve(), ROOT / "tests/test_formal_hcm.py",
                    ROOT / "docs/pi_kali_fl_testbed_design.md", ROOT / "PROJECT_STATUS.md"]
    with tarfile.open(out / "final_source_and_docs.tar.gz", "x:gz") as archive:
        for p in source_files:
            archive.add(p, arcname=str(p.relative_to(ROOT)))
    write_json(out / "verification.json", {"status": "passed", "historical_files_checked": len(before),
               "allowed_document_update": changed, "historical_experiment_changes": [],
               "test_log": "unit_tests.log", "validation_checks": read_json(out / "validation_checks.json"),
               "output_content_checks": content_checks,
               "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    files = [p for p in out.rglob("*") if p.is_file() and "__pycache__" not in p.parts] + source_files + [summary_path(out)]
    write_json(out / "artifact_manifest.json", {str(p.relative_to(ROOT)): {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(set(files))})
    verify(out)


def verify(out):
    manifest = read_json(out / "artifact_manifest.json")
    for name, record in manifest.items():
        p = ROOT / name
        if not p.is_file() or sha(p) != record["sha256"] or p.stat().st_size != record["bytes"]:
            raise RuntimeError(f"Artifact changed: {name}")
    config = read_json(out / "config.json")
    for name, digest in config["input_sha256"].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError(f"Input changed: {name}")
    verify_content(out)
    print(f"Read-only verification passed: {len(manifest)} artifacts and {len(config['input_sha256'])} inputs.")


def verify_content(out):
    """Reconstruct saved aggregates and inspect output formats without writes."""
    import ast
    import xml.etree.ElementTree as ET
    from PIL import Image
    comparison = read_json(out / "comparison.json")
    schema = read_json(SCHEMA_PATH)
    tree, leaves = project_hierarchy(schema)
    pairs = pd.read_csv(out / "all_7056_leaf_pair_contributions.csv")
    if len(pairs) != 7056 or pairs.duplicated(["actual_subtype", "predicted_subtype"]).any():
        raise RuntimeError("Pair table is incomplete")
    lookup = {(r.actual_subtype, r.predicted_subtype): tuple(int(getattr(r, k)) for k in COUNT_KEYS)
              for r in pairs.itertuples()}
    coverage = pd.read_csv(out / "class_coverage.csv")
    if len(coverage) != 84 or int(coverage.validation_support.sum()) != 6486 or int((coverage.validation_support > 0).sum()) != 28:
        raise RuntimeError("Coverage table inconsistent")
    checks = {}
    for model in comparison:
        samples = pd.read_csv(out / f"{model}_sample_hcm.csv")
        if len(samples) != 6486:
            raise RuntimeError("Sample contribution rows missing")
        for row in samples.itertuples():
            values = tuple(int(getattr(row, k)) for k in COUNT_KEYS)
            if values != lookup[row.true_subtype, row.predicted_subtype]:
                raise RuntimeError("Pair/sample contribution mismatch")
            if row.tp + row.fn != len(tree.paths[leaves[row.true_subtype]]) - 1:
                raise RuntimeError("True path identity mismatch")
            if row.tp + row.fp != len(tree.paths[leaves[row.predicted_subtype]]) - 1:
                raise RuntimeError("Predicted path identity mismatch")
        for population in ["all_validation", "attack_truth_only"]:
            subset = samples if population == "all_validation" else samples[samples.true_family != "benign"]
            expected = summarize(subset)
            if expected != comparison[model][population]:
                raise RuntimeError("Saved HCM totals/metrics mismatch")
        matrix = pd.read_csv(out / f"{model}_formal_hcm_2x2.csv", index_col=0)
        c = sum_counts(samples)
        np.testing.assert_array_equal(matrix.to_numpy(), [[c.tp, c.fn], [c.fp, c.tn]])
        for grouping in ["true_family", "true_subtype"]:
            groups = pd.read_csv(out / f"{model}_hcm_by_{grouping}.csv")
            if int(groups.samples.sum()) != 6486 or sum_counts(groups) != c:
                raise RuntimeError("Group totals mismatch")
            if not groups.loc[groups.samples == 0, list(metrics(Counts()))].isna().all().all():
                raise RuntimeError("Zero-support groups should have undefined metrics")
        for level, size in [("detection", 2), ("family", 8), ("subtype", 84)]:
            cm = pd.read_csv(out / f"{model}_{level}_confusion_counts.csv", index_col=0)
            normalized = pd.read_csv(out / f"{model}_{level}_row_normalized.csv", index_col=0)
            if cm.shape != (size, size) or int(cm.to_numpy().sum()) != 6486:
                raise RuntimeError("Confusion matrix shape/count mismatch")
            expected = cm.div(cm.sum(axis=1).replace(0, np.nan), axis=0)
            np.testing.assert_allclose(normalized.to_numpy(), expected.to_numpy(), equal_nan=True, atol=1e-14)
        checks[model] = {"sample_rows": 6486, "group_totals_and_path_identities": True,
                         "micro_metrics_reconstructed": True, "count_and_normalized_matrices_valid": True}
    for path in out.rglob("*.json"):
        read_json(path)
    pngs = list(out.glob("*.png")); svgs = list(out.glob("*.svg"))
    if len(pngs) != 5 or len(svgs) != 5:
        raise RuntimeError("Expected five PNG/SVG figure pairs")
    for path in pngs:
        with Image.open(path) as image:
            image.verify()
    for path in svgs:
        if not ET.parse(path).getroot().tag.endswith("svg"):
            raise RuntimeError("Invalid SVG output")
    for path in [ROOT / "scripts/hcm_eval.py", Path(__file__).resolve(), ROOT / "tests/test_formal_hcm.py"]:
        ast.parse(path.read_text())
    return {"models": checks, "all_leaf_pairs": 7056, "png_files": len(pngs), "svg_files": len(svgs),
            "json_parsed": True, "source_syntax_valid": True}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["evaluate", "seal", "verify"], default="evaluate")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--sources-dir", type=Path, default=DEFAULT_OUT / "sources")
    args = p.parse_args()
    destination = args.output_dir.resolve()
    if not destination.is_relative_to(ROOT / "results"):
        raise ValueError("Outputs must remain under project results/")
    if args.mode == "evaluate":
        evaluate(destination, args.sources_dir.resolve())
    elif args.mode == "seal":
        seal(destination)
    else:
        verify(destination)
