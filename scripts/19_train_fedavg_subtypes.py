
from pathlib import Path
import json
import random

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import accuracy_score, f1_score, classification_report

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "data/splits_v2"
CLIENT_DIR = ROOT / "data/fl_clients_v1"
RESULTS = ROOT / "results"
MODELS = ROOT / "models"

RESULTS.mkdir(exist_ok=True)
MODELS.mkdir(exist_ok=True)

SEED = 42
ROUNDS = 15
LOCAL_EPOCHS = 1
BATCH_SIZE = 128
LR = 0.001

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.set_num_threads(min(4, torch.get_num_threads()))

train = pd.read_csv(SPLITS / "train.csv")
test = pd.read_csv(SPLITS / "test_episode.csv")

FEATURES = [
    c for c in train.columns
    if c.startswith(("network_", "log_"))
]
assert len(FEATURES) == 71


def get_target(df):
    y = df["label4"].astype("string").str.strip()
    y.loc[df["label2"] == "benign"] = "benign"
    assert y.notna().all() and (y != "").all()
    return y.astype(str).to_numpy()


def prepare(df):
    x = df[FEATURES].to_numpy(dtype=np.float64)
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    x = np.clip(x, -1e8, 1e8)
    x = np.sign(x) * np.log1p(np.abs(x))
    return torch.from_numpy(x.astype(np.float32))


train_labels = get_target(train)
test_labels = get_target(test)

ATTACK_CLASSES = sorted(set(train_labels) - {"benign"})
CLASSES = ["benign"] + ATTACK_CLASSES
CLASS_TO_ID = {label: i for i, label in enumerate(CLASSES)}

assert len(CLASSES) == 84
assert set(test_labels).issubset(set(CLASSES))

mapping = pd.DataFrame({
    "subtype": train_labels,
    "family": train["label2"].astype(str).to_numpy()
})

assert (mapping.groupby("subtype")["family"].nunique() == 1).all()

FAMILY_OF = (
    mapping.drop_duplicates("subtype")
    .set_index("subtype")["family"]
    .to_dict()
)

assert all(
    FAMILY_OF[subtype] == family
    for subtype, family in zip(
        test_labels, test["label2"].astype(str)
    )
)

ATTACK_FAMILIES = set(FAMILY_OF.values()) - {"benign"}


class MLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(71, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, len(CLASSES))
        )

    def forward(self, x):
        return self.net(x)


clients = []

for client_id in range(1, 6):
    df = pd.read_csv(
        CLIENT_DIR / f"client_{client_id}_train.csv"
    )

    client_features = [
        c for c in df.columns
        if c.startswith(("network_", "log_"))
    ]
    assert client_features == FEATURES

    labels = get_target(df)
    assert set(labels).issubset(set(CLASSES))

    clients.append({
        "id": client_id,
        "x": prepare(df),
        "y": torch.tensor(
            [CLASS_TO_ID[label] for label in labels],
            dtype=torch.long
        ),
        "size": len(df),
        "seen_subtypes": set(labels) - {"benign"},
        "seen_families": set(df["label2"]) - {"benign"}
    })

TOTAL = sum(client["size"] for client in clients)
assert TOTAL == len(train) == 31216

model = MLP()
criterion = nn.CrossEntropyLoss()
history = []

print("\n=== SUBTYPE FEDAVG CONFIGURATION ===")
print("Clients:", len(clients))
print("Training records:", TOTAL)
print("Output classes:", len(CLASSES))
print("Rounds:", ROUNDS)
print("Local epochs per round:", LOCAL_EPOCHS)

for round_num in range(1, ROUNDS + 1):

    global_weights = {
        k: v.detach().clone()
        for k, v in model.state_dict().items()
    }

    aggregated = {
        k: torch.zeros_like(v)
        for k, v in global_weights.items()
    }

    total_loss = 0.0

    for client in clients:
        local_model = MLP()
        local_model.load_state_dict(global_weights)
        local_model.train()

        optimizer = torch.optim.Adam(
            local_model.parameters(), lr=LR
        )

        generator = torch.Generator().manual_seed(
            SEED + round_num * 100 + client["id"]
        )

        loader = DataLoader(
            TensorDataset(client["x"], client["y"]),
            batch_size=BATCH_SIZE,
            shuffle=True,
            generator=generator
        )

        client_loss = 0.0

        for _ in range(LOCAL_EPOCHS):
            for xb, yb in loader:
                optimizer.zero_grad()
                logits = local_model(xb)
                loss = criterion(logits, yb)
                loss.backward()
                optimizer.step()
                client_loss += loss.item() * len(xb)

        weight = client["size"] / TOTAL

        for k, v in local_model.state_dict().items():
            aggregated[k].add_(v, alpha=weight)

        total_loss += client_loss

    model.load_state_dict(aggregated)

    avg_loss = total_loss / TOTAL
    history.append({
        "round": round_num,
        "weighted_train_loss": avg_loss
    })

    print(
        f"Round {round_num:02d}/{ROUNDS} | "
        f"Weighted train loss: {avg_loss:.4f}"
    )


# Test only after training.
model.eval()

with torch.no_grad():
    pred_ids = model(prepare(test)).argmax(1).numpy()

pred_labels = np.array([CLASSES[i] for i in pred_ids])
y_test = np.array([CLASS_TO_ID[x] for x in test_labels])

true_family = test["label2"].astype(str).to_numpy()
pred_family = np.array([FAMILY_OF[x] for x in pred_labels])

tested_ids = sorted(set(y_test.tolist()))
family_labels = sorted(set(true_family))

sub_acc = accuracy_score(y_test, pred_ids)
sub_f1 = f1_score(
    y_test, pred_ids,
    labels=tested_ids,
    average="macro",
    zero_division=0
)

fam_acc = accuracy_score(true_family, pred_family)
fam_f1 = f1_score(
    true_family, pred_family,
    labels=family_labels,
    average="macro",
    zero_division=0
)

exact_correct = int(np.sum(test_labels == pred_labels))
within_family = int(np.sum(
    (true_family == pred_family)
    & (test_labels != pred_labels)
))
attack_to_benign = int(np.sum(
    (true_family != "benign")
    & (pred_family == "benign")
))
benign_to_attack = int(np.sum(
    (true_family == "benign")
    & (pred_family != "benign")
))
wrong_attack_family = int(np.sum(
    (true_family != "benign")
    & (pred_family != "benign")
    & (true_family != pred_family)
))

assert (
    exact_correct + within_family
    + attack_to_benign + benign_to_attack
    + wrong_attack_family == len(test)
)

print("\n=== FEDAVG SUBTYPE RESULTS ===")
print("Exact subtype accuracy:", round(sub_acc, 4))
print("Subtype Macro F1:", round(sub_f1, 4))
print("Family accuracy:", round(fam_acc, 4))
print("Family Macro F1:", round(fam_f1, 4))

print("\n=== HIERARCHICAL ERROR BREAKDOWN ===")
print("Exact correct:", exact_correct)
print("Correct family, wrong subtype:", within_family)
print("Attack predicted benign:", attack_to_benign)
print("Benign predicted attack:", benign_to_attack)
print("Wrong attack family:", wrong_attack_family)

print("\n=== FAMILY CLASSIFICATION REPORT ===")
print(classification_report(
    true_family, pred_family,
    labels=family_labels,
    zero_division=0
))


# Two distinct locally unseen evaluations.
unseen_rows = []

print("\n=== LOCALLY UNSEEN EVALUATION ===")

for client in clients:
    missing_subtypes = (
        set(ATTACK_CLASSES) - client["seen_subtypes"]
    )
    subtype_mask = np.isin(
        test_labels, list(missing_subtypes)
    )
    subtype_n = int(subtype_mask.sum())

    subtype_score = (
        float(np.mean(
            test_labels[subtype_mask]
            == pred_labels[subtype_mask]
        ))
        if subtype_n else None
    )

    missing_families = (
        ATTACK_FAMILIES - client["seen_families"]
    )
    family_mask = np.isin(
        true_family, list(missing_families)
    )
    family_n = int(family_mask.sum())

    family_score = (
        float(np.mean(
            true_family[family_mask]
            == pred_family[family_mask]
        ))
        if family_n else None
    )

    unseen_rows.append({
        "client_id": client["id"],
        "unseen_subtype_samples": subtype_n,
        "unseen_subtype_exact_accuracy": subtype_score,
        "unseen_family_samples": family_n,
        "unseen_family_accuracy": family_score
    })

    print(
        f"Client {client['id']} | "
        f"Subtype unseen: {subtype_n}, "
        f"accuracy: {subtype_score} | "
        f"Family unseen: {family_n}, "
        f"accuracy: {family_score}"
    )


# Web diagnostic is NOT independent episode testing.
web = pd.read_csv(
    SPLITS / "test_web_diagnostic.csv"
)
web_true = get_target(web)

with torch.no_grad():
    web_ids = model(prepare(web)).argmax(1).numpy()

web_pred = np.array([CLASSES[i] for i in web_ids])
web_families = np.array([FAMILY_OF[x] for x in web_pred])

web_family_recall = float(np.mean(web_families == "web"))
web_subtype_accuracy = float(np.mean(web_pred == web_true))

print("\n=== WEB DIAGNOSTIC ===")
print("Web records:", len(web))
print("Web family recall:", round(web_family_recall, 4))
print("Web exact subtype accuracy:", round(web_subtype_accuracy, 4))
print("(Not an independent episode test)")


# Save outputs.
torch.save({
    "state_dict": model.state_dict(),
    "features": FEATURES,
    "classes": CLASSES,
    "family_of": FAMILY_OF,
    "rounds": ROUNDS,
    "local_epochs": LOCAL_EPOCHS,
    "preprocessing": "signed_log1p_clip_1e8"
}, MODELS / "subtype_fedavg_mlp.pt")

pd.DataFrame(history).to_csv(
    RESULTS / "subtype_fedavg_rounds.csv",
    index=False
)

pd.DataFrame(unseen_rows).to_csv(
    RESULTS / "subtype_fedavg_unseen.csv",
    index=False
)

predictions = pd.DataFrame({
    "true_family": true_family,
    "pred_family": pred_family,
    "true_subtype": test_labels,
    "pred_subtype": pred_labels
})

if "label3" in test.columns:
    predictions["true_label3"] = test["label3"].values

predictions.to_csv(
    RESULTS / "subtype_fedavg_predictions.csv",
    index=False
)

report = classification_report(
    y_test, pred_ids,
    labels=tested_ids,
    target_names=[CLASSES[i] for i in tested_ids],
    output_dict=True,
    zero_division=0
)

pd.DataFrame(report).T.to_csv(
    RESULTS / "subtype_fedavg_report.csv"
)

metrics = {
    "subtype_accuracy": float(sub_acc),
    "subtype_macro_f1": float(sub_f1),
    "family_accuracy": float(fam_acc),
    "family_macro_f1": float(fam_f1),
    "exact_correct": exact_correct,
    "within_family_errors": within_family,
    "attack_to_benign": attack_to_benign,
    "benign_to_attack": benign_to_attack,
    "cross_attack_family": wrong_attack_family,
    "web_family_recall_diagnostic": web_family_recall,
    "web_subtype_accuracy_diagnostic": web_subtype_accuracy,
    "tested_classes": len(tested_ids)
}

with open(
    RESULTS / "subtype_fedavg_metrics.json",
    "w", encoding="utf-8"
) as f:
    json.dump(metrics, f, indent=2)

print("\nFedAvg subtype model and results saved.")
