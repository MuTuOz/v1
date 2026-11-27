#!/usr/bin/env python3
"""Sensitivity analysis of cyber-event detection by attack subtype and Non-IIDness.

Experiment ID: subtype_sensitivity_v1 (post-hoc; no training, no inference on
held-out test files). Inputs are ONLY already-saved artifacts:

* validation predictions of the 44 indexed pre_pi_research_v1 models
  (``predictions.csv`` in every ``artifact_dir`` of EXPERIMENT_INDEX.csv);
* training-only client supports (``audit/original_client_class_support.csv``)
  and the training-only balanced/exclusive allocation CSVs (their union is the
  22,450-row validation_v1 training set). Feature-distribution statistics use
  training rows only; validation features are not read.
* an analyst-defined mitigation mapping (``--mitigation-map``), which is a
  documented heuristic, not an empirically validated playbook.

Outputs go to a NEW directory and the script refuses to overwrite an existing one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "results/pre_pi_research_v1"
SEEDS = (42, 52, 62)
PORT_RE = re.compile(r"-port-\d+$")


# --------------------------------------------------------------------------- helpers
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def technique(subtype: str) -> str:
    """Port-agnostic attack technique, e.g. ddos_http-flood-port-80 -> ddos_http-flood."""
    return PORT_RE.sub("", subtype)


def mechanism(subtype: str) -> str:
    """Family-agnostic mechanism, e.g. ddos_icmp-flood / dos_icmp-flood -> icmp-flood."""
    if subtype == "benign":
        return "benign"
    return technique(subtype).split("_", 1)[1]


def signed_log1p(x: np.ndarray) -> np.ndarray:
    x = np.nan_to_num(x.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    x = np.clip(x, -1e8, 1e8)
    return (np.sign(x) * np.log1p(np.abs(x))).astype(np.float32)


def outcome_category(true_sub, pred_sub, true_fam, pred_fam):
    if true_sub == pred_sub:
        return "exact_correct"
    if true_fam == "benign":
        return "benign_predicted_attack"
    if pred_fam == "benign":
        return "attack_predicted_benign"
    if true_fam == pred_fam:
        return "correct_family_wrong_subtype"
    return "wrong_attack_family"


# --------------------------------------------------------------------------- loading
def load_index() -> pd.DataFrame:
    idx = pd.read_csv(PRE / "EXPERIMENT_INDEX.csv")
    idx["client_id"] = idx["client_id"].astype("Int64")
    return idx


def load_predictions(idx: pd.DataFrame, mit: pd.DataFrame) -> pd.DataFrame:
    mit_action = dict(zip(mit["technique"], mit["mitigation_action"]))
    mit_scope = dict(zip(mit["technique"], mit["mitigation_scope"]))
    frames = []
    for row in idx.itertuples(index=False):
        p = pd.read_csv(ROOT / row.artifact_dir / "predictions.csv")
        if len(p) != 6486:
            raise RuntimeError(f"{row.experiment_id}: {len(p)} rows, expected 6486")
        p["experiment_id"] = row.experiment_id
        p["mode"] = row.mode
        p["seed"] = row.seed
        p["partition"] = row.partition
        p["loss"] = row.loss
        p["model_client_id"] = row.client_id
        p["clients_per_round"] = row.clients_per_round
        p["local_epochs"] = row.local_epochs
        p["features_n"] = row.features
        frames.append(p)
    df = pd.concat(frames, ignore_index=True)
    for side in ("true", "predicted"):
        df[f"{side}_technique"] = df[f"{side}_subtype"].map(technique)
        df[f"{side}_mechanism"] = df[f"{side}_subtype"].map(mechanism)
        df[f"{side}_action"] = df[f"{side}_technique"].map(mit_action)
        df[f"{side}_scope"] = df[f"{side}_technique"].map(mit_scope)
    missing = set(df["true_technique"]).union(df["predicted_technique"]) - set(mit_action)
    if missing:
        raise RuntimeError(f"mitigation map lacks techniques: {sorted(missing)}")
    df["detected"] = df["predicted_family"] != "benign"
    df["exact"] = df["true_subtype"] == df["predicted_subtype"]
    df["technique_ok"] = df["true_technique"] == df["predicted_technique"]
    df["mechanism_ok"] = df["true_mechanism"] == df["predicted_mechanism"]
    df["family_ok"] = df["true_family"] == df["predicted_family"]
    df["mitigation_action_ok"] = df["true_action"] == df["predicted_action"]
    df["mitigation_strict_ok"] = df["mitigation_action_ok"] & (df["true_scope"] == df["predicted_scope"])
    df["category"] = [outcome_category(a, b, c, d) for a, b, c, d in zip(
        df["true_subtype"], df["predicted_subtype"], df["true_family"], df["predicted_family"])]
    return df


def load_training(mode_dir: Path) -> pd.DataFrame:
    parts = []
    for cid in range(1, 6):
        t = pd.read_csv(mode_dir / f"client_{cid}_train.csv", low_memory=False)
        t["alloc_client_id"] = cid
        parts.append(t)
    return pd.concat(parts, ignore_index=True)


# --------------------------------------------------------------------------- analyses
LEVEL_COLS = {
    "attack_detection_recall": "detected",
    "family_accuracy": "family_ok",
    "mechanism_accuracy": "mechanism_ok",
    "technique_accuracy": "technique_ok",
    "exact_subtype_accuracy": "exact",
    "mitigation_action_match": "mitigation_action_ok",
    "mitigation_strict_match": "mitigation_strict_ok",
}


def rates(g: pd.DataFrame) -> pd.Series:
    out = {"rows": len(g)}
    for k, c in LEVEL_COLS.items():
        out[k] = g[c].mean()
    for cat in ("exact_correct", "correct_family_wrong_subtype", "attack_predicted_benign",
                "wrong_attack_family"):
        out[f"rows_{cat}"] = int((g["category"] == cat).sum())
    return pd.Series(out)


def per_subtype_reference(df: pd.DataFrame) -> pd.DataFrame:
    """Reference unweighted original-partition models, attack rows only."""
    ref = df[(df["partition"] == "original") & (df["loss"] == "unweighted")
             & (df["experiment_id"].str.startswith("ref_"))
             & (df["true_family"] != "benign")]
    ref = ref.assign(arm=np.where(ref["mode"] == "local_only",
                                  "local_c" + ref["model_client_id"].astype(str), ref["mode"]))
    per_seed = (ref.groupby(["arm", "seed", "true_family", "true_technique", "true_subtype"])
                .apply(rates, include_groups=False).reset_index())
    metric_cols = list(LEVEL_COLS)
    agg = (per_seed.groupby(["arm", "true_family", "true_technique", "true_subtype"])
           .agg(rows=("rows", "first"), seeds=("seed", "nunique"),
                **{f"{m}_mean": (m, "mean") for m in metric_cols},
                **{f"{m}_sd": (m, "std") for m in metric_cols})
           .reset_index())
    return per_seed, agg


def nonidd_indicators(support: pd.DataFrame) -> pd.DataFrame:
    piv = support.pivot_table(index=["subtype", "family"], columns="client_id",
                              values="training_support", aggfunc="sum").fillna(0)
    total = piv.sum(axis=1)
    share = piv.div(total.replace(0, np.nan), axis=0)
    ent = -(share * np.log2(share.where(share > 0))).sum(axis=1)
    out = pd.DataFrame({
        "training_support_total": total.astype(int),
        "clients_with_support": (piv > 0).sum(axis=1),
        "max_client_share": share.max(axis=1),
        "client_entropy_norm": ent / np.log2(5),
    }).reset_index()
    val = support.groupby("subtype")["validation_support"].first()
    out["validation_support"] = out["subtype"].map(val).astype(int)
    out["technique"] = out["subtype"].map(technique)
    return out


def local_seen_vs_unseen(df: pd.DataFrame, support: pd.DataFrame) -> pd.DataFrame:
    """For each (client, attack subtype): local-only vs Flower vs centralized on the
    same rows, split by whether the subtype is in that client's training data."""
    sup = support.set_index(["client_id", "subtype"])["training_support"]
    ref = df[(df["partition"] == "original") & (df["loss"] == "unweighted")
             & df["experiment_id"].str.startswith("ref_") & (df["true_family"] != "benign")]
    rows = []
    for cid in range(1, 6):
        loc = ref[(ref["mode"] == "local_only") & (ref["model_client_id"] == cid)]
        glob = ref[ref["mode"].isin(["flower_fedavg", "centralized"])]
        for arm, part in (("local_only", loc), ("flower_fedavg", glob[glob["mode"] == "flower_fedavg"]),
                          ("centralized", glob[glob["mode"] == "centralized"])):
            g = part.groupby(["seed", "true_subtype"]).apply(rates, include_groups=False).reset_index()
            g["client_id"] = cid
            g["arm"] = arm
            rows.append(g)
    out = pd.concat(rows, ignore_index=True)
    out["client_training_support"] = [int(sup.get((c, s), 0)) for c, s in
                                      zip(out["client_id"], out["true_subtype"])]
    out["locally_seen"] = out["client_training_support"] > 0
    fam = ref.drop_duplicates("true_subtype").set_index("true_subtype")["true_family"]
    out["true_family"] = out["true_subtype"].map(fam)
    fam_seen = (support[support["training_support"] > 0].groupby("client_id")["family"]
                .apply(set).to_dict())
    out["family_locally_seen"] = [f in fam_seen.get(c, set()) for c, f in
                                  zip(out["client_id"], out["true_family"])]
    return out


def partition_sensitivity(df: pd.DataFrame, train_sets: dict[str, pd.DataFrame],
                          support: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ids = {"original": "ref_flower_s42", "balanced": "balanced_flower_p5_e1_s42",
           "exclusive": "exclusive_flower_p5_e1_s42"}
    stats_rows, per_sub = [], []
    js = pd.read_csv(PRE / "audit/partition_statistics.csv")
    for part, eid in ids.items():
        g = df[(df["experiment_id"] == eid)]
        att = g[g["true_family"] != "benign"]
        s = rates(att)
        s["partition"] = part
        s["experiment_id"] = eid
        s["benign_false_positive_rate"] = g[g["true_family"] == "benign"]["detected"].mean()
        s["mean_client_js_divergence_bits"] = js[js["partition"] == part]["js_divergence_bits"].mean()
        if part == "original":
            sup = support[support["training_support"] > 0]
            s["mean_client_subtype_support"] = sup.groupby("client_id")["subtype"].nunique().mean()
        else:
            t = train_sets[part]
            s["mean_client_subtype_support"] = t.groupby("alloc_client_id")["label4"].nunique().mean()
        stats_rows.append(s)
        ps = att.groupby(["true_family", "true_subtype"]).apply(rates, include_groups=False).reset_index()
        ps["partition"] = part
        per_sub.append(ps)
    return pd.DataFrame(stats_rows), pd.concat(per_sub, ignore_index=True)


def gap_correlations(agg: pd.DataFrame, ind: pd.DataFrame) -> pd.DataFrame:
    """Spearman (rank, distribution-free) association between Non-IID indicators and
    the Flower-minus-centralized gap per validation-observed attack subtype."""
    c = agg[agg["arm"] == "centralized"].set_index("true_subtype")
    f = agg[agg["arm"] == "flower_fedavg"].set_index("true_subtype")
    rows = []
    merged = ind.set_index("subtype").loc[c.index]
    for metric in ("attack_detection_recall", "family_accuracy", "exact_subtype_accuracy",
                   "mitigation_action_match"):
        gap = f[f"{metric}_mean"] - c[f"{metric}_mean"]
        for indicator in ("training_support_total", "clients_with_support", "max_client_share",
                          "client_entropy_norm"):
            for target_name, target in (("flower_minus_centralized", gap),
                                        ("flower_level", f[f"{metric}_mean"])):
                rho, p = stats.spearmanr(merged[indicator], target)
                rows.append({"metric": metric, "target": target_name, "indicator": indicator,
                             "n_subtypes": len(gap), "spearman_rho": rho, "p_value": p})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- feature distributions
def normality_tests(train: pd.DataFrame, feats: list[str], rng: np.random.Generator,
                    min_rows: int = 20, max_rows: int = 500) -> pd.DataFrame:
    X = signed_log1p(train[feats].to_numpy())
    rows = []
    for sub, idx in train.groupby("label4").indices.items():
        if len(idx) < min_rows:
            continue
        take = idx if len(idx) <= max_rows else rng.choice(idx, max_rows, replace=False)
        for j, feat in enumerate(feats):
            v = X[take, j].astype(np.float64)
            if np.ptp(v) == 0:
                rows.append({"subtype": sub, "feature": feat, "n": len(v), "constant": True,
                             "shapiro_p": np.nan, "skew": 0.0, "excess_kurtosis": 0.0})
                continue
            p = stats.shapiro(v).pvalue
            rows.append({"subtype": sub, "feature": feat, "n": len(v), "constant": False,
                         "shapiro_p": p, "skew": stats.skew(v),
                         "excess_kurtosis": stats.kurtosis(v)})
    out = pd.DataFrame(rows)
    nonconst = ~out["constant"]
    m = int(nonconst.sum())
    # Benjamini-Hochberg over all non-constant tests
    p = out.loc[nonconst, "shapiro_p"].to_numpy()
    order = np.argsort(p)
    q = np.empty_like(p)
    q[order] = np.minimum.accumulate((p[order] * m / np.arange(1, m + 1))[::-1])[::-1]
    out.loc[nonconst, "shapiro_q_bh"] = np.minimum(q, 1.0)
    out["normality_rejected_q05"] = out["shapiro_q_bh"] < 0.05
    return out


def sibling_pairs(subs: list[str]) -> list[tuple[str, str, str]]:
    pairs = set()
    by_tech: dict[str, list[str]] = {}
    by_mech: dict[str, list[str]] = {}
    by_fam: dict[str, list[str]] = {}
    for s in subs:
        if s == "benign":
            continue
        by_tech.setdefault(technique(s), []).append(s)
        by_mech.setdefault(mechanism(s), []).append(s)
        by_fam.setdefault(s.split("_")[0], []).append(s)
    for grp, kind in ((by_tech, "same_technique_other_port"), (by_mech, "same_mechanism_dos_vs_ddos")):
        for members in grp.values():
            for i, a in enumerate(sorted(members)):
                for b in sorted(members)[i + 1:]:
                    if kind == "same_mechanism_dos_vs_ddos" and technique(a).split("_")[0] == technique(b).split("_")[0]:
                        continue
                    pairs.add((a, b, kind))
    # the professor's example tree: ddos -> http flood vs icmp flood vs icmp frag flood
    focus = ["ddos_http-flood-port-80", "ddos_http-flood-port-1883", "ddos_icmp-flood",
             "ddos_icmp-frag-flood"]
    for i, a in enumerate(focus):
        for b in focus[i + 1:]:
            if a in subs and b in subs and not any({a, b} == {x, y} for x, y, _ in pairs):
                pairs.add((a, b, "ddos_example_tree"))
    return sorted(pairs)


def pairwise_separability(train: pd.DataFrame, feats: list[str], pairs, seed: int) -> pd.DataFrame:
    """Two-sample comparisons on TRAINING rows only: per-feature KS statistics
    (distribution-free) and a classifier two-sample test (balanced accuracy of a
    grouped-CV random forest separating the two subtypes)."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold, cross_val_predict
    from sklearn.metrics import balanced_accuracy_score

    X = signed_log1p(train[feats].to_numpy())
    lab = train["label4"].to_numpy()
    groups = train["episode_id"].astype(str).to_numpy()
    rows = []
    for a, b, kind in pairs:
        ia, ib = np.where(lab == a)[0], np.where(lab == b)[0]
        if len(ia) < 6 or len(ib) < 6:
            rows.append({"subtype_a": a, "subtype_b": b, "pair_kind": kind, "n_a": len(ia),
                         "n_b": len(ib), "status": "skipped_lt6_rows"})
            continue
        ks = np.array([stats.ks_2samp(X[ia, j], X[ib, j]).statistic for j in range(len(feats))])
        top = np.argsort(ks)[::-1][:5]
        idx = np.concatenate([ia, ib])
        y = (lab[idx] == b).astype(int)
        g = groups[idx]
        n_groups = (len(set(g[y == 0])), len(set(g[y == 1])))
        k = min(5, *n_groups)
        if k >= 2:
            cv, cv_name, kw = StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed), \
                f"StratifiedGroupKFold(k={k}, groups=episode_id)", {"groups": g}
        else:
            cv, cv_name, kw = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed), \
                "StratifiedKFold(k=5) - <2 episodes per class, rows may be correlated", {}
        clf = RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=-1,
                                     class_weight="balanced")
        pred = cross_val_predict(clf, X[idx], y, cv=cv, **kw)
        rows.append({
            "subtype_a": a, "subtype_b": b, "pair_kind": kind, "n_a": len(ia), "n_b": len(ib),
            "episodes_a": n_groups[0], "episodes_b": n_groups[1], "status": "ok",
            "median_ks": float(np.median(ks)), "max_ks": float(ks.max()),
            "features_ks_gt_0_5": int((ks > 0.5).sum()),
            "top_ks_features": ";".join(f"{feats[j]}={ks[j]:.3f}" for j in top),
            "c2st_balanced_accuracy": balanced_accuracy_score(y, pred), "cv": cv_name,
        })
    return pd.DataFrame(rows)


def validation_pair_confusion(df: pd.DataFrame, sep: pd.DataFrame) -> pd.DataFrame:
    ref = df[df["experiment_id"].isin([f"ref_{m}_s{s}" for m in ("centralized", "flower") for s in SEEDS])]
    out = []
    for r in sep[sep["status"] == "ok"].itertuples():
        for mode in ("centralized", "flower_fedavg"):
            g = ref[ref["mode"] == mode]
            for t, p in ((r.subtype_a, r.subtype_b), (r.subtype_b, r.subtype_a)):
                rows = g[g["true_subtype"] == t]
                if rows.empty:
                    continue
                out.append({"subtype_a": r.subtype_a, "subtype_b": r.subtype_b, "pair_kind": r.pair_kind,
                            "mode": mode, "true": t, "predicted_as_sibling": p,
                            "validation_rows_x_3_seeds": len(rows),
                            "rate_predicted_as_sibling": float((rows["predicted_subtype"] == p).mean()),
                            "c2st_balanced_accuracy": r.c2st_balanced_accuracy,
                            "median_ks": r.median_ks})
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- figures
def figures(out: Path, agg: pd.DataFrame, ind: pd.DataFrame, part_stats: pd.DataFrame,
            norm: pd.DataFrame, sep: pd.DataFrame) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    made = []
    fig_dir = out / "figures"
    fig_dir.mkdir()
    levels = ["attack_detection_recall", "mitigation_action_match", "family_accuracy",
              "technique_accuracy", "exact_subtype_accuracy"]
    labels = ["Detection", "Mitigation\naction", "Family", "Technique\n(port-agnostic)", "Exact\nsubtype"]

    # 1. Heatmap: per subtype x level, centralized vs flower (3-seed means)
    for arm in ("centralized", "flower_fedavg"):
        a = agg[agg["arm"] == arm].sort_values(["true_family", "true_subtype"])
        M = a[[f"{l}_mean" for l in levels]].to_numpy()
        fig, ax = plt.subplots(figsize=(7.5, 0.32 * len(a) + 1.6))
        im = ax.imshow(M, vmin=0, vmax=1, cmap="viridis", aspect="auto")
        ax.set_yticks(range(len(a)), [f"{s} (n={n})" for s, n in zip(a["true_subtype"], a["rows"])], fontsize=7)
        ax.set_xticks(range(len(levels)), labels, fontsize=8)
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                ax.text(j, i, f"{M[i, j]:.2f}", ha="center", va="center", fontsize=6,
                        color="white" if M[i, j] < 0.55 else "black")
        ax.set_title(f"{arm}: per-subtype rate by decision level\n(validation_v1, mean of seeds 42/52/62, attack rows)", fontsize=9)
        fig.colorbar(im, ax=ax, fraction=0.03)
        fig.tight_layout()
        for ext in ("png", "svg"):
            fig.savefig(fig_dir / f"subtype_level_heatmap_{arm}.{ext}", dpi=160)
        plt.close(fig)
        made.append(f"subtype_level_heatmap_{arm}")

    # 2. Flower-minus-centralized detection gap vs clients_with_support
    c = agg[agg["arm"] == "centralized"].set_index("true_subtype")
    f = agg[agg["arm"] == "flower_fedavg"].set_index("true_subtype")
    m = ind.set_index("subtype").loc[c.index]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, metric, title in ((axes[0], "attack_detection_recall", "Detection recall"),
                              (axes[1], "exact_subtype_accuracy", "Exact subtype accuracy")):
        gap = f[f"{metric}_mean"] - c[f"{metric}_mean"]
        jitter = np.random.default_rng(0).uniform(-0.12, 0.12, len(gap))
        ax.scatter(m["clients_with_support"] + jitter, gap, s=12 + m["training_support_total"] / 8,
                   alpha=0.7, edgecolor="k", linewidth=0.4)
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_xlabel("# clients holding the subtype in training (Non-IID spread)")
        ax.set_ylabel(f"Flower − Centralized ({title})")
        ax.set_title(title + " gap per subtype (size ∝ training rows)", fontsize=9)
        for s, x, y in zip(gap.index, m["clients_with_support"], gap):
            if abs(y) > 0.35:
                ax.annotate(s, (x, y), fontsize=6)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(fig_dir / f"nonid_spread_vs_gap.{ext}", dpi=160)
    plt.close(fig)
    made.append("nonid_spread_vs_gap")

    # 3. partition sensitivity bars
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ps = part_stats.set_index("partition").loc[["balanced", "original", "exclusive"]]
    w = 0.15
    for k, (lvl, lab) in enumerate(zip(levels, labels)):
        ax.bar(np.arange(3) + (k - 2) * w, ps[lvl], w, label=lab.replace("\n", " "))
    ax.set_xticks(range(3), [f"{p}\nJS={v:.3f} bits" for p, v in zip(ps.index, ps["mean_client_js_divergence_bits"])])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Rate on 2,648 validation attack rows")
    ax.set_title("Flower FedAvg (seed 42, 5 clients, 15 rounds) under increasing Non-IIDness", fontsize=9)
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(fig_dir / f"partition_sensitivity.{ext}", dpi=160)
    plt.close(fig)
    made.append("partition_sensitivity")

    # 4. normality rejection per subtype
    nn = norm[~norm["constant"]].groupby("subtype")["normality_rejected_q05"].mean().sort_values()
    fig, ax = plt.subplots(figsize=(7, 0.18 * len(nn) + 1.2))
    ax.barh(range(len(nn)), nn.to_numpy())
    ax.set_yticks(range(len(nn)), nn.index, fontsize=6)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of non-constant features with Shapiro-Wilk normality rejected (BH q<0.05)")
    ax.set_title("Feature distributions are not normal (training rows, signed-log1p space)", fontsize=9)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(fig_dir / f"normality_rejection.{ext}", dpi=160)
    plt.close(fig)
    made.append("normality_rejection")
    return made


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/subtype_sensitivity_v1")
    ap.add_argument("--mitigation-map", default="docs/mitigation_mapping_v1.csv")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    out = ROOT / args.out
    if out.exists():
        print(f"refusing to overwrite existing {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True)
    t0 = time.time()
    rng = np.random.default_rng(args.seed)
    log = []

    mit_path = ROOT / args.mitigation_map
    mit = pd.read_csv(mit_path)
    idx = load_index()
    df = load_predictions(idx, mit)
    log.append(f"loaded {idx.shape[0]} experiments x 6486 validation predictions = {len(df)} rows")

    support = pd.read_csv(PRE / "audit/original_client_class_support.csv")
    train_bal = load_training(PRE / "audit/allocations/balanced")
    train_exc = load_training(PRE / "audit/allocations/exclusive")
    feats = json.loads((ROOT / "results/pre_pi_research_v1/phase01/ref_local_c1_s42/config.json").read_text())["features"]
    assert len(feats) == 71, len(feats)
    # integrity: both allocations must be the same 22,450-row training set with the
    # same label counts as the original partition support table.
    orig_counts = support.groupby("subtype")["training_support"].sum()
    for name, t in (("balanced", train_bal), ("exclusive", train_exc)):
        assert len(t) == 22450, (name, len(t))
        c = t["label4"].value_counts().reindex(orig_counts.index, fill_value=0)
        assert (c == orig_counts).all(), f"{name} label counts differ from original support"
    log.append("verified balanced/exclusive allocations: 22,450 rows each, label counts equal original support")

    # integrity: categories sum to every evaluation row
    cat_tot = df.groupby("experiment_id")["category"].count()
    assert (cat_tot == 6486).all()
    benign_fp = df[df["true_family"] == "benign"].groupby("experiment_id")["category"].value_counts().unstack(fill_value=0)

    per_seed, agg = per_subtype_reference(df)
    per_seed.to_csv(out / "per_subtype_reference_per_seed.csv", index=False)
    agg.to_csv(out / "per_subtype_reference_summary.csv", index=False)

    ind = nonidd_indicators(support)
    ind.to_csv(out / "subtype_nonid_indicators.csv", index=False)

    lsu = local_seen_vs_unseen(df, support)
    lsu.to_csv(out / "client_subtype_seen_unseen_per_seed.csv", index=False)
    lsu_sum = (lsu.groupby(["arm", "locally_seen", "family_locally_seen"])
               .apply(lambda g: pd.Series({
                   "client_subtype_seed_cells": len(g),
                   "rows": int(g["rows"].sum()),
                   **{k: float(np.average(g[k], weights=g["rows"])) for k in LEVEL_COLS}}),
                      include_groups=False).reset_index())
    lsu_sum.to_csv(out / "client_seen_unseen_summary.csv", index=False)

    part_stats, part_sub = partition_sensitivity(df, {"balanced": train_bal, "exclusive": train_exc}, support)
    part_stats.to_csv(out / "partition_sensitivity_global.csv", index=False)
    part_sub.to_csv(out / "partition_sensitivity_per_subtype.csv", index=False)

    corr = gap_correlations(agg, ind)
    corr.to_csv(out / "nonid_gap_spearman.csv", index=False)

    # level summary per arm (attack rows, seeds pooled as means)
    lvl = (per_seed.groupby(["arm", "seed"]).apply(
        lambda g: pd.Series({k: float(np.average(g[k], weights=g["rows"])) for k in LEVEL_COLS}),
        include_groups=False).reset_index())
    lvl_sum = lvl.groupby("arm").agg(**{f"{k}_mean": (k, "mean") for k in LEVEL_COLS},
                                     **{f"{k}_sd": (k, "std") for k in LEVEL_COLS}).reset_index()
    lvl_sum.to_csv(out / "decision_level_summary.csv", index=False)

    # loss-weighting sensitivity per subtype for centralized & flower (seed 42)
    lw = df[(df["seed"] == 42) & df["mode"].isin(["centralized", "flower_fedavg"]) &
            (df["partition"] == "original") & (df["features_n"] == 71) &
            (df["clients_per_round"] == 5) & (df["local_epochs"] == 1) &
            ~df["experiment_id"].str.startswith(("historical", "diagnostic")) & (df["true_family"] != "benign")]
    lw_sub = lw.groupby(["mode", "loss", "true_family", "true_subtype"]).apply(rates, include_groups=False).reset_index()
    lw_sub.to_csv(out / "loss_weighting_per_subtype_s42.csv", index=False)

    # feature distributions (training only)
    norm = normality_tests(train_bal, feats, rng)
    norm.to_csv(out / "feature_normality_training.csv", index=False)
    nc = norm[~norm["constant"]]
    norm_sum = {
        "subtypes_tested": int(norm["subtype"].nunique()),
        "subtype_feature_tests_nonconstant": int(len(nc)),
        "constant_subtype_feature_cells": int(norm["constant"].sum()),
        "share_rejected_bh_q05": float(nc["normality_rejected_q05"].mean()),
        "median_abs_skew": float(nc["skew"].abs().median()),
        "median_excess_kurtosis": float(nc["excess_kurtosis"].median()),
    }

    pairs = sibling_pairs(sorted(train_bal["label4"].unique()))
    sep = pairwise_separability(train_bal, feats, pairs, args.seed)
    sep.to_csv(out / "sibling_pair_separability_training.csv", index=False)
    vpc = validation_pair_confusion(df, sep)
    vpc.to_csv(out / "sibling_pair_validation_confusion.csv", index=False)

    made = figures(out, agg, ind, part_stats, norm, sep)

    summary = {
        "experiment_id": "subtype_sensitivity_v1",
        "type": "post-hoc analysis of saved validation_v1 predictions + training-only feature statistics",
        "no_training": True, "no_model_inference": True,
        "protected_test_files_accessed": False, "validation_features_accessed": False,
        "experiments": int(idx.shape[0]), "prediction_rows": int(len(df)),
        "decision_level_summary": lvl_sum.to_dict(orient="records"),
        "partition_sensitivity": part_stats.to_dict(orient="records"),
        "normality": norm_sum,
        "sibling_pairs": int((sep["status"] == "ok").sum()),
        "figures": made, "log": log,
        "runtime_seconds": time.time() - t0,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

    inputs = [PRE / "EXPERIMENT_INDEX.csv", PRE / "audit/original_client_class_support.csv",
              PRE / "audit/partition_statistics.csv", mit_path]
    inputs += sorted((PRE / "audit/allocations").glob("*/client_*_train.csv"))
    inputs += [ROOT / a / "predictions.csv" for a in idx["artifact_dir"]]
    prov = {
        "command": " ".join([sys.executable] + sys.argv),
        "python": sys.version, "platform": platform.platform(),
        "packages": {m.__name__: m.__version__ for m in (np, pd)} | {"scipy": __import__("scipy").__version__,
                     "sklearn": __import__("sklearn").__version__},
        "seed": args.seed,
        "script_sha256": sha256(Path(__file__)),
        "inputs_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in inputs},
    }
    (out / "provenance.json").write_text(json.dumps(prov, indent=2))
    print(json.dumps({k: summary[k] for k in ("experiments", "prediction_rows", "normality", "sibling_pairs")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
