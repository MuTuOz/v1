"""Audit, run, evaluate and verify the isolated Flower 84-class experiment.

Use the existing WSL environment. No test-set paths are opened by this script.
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
import socket
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "flower_subtype_app"
OUT = ROOT / "results/subtype_flower_val_v1"
MODEL = ROOT / "models/subtype_flower_val_v1.pt"
sys.path.insert(0, str(APP))

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from seniorfl_subtype.task import (CLASSES, CLASS_TO_ID, CLIENT_SIZES, DEFAULTS, FAMILY_OF,
                                   FEATURES, SCHEMA, SubtypeMLP, make_labels, prepare, read_split)


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(path):
    return torch.load(path, map_location="cpu", weights_only=True)


def audit():
    if (OUT / "data_audit.json").exists():
        raise FileExistsError("Audit already exists; preserve the previous run")
    assert importlib.metadata.version("flwr") == "1.40.0"
    torch.set_num_threads(1)
    train = read_split(ROOT, "train.csv")
    val = read_split(ROOT, "validation.csv")
    clients = [read_split(ROOT, f"client_{i}_train.csv") for i in CLIENT_SIZES]
    assert len(train) == 22450 and len(val) == 6486
    assert [len(d) for d in clients] == list(CLIENT_SIZES.values())
    assert train[["label2", "label4"]].notna().all().all()
    assert train.groupby("label4").label2.nunique().max() == 1
    mapping = train.drop_duplicates("label4").set_index("label4").label2.to_dict()
    classes = ["benign"] + sorted(set(train.label4) - {"benign"})
    assert mapping == FAMILY_OF and classes == CLASSES
    assert all(s == "benign" or s.split("_", 1)[0] == f for s, f in mapping.items())
    assert len(classes) == 84 and len(FEATURES) == 71
    assert val.label4.nunique() == 28
    for d in [train, val] + clients:
        assert list(d.columns) == list(train.columns)
        assert d.label4.map(mapping).equals(d.label2)
        assert [c for c in d.columns if c.startswith(("network_", "log_"))] == FEATURES
    # Metadata identities are unique; CSV floating point round-trips can differ below float32.
    joined = pd.concat(clients, ignore_index=True)
    rows = lambda d: Counter(pd.util.hash_pandas_object(d, index=False).tolist())
    keys = list(train.columns[:8])
    assert not train.duplicated(keys).any() and not joined.duplicated(keys).any()
    left = train.sort_values(keys).reset_index(drop=True)
    right = joined.sort_values(keys).reset_index(drop=True)
    assert left[keys].equals(right[keys])
    torch.testing.assert_close(prepare(left), prepare(right), rtol=0, atol=0)
    raw_delta = np.abs(left[FEATURES].to_numpy(float) - right[FEATURES].to_numpy(float))
    attack_train = set(train.loc[train.label2 != "benign", "episode_id"])
    attack_val = set(val.loc[val.label2 != "benign", "episode_id"])
    assert not (attack_train & attack_val)
    baseline = checkpoint(ROOT / "models/subtype_centralized_val_v1.pt")
    for k in ["features", "classes", "family_of", "preprocessing"]:
        assert baseline[k] == SCHEMA[k]
    sys.path.insert(0, str(ROOT / "flower_app"))
    from seniorfl.task import prepare as baseline_prepare
    from seniorfl.subtype_task import SubtypeMLP as BaselineMLP, make_labels as baseline_labels
    torch.testing.assert_close(prepare(train), baseline_prepare(train), rtol=0, atol=0)
    torch.testing.assert_close(prepare(val), baseline_prepare(val), rtol=0, atol=0)
    assert torch.equal(make_labels(train), baseline_labels(train))
    torch.manual_seed(42)
    a = SubtypeMLP()
    torch.manual_seed(42)
    b = BaselineMLP()
    for k, tensor in a.state_dict().items():
        torch.testing.assert_close(tensor, b.state_dict()[k], rtol=0, atol=0)
    assert sum(p.numel() for p in a.parameters()) == 9460
    # Edge cases: NaN/Inf -> 0, clipping then signed log1p; baseline equivalence.
    edge = pd.DataFrame([[np.nan, np.inf, -np.inf, 1e20, -1e20] + [0.] * 66], columns=FEATURES)
    torch.testing.assert_close(prepare(edge), baseline_prepare(edge), rtol=0, atol=0)
    absent = sorted(set(CLASSES) - set(val.label4))
    coverage = pd.DataFrame({"subtype_id": range(84), "subtype": CLASSES,
                             "family": [mapping[s] for s in CLASSES],
                             "train_support": [int((train.label4 == s).sum()) for s in CLASSES],
                             "validation_support": [int((val.label4 == s).sum()) for s in CLASSES]})
    for i, d in enumerate(clients, 1):
        coverage[f"client_{i}_train_support"] = [int((d.label4 == s).sum()) for s in CLASSES]
    coverage.to_csv(OUT / "class_mapping_and_coverage.csv", index=False)
    family_counts = pd.DataFrame([d.label2.value_counts() for d in clients],
                                 index=[f"client_{i}" for i in CLIENT_SIZES]).fillna(0).astype(int)
    family_counts.to_csv(OUT / "client_family_counts.csv")
    data_hashes = {str(p.relative_to(ROOT)): sha(p) for p in
                   [ROOT / "data/validation_v1" / n for n in
                    ["train.csv", "validation.csv"] + [f"client_{i}_train.csv" for i in CLIENT_SIZES]]}
    audit_result = {"training_samples": len(train), "validation_samples": len(val),
                    "attack_validation_samples": int((val.label2 != "benign").sum()),
                    "benign_validation_samples": int((val.label2 == "benign").sum()),
                    "classes": 84, "observed_validation_classes": 28,
                    "absent_validation_classes": absent,
                    "validation_family_counts": val.label2.value_counts().to_dict(),
                    "client_sizes": CLIENT_SIZES, "client_union_metadata_identical_to_train": True,
                    "client_union_preprocessed_tensors_identical_to_train": True,
                    "raw_numeric_max_absolute_difference": float(np.nanmax(raw_delta)),
                    "raw_numeric_unequal_values": int(np.count_nonzero(raw_delta)),
                    "subtype_family_mapping_unique_and_verified": True,
                    "baseline_model_schema_and_preprocessing_identical": True,
                    "initial_weights_identical_at_seed_42": True,
                    "attack_heuristic_episode_overlap_train_validation": len(attack_train & attack_val),
                    "full_row_overlap_train_validation": sum((rows(train) & rows(val)).values()),
                    "sha256": data_hashes,
                    "data_read_allowlist": sorted(data_hashes),
                    "test_sets_accessed": False}
    write_json("data_audit.json", audit_result)
    config = {**DEFAULTS, "clients": 5, "architecture": [71, 64, 32, 84],
               "parameters": 9460, "optimizer": "Adam", "optimizer_reset_each_round": True,
               "loss": "CrossEntropyLoss", "aggregation": "num-examples weighted FedAvg",
               "fraction_train": 1.0, "fraction_evaluate": 0.0,
               "client_shuffle_seed": "42 + 100 * server_round + client_id (1..5)",
               "server_threads": 1, "client_threads": 1, "device": "cpu",
               "deterministic_torch_algorithms": True,
               "validation_policy": "final round only; no model selection",
               "baseline_epochs": 15, "baseline_optimizer_state": "persistent across epochs",
               "run_command": f"{sys.executable} scripts/26_run_flower_subtype_val_v1.py --stage all"}
    write_json("config.json", config)
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
    (OUT / "requirements.freeze.txt").write_text(freeze.stdout)
    write_json("environment.json", {"python": sys.version, "executable": sys.executable,
                                     "platform": platform.platform(), "torch_config": torch.__config__.show(),
                                     "packages": {n: importlib.metadata.version(n) for n in
                                                  ["flwr", "ray", "torch", "numpy", "pandas", "scikit-learn"]},
                                     "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    print(json.dumps(audit_result, indent=2), flush=True)


def train():
    if MODEL.exists():
        raise FileExistsError(MODEL)
    if not (OUT / "data_audit.json").exists():
        raise RuntimeError("Audit required first")
    # Use the official runtime-dependency flag to reuse the authorized WSL venv.
    # A dedicated Flower home avoids changing the original Flower configuration.
    flower_home = Path("/home/seniorfl/.flwr/subtype84_val_v1")
    flower_home.mkdir(exist_ok=True)
    config_path = flower_home / "config.toml"
    config_text = ('[superlink]\ndefault = "subtype-simulation"\n'
                   '[superlink.subtype-simulation]\naddress = "127.0.0.1:39092"\ninsecure = true\n'
                   'options.num-supernodes = 5\noptions.backend.name = "ray"\n'
                   'options.backend.client-resources.num-cpus = 1\n'
                   'options.backend.client-resources.num-gpus = 0.0\n')
    if config_path.exists():
        assert config_path.read_text() == config_text
    else:
        config_path.write_text(config_text)
    env = os.environ.copy()
    env.update({"FLWR_HOME": str(flower_home), "FLWR_TELEMETRY_ENABLED": "0",
                "PATH": str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", ""),
                "MPLCONFIGDIR": str(OUT / "matplotlib_config")})
    cmd = [str(Path(sys.executable).parent / "flwr"), "run", str(APP), "subtype-simulation", "--stream"]
    server_cmd = [str(Path(sys.executable).parent / "flower-superlink"), "--insecure", "--simulation",
                  "--disable-runtime-dependency-installation", "--host", "127.0.0.1", "--port", "39092"]
    attempt = 1
    while (OUT / f"simulation_attempt_{attempt:02d}.log").exists():
        attempt += 1
    log_name = f"simulation_attempt_{attempt:02d}.log"
    write_json(f"launch_attempt_{attempt:02d}.json", {"command": cmd, "superlink_command": server_cmd,
               "cwd": str(ROOT), "transport": "Flower local SuperLink/Ray", "env_overrides":
               {k: env[k] for k in ["FLWR_HOME", "FLWR_TELEMETRY_ENABLED", "MPLCONFIGDIR"]},
               "runtime_dependency_installation": False, "python_environment": str(Path(sys.executable).parent.parent),
               "started_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    with (OUT / f"superlink_attempt_{attempt:02d}.log").open("x") as server_log:
        server = subprocess.Popen(server_cmd, cwd=ROOT, env=env, stdout=server_log, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Dedicated SuperLink exited before readiness")
                try:
                    with socket.create_connection(("127.0.0.1", 39092), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Dedicated SuperLink failed to become ready")
            with (OUT / log_name).open("x", encoding="utf-8") as log:
                result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        finally:
            server.terminate()
            server.wait(timeout=30)
    if result.returncode or not MODEL.is_file():
        raise RuntimeError(f"Simulation did not save a model (exit {result.returncode}); see {log_name}")
    write_json("successful_launch.json", {"simulation_log": log_name, "attempt": attempt,
                                          "runtime_dependency_installation": False})


def evaluate_model(path, name, val):
    data = checkpoint(path)
    for k in ["features", "classes", "family_of", "preprocessing"]:
        assert data[k] == SCHEMA[k]
    model = SubtypeMLP()
    model.load_state_dict(data["state_dict"])
    model.eval()
    with torch.inference_mode():
        yp = np.concatenate([model(x).argmax(1).numpy() for x in prepare(val).split(512)])
    yt = make_labels(val).numpy()
    ts = np.array(CLASSES)[yt]
    ps = np.array(CLASSES)[yp]
    tf = val.label2.to_numpy()
    pf = np.array([FAMILY_OF[s] for s in ps])
    attack = tf != "benign"
    exact = yt == yp
    masks = {"exact_correct": exact,
             "correct_family_wrong_subtype": attack & ~exact & (tf == pf),
             "attack_predicted_benign": attack & (pf == "benign"),
             "benign_predicted_attack": ~attack & (pf != "benign"),
             "wrong_attack_family": attack & (pf != "benign") & (tf != pf)}
    assert np.all(np.stack(list(masks.values())).sum(axis=0) == 1)
    breakdown = {k: int(v.sum()) for k, v in masks.items()}
    assert sum(breakdown.values()) == len(val)
    observed = sorted(np.unique(yt).tolist())
    observed_attack = [i for i in observed if CLASSES[i] != "benign"]
    families = sorted(set(FAMILY_OF.values()))
    metrics = {"experiment": name, "training_samples": 22450, "validation_samples": len(val),
               "num_classes": 84, "num_observed_validation_classes": len(observed),
               "exact_subtype_accuracy": float(accuracy_score(yt, yp)),
               "subtype_macro_f1_observed": float(f1_score(yt, yp, labels=observed, average="macro", zero_division=0)),
               "subtype_macro_f1_all_84_zero_support": float(f1_score(yt, yp, labels=list(range(84)), average="macro", zero_division=0)),
               "attack_only_subtype_accuracy": float(accuracy_score(yt[attack], yp[attack])),
               "attack_only_subtype_macro_f1": float(f1_score(yt[attack], yp[attack], labels=observed_attack, average="macro", zero_division=0)),
               "family_accuracy": float(accuracy_score(tf, pf)),
               "family_macro_f1_observed": float(f1_score(tf, pf, labels=sorted(set(tf)), average="macro", zero_division=0)),
               "attack_detection_recall": float(np.mean(pf[attack] != "benign")),
               "benign_false_positive_rate": float(np.mean(pf[~attack] != "benign")),
               "hierarchical_error_breakdown": breakdown, "seed": 42,
               "model_sha256": sha(path), "validation_sha256": sha(ROOT / "data/validation_v1/validation.csv"),
               "macro_f1_label_policy": "28 ground-truth observed subtypes; 27 attack subtypes; 7 observed families",
               "attack_validation_samples": int(attack.sum()), "benign_validation_samples": int((~attack).sum())}
    write_json(f"{name}_metrics.json", metrics)
    preds = pd.DataFrame({"validation_row": range(len(val)), "true_subtype_id": yt, "predicted_subtype_id": yp,
                          "true_subtype": ts, "predicted_subtype": ps, "true_family": tf, "predicted_family": pf,
                          "episode_id": val.episode_id.to_numpy(),
                          "hierarchical_category": np.select(list(masks.values()), list(masks), default="INVALID")})
    preds.to_csv(OUT / f"{name}_predictions.csv", index=False)
    pd.DataFrame(classification_report(yt, yp, labels=list(range(84)), target_names=CLASSES,
                                        output_dict=True, zero_division=0)).T.to_csv(OUT / f"{name}_report.csv")
    pd.DataFrame(confusion_matrix(yt, yp, labels=list(range(84))), index=CLASSES, columns=CLASSES).to_csv(OUT / f"{name}_confusion.csv")
    pd.DataFrame(classification_report(tf, pf, labels=families, output_dict=True, zero_division=0)).T.to_csv(OUT / f"{name}_family_report.csv")
    pd.DataFrame(confusion_matrix(tf, pf, labels=families), index=families, columns=families).to_csv(OUT / f"{name}_family_confusion.csv")
    pd.DataFrame([breakdown], index=[name]).to_csv(OUT / f"{name}_hierarchical_errors.csv")
    return metrics, preds


def finalize():
    torch.set_num_threads(1)
    if not MODEL.is_file():
        raise RuntimeError("No trained Flower model: no experimental results can be reported")
    if (OUT / "fedavg_metrics.json").exists():
        raise FileExistsError("Final evaluation already exists")
    val = read_split(ROOT, "validation.csv")
    fed, _ = evaluate_model(MODEL, "fedavg", val)
    cen, cp = evaluate_model(ROOT / "models/subtype_centralized_val_v1.pt", "centralized_recomputed", val)
    historical = json.loads((ROOT / "results/subtype_centralized_val_v1_metrics.json").read_text())
    for k, v in historical.items():
        if k in cen and isinstance(v, (float, int)):
            assert np.isclose(v, cen[k], rtol=0, atol=1e-12), (k, v, cen[k])
    assert historical["hierarchical_error_breakdown"] == cen["hierarchical_error_breakdown"]
    old = pd.read_csv(ROOT / "results/subtype_centralized_val_v1_predictions.csv")
    for k in ["true_subtype", "predicted_subtype", "true_family", "predicted_family", "episode_id"]:
        assert old[k].equals(cp[k]), k
    metrics = ["exact_subtype_accuracy", "subtype_macro_f1_observed", "attack_only_subtype_accuracy",
               "attack_only_subtype_macro_f1", "family_accuracy", "family_macro_f1_observed",
               "attack_detection_recall", "benign_false_positive_rate"]
    comparison = pd.DataFrame([{"metric": k, "centralized": cen[k], "flower_fedavg": fed[k],
                                "fedavg_minus_centralized_percentage_points": 100 * (fed[k] - cen[k])} for k in metrics])
    comparison.to_csv(OUT / "comparison.csv", index=False)
    write_json("comparison.json", {"centralized": cen, "flower_fedavg": fed,
                                    "centralized_saved_predictions_reproduced_exactly": True})
    figures(fed, cen)
    report(fed, cen)


def figures(fed, cen):
    os.environ.setdefault("MPLCONFIGDIR", str(OUT / "matplotlib_config"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "svg.fonttype": "none"})
    specs = [("exact_subtype_accuracy", "Exact subtype accuracy"), ("subtype_macro_f1_observed", "Subtype macro F1 (28)"),
             ("attack_only_subtype_accuracy", "Attack subtype accuracy"), ("family_accuracy", "Family accuracy"),
             ("family_macro_f1_observed", "Family macro F1 (7)"), ("attack_detection_recall", "Attack recall")]
    fig, ax = plt.subplots(figsize=(10, 5)); pos = np.arange(len(specs))
    for offset, model, label in [(-.2, cen, "Centralized"), (.2, fed, "Flower FedAvg")]:
        bars = ax.bar(pos + offset, [100 * model[k] for k, _ in specs], .4, label=label)
        ax.bar_label(bars, fmt="%.1f", fontsize=8)
    ax.set_xticks(pos, [s for _, s in specs], rotation=18, ha="right"); ax.set_ylim(0, 110)
    ax.set_ylabel("Percent"); ax.legend(); fig.tight_layout()
    save_figure(fig, "comparison")
    fig, ax = plt.subplots(figsize=(8, 4))
    rounds = pd.read_csv(OUT / "rounds.csv")
    ax.plot(rounds["round"], rounds.weighted_train_loss, marker="o")
    ax.set(xlabel="FedAvg round", ylabel="Sample-weighted local training loss", xticks=range(1, 16))
    fig.tight_layout(); save_figure(fig, "training_loss")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, name, label in zip(axes, ["centralized_recomputed", "fedavg"], ["Centralized", "Flower FedAvg"]):
        cm = pd.read_csv(OUT / f"{name}_family_confusion.csv", index_col=0)
        im = ax.imshow(cm.to_numpy(), cmap="Blues")
        ax.set_xticks(range(8), cm.columns, rotation=45, ha="right")
        ax.set_yticks(range(8), cm.index); ax.set(xlabel="Predicted family", ylabel="True family", title=label)
        for i in range(8):
            for j in range(8):
                n = int(cm.iloc[i, j]); ax.text(j, i, str(n), ha="center", va="center", fontsize=8,
                                               color="white" if n > cm.to_numpy().max() / 2 else "black")
        fig.colorbar(im, ax=ax, fraction=.046)
    fig.tight_layout(); save_figure(fig, "family_confusion")
    fig, ax = plt.subplots(figsize=(14, 10))
    cm = pd.read_csv(OUT / "fedavg_confusion.csv", index_col=0)
    support = cm.sum(axis=1) > 0
    shown = cm.loc[support]
    normalized = shown.div(shown.sum(axis=1), axis=0)
    im = ax.imshow(normalized, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_yticks(range(len(shown)), shown.index, fontsize=7)
    ax.set_xticks(range(84), cm.columns, rotation=90, fontsize=5)
    ax.set(xlabel="Predicted subtype (all 84)", ylabel="True subtype (28 observed)",
           title="Flower FedAvg: row-normalized subtype confusion; 56 absent true classes omitted")
    fig.colorbar(im, ax=ax); fig.tight_layout(); save_figure(fig, "subtype_confusion_observed")
    fig, ax = plt.subplots(figsize=(8, 5))
    table = pd.read_csv(OUT / "client_family_counts.csv", index_col=0)
    table.plot.bar(stacked=True, ax=ax); ax.set(xlabel="Client", ylabel="Training samples")
    ax.legend(bbox_to_anchor=(1.02, 1)); fig.tight_layout(); save_figure(fig, "client_distribution")


def save_figure(fig, name):
    import matplotlib.pyplot as plt
    for extension in ["png", "svg"]:
        fig.savefig(OUT / f"{name}.{extension}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def report(fed, cen):
    execution = json.loads((OUT / "training_execution.json").read_text())
    labels = {"exact_subtype_accuracy": "Tam alt tür doğruluğu", "subtype_macro_f1_observed": "Alt tür Makro F1 (gözlenen 28)",
              "attack_only_subtype_accuracy": "Yalnız saldırılarda tam alt tür doğruluğu",
              "attack_only_subtype_macro_f1": "Yalnız saldırılarda Makro F1 (27)",
              "family_accuracy": "Alt türden türetilen aile doğruluğu", "family_macro_f1_observed": "Aile Makro F1 (gözlenen 7)",
              "attack_detection_recall": "Saldırı tespit duyarlılığı", "benign_false_positive_rate": "Benign yanlış pozitif oranı"}
    lines = ["# 84 sınıflı Flower FedAvg — validation_v1", "", "## Amaç ve gerçekleşen çalışma", "",
             "`references/proposal.docx`, farklı saldırı dağılımlarına sahip istemcilerin ortak modelini yerel ve merkezi modellerle karşılaştırmayı; saldırıyı benign sayma ve doğru aile içinde yanlış alt tür seçme hatalarını ayırmayı hedefler. Bu deney, önerinin **84 sınıflı federe–merkezi karşılaştırmasını** gerçekleştirir. Bu görevde yeni yerel modeller, fiziksel istemciler veya dashboard uygulanmadı; önceki deneyler yeni ölçüm olarak sunulmadı.", "",
             "## Veri ve eşdeğerlik kontrolleri", "",
             "- Eğitim: `data/validation_v1/train.csv`, 22.450 kayıt; mevcut beş Non-IID istemci: 4.430 / 6.216 / 2.901 / 5.103 / 3.800. Birleşimlerinin sekiz metadata alanından oluşan benzersiz kayıt kimlikleri ve modele giren ön işlenmiş float32 tensörleri merkezi eğitimle birebir eşit. CSV okumada iki ham sayıda en fazla 4.136e-25 fark bulundu; model girdisine yansımadığı doğrulandı, veri değiştirilmedi.",
             "- Değerlendirme yalnız `data/validation_v1/validation.csv`: 6.486 kayıt; 3.838 benign, 2.648 saldırı; 28 alt tür ve 7 aile. Web ailesi doğrulamada yok.",
             "- Eğitimden türetilen benign + sıralı 83 saldırı sınıfı, 71 özellik ve alt tür→aile eşlemesi mevcut merkezi model ile birebir doğrulandı. Her alt tür tek aileye bağlı; doğrulama etiketleri de bu eşlemeyle uyumlu.",
             "- Ön işleme: float64 giriş; NaN/±Inf→0; ±1e8 kırpma; sign(x)·log1p(abs(x)); float32. Eğitim/doğrulama tensörleri ve seed=42 başlangıç ağırlıkları orijinal kodla birebir eşit.",
             "- `test_episode.csv` ve `test_web_diagnostic.csv` açılmadı; bu deneyin okuyucusu yalnız izin verilen eğitim/doğrulama dosyalarını kabul eder.", "",
             "## Yapılandırma ve yürütme", "",
             "Flower **1.40.0**, ayrı `flower_subtype_app/`, gerçek ClientApp/ServerApp, yerel SuperLink + Ray simülasyonu. Mimari: **71→64→32→84**, ReLU, 9.460 parametre. **15 tur**, her tur **5/5 istemci**, **1 yerel epoch**, batch **128**, Adam **0.001**, CPU; seed **42**, istemci karıştırma tohumu `42 + 100*tur + istemci_id`. Her tur Adam durumu yeniden başlatılır; merkezi modelin Adam durumu 15 epoch boyunca korunur. İki modelde toplam örnek sunumu 336.750; farklı optimizasyon yörüngeleri nedeniyle 15 tur, 15 merkezi epoch ile aynı güncelleme süreci değildir.", "",
             "Her güncelleme gerçek örnek sayısıyla ağırlıklandırıldı: `n_i / 22450`. 75 istemci güncellemesi ve 15 turun tamamı denetlendi; Flower ağırlık ortalaması her tensörde bağımsız float64 referansla kontrol edildi. Değerlendirme yalnız son turda; doğrulama ile model seçimi yapılmadı.", "",
             f"Ölçülen strateji/eğitim süresi: **{execution['training_wall_seconds']:.3f} saniye** (SuperLink başlatma, paketleme ve son değerlendirme hariç). Bu simülasyon süresi fiziksel ağ gecikmesi veya Raspberry Pi performansı değildir.", "",
             "Paketlenen Flower uygulaması `.flwr/apps` altında çalışsa bile veri yolu paket konumundan türetilmez: `project-root` ayarı kullanılır ve istemciye ConfigRecord ile gönderilir. Dataset FAB içine kopyalanmaz.", "",
             "## Aynı doğrulama kümesindeki sonuçlar", "",
             "Mevcut `models/subtype_centralized_val_v1.pt` yeniden değerlendirildi; tarihi JSON metrikleri ve 6.486 tahminin tamamı birebir yeniden üretildi. Merkezi model yeniden eğitilmedi.", "",
             "| Ölçüt | Merkezi (%) | Flower FedAvg (%) | Fark (yüzde puan) |", "|---|---:|---:|---:|"]
    for k, label in labels.items():
        lines.append(f"| {label} | {cen[k]*100:.4f} | {fed[k]*100:.4f} | {(fed[k]-cen[k])*100:+.4f} |")
    lines += ["", "Ana alt tür Makro F1 yalnız ground-truth'ta gözlenen 28 sınıf üzerinden, saldırı Makro F1 27 saldırı sınıfından, aile Makro F1 7 gözlenen aileden hesaplandı; `zero_division=0`. Gözlenmeyen sınıflara tahminler örnek düzeyinde hata olarak sayılır; bu sınıfların F1 terimleri ana ortalamaya eklenmez. 84 satırlı sınıf raporundaki tüm-sınıflar Makro F1 ise farklı bir payda kullanır ve ana ölçüt değildir.", "",
              f"Sıfır destekli sınıfları da 0 sayan tüm-84 Makro F1: merkezi **{cen['subtype_macro_f1_all_84_zero_support']:.6f}**, FedAvg **{fed['subtype_macro_f1_all_84_zero_support']:.6f}**. Bu değer 84 sınıfın tamamının doğrulandığı anlamına gelmez.", "",
              "## Hiyerarşik hata dökümü", "", "| Ayrık kategori | Merkezi | Flower FedAvg |", "|---|---:|---:|"]
    names = {"exact_correct": "Tam doğru (benign dahil)", "correct_family_wrong_subtype": "Doğru saldırı ailesi, yanlış alt tür",
             "attack_predicted_benign": "Saldırı → benign", "benign_predicted_attack": "Benign → saldırı", "wrong_attack_family": "Yanlış saldırı ailesi"}
    for k, label in names.items():
        lines.append(f"| {label} | {cen['hierarchical_error_breakdown'][k]} | {fed['hierarchical_error_breakdown'][k]} |")
    lines += ["| **Toplam** | **6486** | **6486** |", "",
              "Her örnek tam bir kategoriye girer. Tam-doğru sayısı / 6486 alt tür doğruluğunu; (tam-doğru + doğru-aile/yanlış-alt-tür) / 6486 aile doğruluğunu verir. Saldırı→benign / 2648 tespit kaçırma oranıdır; benign→saldırı / 3838 yanlış alarm oranıdır.", "",
              "## Şekiller ve yeniden üretim", "",
              "![Metrik karşılaştırması](subtype_flower_val_v1/comparison.png)", "",
              "![Aile karışıklık matrisleri](subtype_flower_val_v1/family_confusion.png)", "",
              "![Yerel eğitim kaybı](subtype_flower_val_v1/training_loss.png)", "",
              "![Non-IID dağılım](subtype_flower_val_v1/client_distribution.png)", "",
              "Alt tür karışıklık şekli `subtype_flower_val_v1/subtype_confusion_observed.png`: 28 gözlenen gerçek sınıf × 84 tahmin sınıfı; tam 84×84 sayımlar CSV'de. Şekiller ayrıca SVG olarak saklandı.", "",
              "```bash", "/home/seniorfl/seniorproject-fl-venv/bin/python scripts/26_run_flower_subtype_val_v1.py --stage all", "```", "",
              "Yeni çalıştırmada mevcut deney çıktıları kasıtlı olarak korunur; bağımsız tekrar için yeni çıktı/model adları ve yeni yedek manifesti gerekir. Sadece doğrulamak için `--stage verify` kullanılabilir. Tam bağımlılıklar `requirements.freeze.txt`, ayarlar `config.json`, ortam `environment.json`, giriş SHA-256'ları `data_audit.json`, kaynak yedeği `backup.json`, tamamlanan deneyin kaynak kopyası `experiment_source.tar.gz`, komut ve log `launch.json` / `simulation.log` dosyalarındadır.", "",
              "Model: `models/subtype_flower_val_v1.pt`. `results/subtype_flower_val_v1/` içinde iki model için JSON metrikler, tahminler, 84×84 alt tür ve 8×8 aile matrisleri, sınıf/aile raporları, hiyerarşik dökümler, `rounds.csv` (15), `client_rounds.csv` (75), `comparison.csv`, sınıf kapsamı ve bütünlük manifestleri saklanır. `verification.json` son tutarlılık ve korunma kontrollerini kaydeder.", "",
              "## Yorum ve sınırlılıklar", "",
              f"Bu tek koşuda FedAvg'nin alt tür doğruluğu merkeziden {(fed['exact_subtype_accuracy']-cen['exact_subtype_accuracy'])*100:+.4f} yüzde puan, saldırı alt tür doğruluğu {(fed['attack_only_subtype_accuracy']-cen['attack_only_subtype_accuracy'])*100:+.4f} yüzde puan, aile doğruluğu {(fed['family_accuracy']-cen['family_accuracy'])*100:+.4f} yüzde puan farklıdır. Benign çoğunluğu nedeniyle genel doğruluk, saldırı alt tür başarısıyla birlikte okunmalıdır; güvenilirlik için birden çok tohum ve istemci dağılımı gerekir.", "",
              "- Episode ID'leri sezgisel aday gruplardır; eğitim/doğrulama saldırı episode kesişiminin sıfır olması bağımsız oturum garantisi vermez. Tam bağımsız oturum değerlendirmesi iddia edilmez.",
              "- Benign doğrulama zamansal holdout'tur; bağımsız benign episode ayrımı değildir.",
              "- **56/84 sınıf doğrulamada yoktur**; web ailesinin performansı ölçülmedi. 84 çıkışlı model, tam 84 sınıflı doğrulama kapsamı demek değildir.",
              "- Tek tohum, tek Non-IID bölüşüm ve sabit tam katılım kullanıldı; anlamlılık, güven aralığı veya genellenebilir üstünlük gösterilmedi. Yerel eğitimde görülmeyen saldırılara transfer, yeni yerel 84-sınıf modellerle aynı doğrulama üzerinde karşılaştırılmadan kanıtlanamaz.",
              "- Önceki yerel/8-sınıflı deneyler bu tablodaki 84-sınıflı sonuçlarla doğrudan eşdeğer kabul edilmez. Gerçek istemci gecikmesi, enerji tüketimi, iletişim maliyeti ve saldırı testbed'i bu çalışmada ölçülmedi.", "",
              "## Gelecek çalışma", "",
              "Aynı protokolde yerel 84-sınıf modelleri, istemcide görülmeyen sınıf analizi, çoklu tohum/dağılım ve kısmi katılım deneyleri; gerçek Raspberry Pi Flower istemcileri; izole Kali Linux IIoT saldırı testbed'inde kontrollü trafik değerlendirmesi; dashboard ve donanım çıkarım ölçümleri planlanmaktadır. Fiziksel testbed bu görevde uygulanmadı.", "",
              "API dayanağı: [Flower resmi ClientApp/ServerApp örneği](https://flower.ai/docs/framework/tutorial-series-get-started-with-flower-pytorch.html); kurulu 1.40.0 API imzaları ayrıca doğrudan kontrol edildi. Sayısal deney sonuçları yerel çalıştırmadan üretilmiştir.", ""]
    target = ROOT / "results/subtype_flower_val_v1_summary.md"
    with target.open("x", encoding="utf-8") as f:
        f.write("\n".join(lines))


def verify():
    before = json.loads((OUT / "preservation_before.json").read_text())
    changed = [name for name, digest in before.items() if not (ROOT / name).is_file() or sha(ROOT / name) != digest]
    assert not changed, changed
    audit_data = json.loads((OUT / "data_audit.json").read_text())
    assert all(sha(ROOT / p) == h for p, h in audit_data["sha256"].items())
    rounds = pd.read_csv(OUT / "rounds.csv")
    clients = pd.read_csv(OUT / "client_rounds.csv")
    assert rounds["round"].tolist() == list(range(1, 16))
    assert len(clients) == 75 and (rounds.clients == 5).all() and (rounds.total_examples == 22450).all()
    for _, group in clients.groupby("round"):
        assert group.client_id.tolist() == list(CLIENT_SIZES)
        assert group.num_examples.sum() == 22450 and np.isclose(group.aggregation_weight.sum(), 1)
    checks = {}
    for name in ["fedavg", "centralized_recomputed"]:
        m = json.loads((OUT / f"{name}_metrics.json").read_text())
        p = pd.read_csv(OUT / f"{name}_predictions.csv")
        cm = pd.read_csv(OUT / f"{name}_confusion.csv", index_col=0)
        fm = pd.read_csv(OUT / f"{name}_family_confusion.csv", index_col=0)
        assert len(p) == 6486 and cm.shape == (84, 84) and fm.shape == (8, 8)
        assert cm.to_numpy().sum() == fm.to_numpy().sum() == sum(m["hierarchical_error_breakdown"].values()) == 6486
        assert cm.index.tolist() == CLASSES and cm.columns.tolist() == CLASSES
        np.testing.assert_array_equal(cm.to_numpy(), confusion_matrix(p.true_subtype_id, p.predicted_subtype_id, labels=range(84)))
        assert p.hierarchical_category.value_counts().to_dict() == {k:v for k,v in m['hierarchical_error_breakdown'].items() if v}
        b = m["hierarchical_error_breakdown"]
        assert np.isclose(np.trace(cm) / 6486, m["exact_subtype_accuracy"])
        assert np.isclose((b["exact_correct"] + b["correct_family_wrong_subtype"]) / 6486, m["family_accuracy"])
        assert np.isclose(1 - b["attack_predicted_benign"] / 2648, m["attack_detection_recall"])
        assert np.isclose(b["benign_predicted_attack"] / 3838, m["benign_false_positive_rate"])
        checks[name] = {"predictions": len(p), "confusion_total": int(cm.to_numpy().sum()),
                        "hierarchical_total": sum(b.values()), "metrics_consistent": True}
    summary = ROOT / "results/subtype_flower_val_v1_summary.md"
    assert MODEL.stat().st_size > 0 and summary.stat().st_size > 0
    source_path = OUT / "experiment_source.tar.gz"
    if not source_path.exists():
        with tarfile.open(source_path, "x:gz") as archive:
            for p in sorted(APP.rglob("*")) + [Path(__file__).resolve()]:
                if p.is_file() and "__pycache__" not in p.parts:
                    archive.add(p, arcname=str(p.relative_to(ROOT)))
    write_json("verification.json", {"status": "passed", "protected_files_verified": len(before),
                                      "changed_historical_files": changed, "rounds": 15, "client_updates": 75,
                                      "checks": checks, "test_sets_accessed": False,
                                      "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    outputs = [p for p in OUT.rglob("*") if p.is_file() and p.name != "artifact_manifest.json"] + [MODEL, summary]
    write_json("artifact_manifest.json", {str(p.relative_to(ROOT)): {"bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(outputs)})
    print((OUT / "verification.json").read_text(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["audit", "train", "finalize", "verify", "all"], default="all")
    args = parser.parse_args()
    steps = {"audit": audit, "train": train, "finalize": finalize, "verify": verify}
    for name, fn in steps.items():
        if args.stage in [name, "all"]:
            print(f"=== {name} ===", flush=True)
            fn()
