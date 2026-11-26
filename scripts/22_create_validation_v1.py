
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/splits_v2/train.csv"
TEST = ROOT / "data/splits_v2/test_episode.csv"
CLIENTS = ROOT / "data/fl_clients_v1"
OUT = ROOT / "data/validation_v1"
REPORT = ROOT / "results/validation_v1_manifest.json"

SEED = 42
VAL_FRACTION = 0.20
GAP_MINUTES = 5

rng = np.random.default_rng(SEED)

train = pd.read_csv(SOURCE)

# 1. Verify existing train/test attack-group separation.
test_ids = pd.read_csv(
    TEST, usecols=["episode_id", "label2"]
)

train_attack_ids = set(
    train.loc[
        train["label2"] != "benign", "episode_id"
    ]
)
test_attack_ids = set(
    test_ids.loc[
        test_ids["label2"] != "benign", "episode_id"
    ]
)

attack_test_overlap = train_attack_ids & test_attack_ids

if attack_test_overlap:
    raise RuntimeError(
        "Attack episode IDs overlap with the test set: "
        + str(sorted(attack_test_overlap)[:10])
    )

# 2. Choose whole attack episodes for validation.
attack = train[train["label2"] != "benign"]

mixed = attack.groupby("episode_id")["label4"].nunique()

if (mixed > 1).any():
    raise RuntimeError(
        "Some attack episodes contain multiple subtypes."
    )

selected_episodes = set()
single_episode_subtypes = []

for subtype, df in attack.groupby("label4"):
    episodes = sorted(df["episode_id"].unique())

    if len(episodes) < 2:
        single_episode_subtypes.append(str(subtype))
        continue

    n_select = max(
        1, round(len(episodes) * VAL_FRACTION)
    )
    n_select = min(n_select, len(episodes) - 1)

    selected = rng.choice(
        episodes, size=n_select, replace=False
    )
    selected_episodes.update(selected.tolist())

# 3. Split benign traffic chronologically.
benign = train[train["label2"] == "benign"]
benign_times = pd.to_datetime(
    benign["timestamp_start"], utc=True
)

ordered_times = (
    benign_times.drop_duplicates()
    .sort_values()
    .reset_index(drop=True)
)

if len(ordered_times) < 2:
    raise RuntimeError(
        "Not enough benign timestamps for a time split."
    )

cutoff_index = int(
    len(ordered_times) * (1 - VAL_FRACTION)
)
cutoff_index = min(
    cutoff_index, len(ordered_times) - 1
)

cutoff = ordered_times.iloc[cutoff_index]
train_end = cutoff - pd.Timedelta(
    minutes=GAP_MINUTES
)

def make_masks(df):
    times = pd.to_datetime(
        df["timestamp_start"], utc=True
    )

    is_attack = df["label2"] != "benign"

    val_attack = (
        is_attack
        & df["episode_id"].isin(selected_episodes)
    )
    train_attack = (
        is_attack
        & ~df["episode_id"].isin(selected_episodes)
    )

    is_benign = ~is_attack

    val_benign = is_benign & (times >= cutoff)
    train_benign = is_benign & (times < train_end)

    training = train_attack | train_benign
    validation = val_attack | val_benign
    excluded = ~(training | validation)

    assert not (training & validation).any()

    return training, validation, excluded

train_mask, val_mask, excluded_mask = make_masks(train)

new_train = train.loc[train_mask].copy()
validation = train.loc[val_mask].copy()

# 4. Safety checks.
assert len(new_train) + len(validation) + int(
    excluded_mask.sum()
) == len(train)

assert set(new_train["label4"]) == set(train["label4"])

new_attack_ids = set(
    new_train.loc[
        new_train["label2"] != "benign", "episode_id"
    ]
)
val_attack_ids = set(
    validation.loc[
        validation["label2"] != "benign", "episode_id"
    ]
)

assert not (new_attack_ids & val_attack_ids)

new_benign_times = pd.to_datetime(
    new_train.loc[
        new_train["label2"] == "benign", "timestamp_start"
    ], utc=True
)
val_benign_times = pd.to_datetime(
    validation.loc[
        validation["label2"] == "benign", "timestamp_start"
    ], utc=True
)

assert new_benign_times.max() < val_benign_times.min()

# 5. Prepare client-specific training and validation.
client_outputs = {}
total_client_train = 0
total_client_val = 0
total_client_excluded = 0

client_frames = []

for client_id in range(1, 6):
    df = pd.read_csv(
        CLIENTS / f"client_{client_id}_train.csv"
    )

    client_frames.append(df)

    ct, cv, ce = make_masks(df)

    client_outputs[client_id] = {
        "train": df.loc[ct].copy(),
        "validation": df.loc[cv].copy(),
        "excluded": int(ce.sum()),
    }

    total_client_train += int(ct.sum())
    total_client_val += int(cv.sum())
    total_client_excluded += int(ce.sum())

assert sum(len(df) for df in client_frames) == len(train)

assert total_client_train == len(new_train)
assert total_client_val == len(validation)
assert total_client_excluded == int(excluded_mask.sum())

# 6. Save new files, never modify original splits.
if OUT.exists() and any(OUT.iterdir()):
    raise RuntimeError(
        f"Output directory is not empty: {OUT}. "
        "Refusing to overwrite a previous split."
    )

OUT.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)

new_train.to_csv(OUT / "train.csv", index=False)
validation.to_csv(OUT / "validation.csv", index=False)

for client_id, partitions in client_outputs.items():
    partitions["train"].to_csv(
        OUT / f"client_{client_id}_train.csv",
        index=False
    )
    partitions["validation"].to_csv(
        OUT / f"client_{client_id}_val.csv",
        index=False
    )

report = {
    "split_name": "hybrid_validation_v1",
    "seed": SEED,
    "original_train_rows": len(train),
    "new_train_rows": len(new_train),
    "validation_rows": len(validation),
    "excluded_benign_gap_rows": int(excluded_mask.sum()),
    "benign_validation_cutoff": cutoff.isoformat(),
    "benign_gap_minutes": GAP_MINUTES,
    "selected_attack_episode_ids": sorted(
        selected_episodes
    ),
    "selected_attack_episode_count": len(
        selected_episodes
    ),
    "single_episode_subtypes_kept_in_train":
        single_episode_subtypes,
    "train_family_counts": new_train[
        "label2"
    ].value_counts().to_dict(),
    "validation_family_counts": validation[
        "label2"
    ].value_counts().to_dict(),
    "train_subtype_count": int(
        new_train["label4"].nunique()
    ),
    "validation_subtype_count": int(
        validation["label4"].nunique()
    ),
    "attack_episode_train_val_overlap": len(
        new_attack_ids & val_attack_ids
    ),
    "attack_episode_train_test_overlap": len(
        attack_test_overlap
    ),
    "client_counts": {
        str(i): {
            "train": len(client_outputs[i]["train"]),
            "validation": len(
                client_outputs[i]["validation"]
            ),
            "excluded": client_outputs[i]["excluded"]
        }
        for i in range(1, 6)
    },
    "limitations": [
        "Attack episodes are heuristic candidates, "
        "not independently verified sessions.",
        "Benign samples use a temporal holdout, "
        "not independent episode groups.",
        "Singleton attack subtypes are not "
        "represented in attack validation.",
        "The held-out subtype distribution "
        "may differ from the original dataset."
    ]
}

REPORT.write_text(
    json.dumps(
        report, indent=2, ensure_ascii=False
    ),
    encoding="utf-8"
)

print("\n=== VALIDATION V1 CREATED ===")
print("Original train:", len(train))
print("New train:", len(new_train))
print("Validation:", len(validation))
print("Benign gap exclusions:", int(excluded_mask.sum()))
print("Attack episodes held out:", len(selected_episodes))
print("Train subtypes:", new_train["label4"].nunique())
print("Validation subtypes:", validation["label4"].nunique())

print("\nValidation family distribution:")
print(
    validation["label2"].value_counts().to_string()
)

print("\nClient distributions:")
for client_id, p in client_outputs.items():
    print(
        f"Client {client_id}: "
        f"train={len(p['train'])}, "
        f"val={len(p['validation'])}"
    )

print("\nAttack episode overlap (train/val):",
      len(new_attack_ids & val_attack_ids))
print("Attack episode overlap (train/test):",
      len(attack_test_overlap))

print("\nSaved data:", OUT)
print("Saved report:", REPORT)
