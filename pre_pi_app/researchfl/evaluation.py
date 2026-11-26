"""One frozen evaluation protocol shared by every pre-Pi model and subset."""
from functools import lru_cache
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from .common import CLASSES, CLASS_TO_ID, FAMILY_OF, SCHEMA, MLP, dump, prepare


@lru_cache(maxsize=1)
def hcm_lookup(root):
    sys.path.insert(0, str(Path(root) / "scripts"))
    from hcm_eval import project_hierarchy
    tree, leaves = project_hierarchy(SCHEMA)
    return np.array([[tree.contribution(leaves[t], leaves[p]).values() for p in CLASSES] for t in CLASSES], dtype=np.int64)


def masks_for_support(training_subtypes, validation_subtypes):
    """Client-relative masks use frozen training support and true labels only."""
    local = set(training_subtypes)
    global_attacks = set(CLASSES) - {"benign"}
    local_families = {FAMILY_OF[s] for s in local} - {"benign"}
    missing = global_attacks - local
    y = np.asarray(validation_subtypes)
    families = np.array([FAMILY_OF[s] for s in y])
    unseen_subtype = np.isin(y, sorted(missing))
    unseen_family = (families != "benign") & ~np.isin(families, sorted(local_families))
    known_family_unseen_subtype = unseen_subtype & np.isin(families, sorted(local_families))
    if not np.array_equal(unseen_subtype, unseen_family | known_family_unseen_subtype):
        raise ValueError("Client-relative unseen masks must partition missing attack subtypes")
    return {"A_unseen_subtype": unseen_subtype, "B_unseen_family": unseen_family,
            "C_unseen_subtype_known_family": known_family_unseen_subtype}


def score(y, p, root):
    from hcm_eval import Counts, metrics as hm
    y, p = np.asarray(y, dtype=np.int64), np.asarray(p, dtype=np.int64)
    if len(y) != len(p) or np.any(y < 0) or np.any(y >= 84) or np.any(p < 0) or np.any(p >= 84):
        raise ValueError("Invalid label vectors")
    if not len(y):
        return {"samples": 0, "observed_subtypes": 0, "status": "unsupported_empty_subset",
                "exact_subtype_accuracy": None, "subtype_macro_f1_observed": None,
                "attack_only_subtype_accuracy": None, "attack_only_subtype_macro_f1": None,
                "family_accuracy": None, "family_macro_f1_observed": None,
                "attack_detection_recall": None, "benign_false_positive_rate": None,
                "hcm_f1": None, "hcm_counts": dict(zip(["tp", "tn", "fp", "fn"], [0]*4)),
                "hcm_metrics": hm(Counts()), "hierarchical_errors": {}}
    ts, ps = np.asarray(CLASSES)[y], np.asarray(CLASSES)[p]
    tf = np.array([FAMILY_OF[s] for s in ts]); pf = np.array([FAMILY_OF[s] for s in ps])
    attack = tf != "benign"; exact = y == p
    categories = {"exact_correct": exact,
                  "correct_family_wrong_subtype": attack & ~exact & (tf == pf),
                  "attack_predicted_benign": attack & (pf == "benign"),
                  "benign_predicted_attack": ~attack & (pf != "benign"),
                  "wrong_attack_family": attack & (pf != "benign") & (tf != pf)}
    if not np.all(np.stack(list(categories.values())).sum(axis=0) == 1):
        raise ValueError("Error categories must be disjoint and exhaustive")
    h = Counts(*(int(n) for n in hcm_lookup(str(root))[y, p].sum(axis=0)))
    hmetrics = hm(h)
    observed = sorted(np.unique(y).tolist())
    attack_labels = [i for i in observed if i != 0]
    return {"samples": len(y), "observed_subtypes": len(observed), "observed_families": len(set(tf)),
            "status": "evaluated", "exact_subtype_accuracy": float(np.mean(exact)),
            "subtype_macro_f1_observed": float(f1_score(y, p, labels=observed, average="macro", zero_division=0)),
            "attack_only_subtype_accuracy": float(np.mean(exact[attack])) if attack.any() else None,
            "attack_only_subtype_macro_f1": float(f1_score(y[attack], p[attack], labels=attack_labels, average="macro", zero_division=0)) if attack.any() else None,
            "family_accuracy": float(np.mean(tf == pf)),
            "family_macro_f1_observed": float(f1_score(tf, pf, labels=sorted(set(tf)), average="macro", zero_division=0)),
            "attack_detection_recall": float(np.mean(pf[attack] != "benign")) if attack.any() else None,
            "benign_false_positive_rate": float(np.mean(pf[~attack] != "benign")) if (~attack).any() else None,
            "attack_samples": int(attack.sum()), "benign_samples": int((~attack).sum()),
            "hcm_counts": h.to_dict(), "hcm_metrics": hmetrics, "hcm_f1": hmetrics["f1"],
            "hierarchical_errors": {k: int(v.sum()) for k,v in categories.items()}}


def evaluate_checkpoint(root, checkpoint, destination):
    root, destination = Path(root), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "metrics.json").exists():
        raise FileExistsError(destination)
    data = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if data["classes"] != CLASSES or data["family_of"] != FAMILY_OF:
        raise ValueError("Checkpoint label schema changed")
    val = pd.read_csv(root / "data/validation_v1/validation.csv")
    y = val.label4.map(CLASS_TO_ID).to_numpy(np.int64)
    model = MLP(len(data["features"])); model.load_state_dict(data["state_dict"]); model.eval()
    with torch.inference_mode():
        p = np.concatenate([model(x).argmax(1).numpy() for x in prepare(val, data["features"]).split(512)])
    evaluate_predictions(root, val, y, p, destination)
    return p


def evaluate_predictions(root, val, y, p, dest):
    m = score(y, p, root); dump(Path(dest) / "metrics.json", m)
    ps = np.asarray(CLASSES)[p]; tf = val.label2.to_numpy(); pf = np.array([FAMILY_OF[s] for s in ps])
    out = pd.DataFrame({"validation_row": range(len(y)), "true_subtype_id": y, "predicted_subtype_id": p,
                        "true_subtype": np.asarray(CLASSES)[y], "predicted_subtype": ps,
                        "true_family": tf, "predicted_family": pf, "episode_id": val.episode_id.to_numpy()})
    out.to_csv(Path(dest)/"predictions.csv", index=False)
    families = ["benign"] + sorted(set(FAMILY_OF.values()) - {"benign"})
    for name, t, pred, labs, names in [("subtype",y,p,list(range(84)),CLASSES),
                                       ("family",tf,pf,families,families),
                                       ("detection",(tf!="benign").astype(int),(pf!="benign").astype(int),[0,1],["benign","attack"])]:
        pd.DataFrame(confusion_matrix(t, pred, labels=labs), index=names, columns=names).to_csv(Path(dest)/f"{name}_confusion.csv")
        pd.DataFrame(classification_report(t, pred, labels=labs, target_names=names,
                                          output_dict=True, zero_division=0)).T.to_csv(Path(dest)/f"{name}_report.csv")
    contributions = hcm_lookup(str(root))[y,p]
    pd.DataFrame(contributions, columns=["tp","tn","fp","fn"]).to_csv(Path(dest)/"sample_hcm.csv", index=False)


def unseen_analysis(root, prediction_path, partition, destination, experiment_id):
    from .common import train_path
    df = pd.read_csv(prediction_path)
    y = df.true_subtype_id.to_numpy(); p = df.predicted_subtype_id.to_numpy()
    rows = []; perclass = []; mask_rows = []
    for client in range(1,6):
        path = train_path(root, {"partition":partition}, client)
        training = pd.read_csv(path, usecols=["label4"])
        masks = masks_for_support(set(training.label4), df.true_subtype)
        for label, mask in masks.items():
            m = score(y[mask],p[mask],root)
            rows.append({"experiment_id":experiment_id,"client_id":client,"subset":label,
                         **{k:v for k,v in m.items() if not isinstance(v,dict)}})
            mask_rows.extend({"client_id":client,"subset":label,"validation_row":int(i)} for i in np.flatnonzero(mask))
            for subtype in np.unique(y[mask]):
                select = mask & (y==subtype)
                perclass.append({"experiment_id":experiment_id,"client_id":client,"subset":label,
                                 "subtype":CLASSES[subtype],"family":FAMILY_OF[CLASSES[subtype]],
                                 "samples":int(select.sum()),"exact_subtype_accuracy":float(np.mean(p[select]==y[select])),
                                 "family_accuracy":float(np.mean([FAMILY_OF[CLASSES[a]]==FAMILY_OF[CLASSES[b]] for a,b in zip(y[select],p[select])]))})
    destination=Path(destination); destination.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(destination/"locally_unseen.csv",index=False)
    pd.DataFrame(perclass).to_csv(destination/"locally_unseen_per_class.csv",index=False)
    pd.DataFrame(mask_rows,columns=["client_id","subset","validation_row"]).to_csv(destination/"evaluation_masks.csv",index=False)
    return rows
