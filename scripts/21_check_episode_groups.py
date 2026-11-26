
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "data" / "splits_v2"
CLIENTS = ROOT / "data" / "fl_clients_v1"

COLS = ["episode_id", "label2", "label4"]

train = pd.read_csv(SPLITS / "train.csv", usecols=COLS)
test = pd.read_csv(
    SPLITS / "test_episode.csv", usecols=COLS
)

print("\n=== 1. EPISODE GROUP AUDIT ===")

groups = train.groupby(
    "episode_id", dropna=False
).agg(
    rows=("label2", "size"),
    families=("label2", "nunique"),
    subtypes=("label4", "nunique")
)

print("Train episodes:", len(groups))
print("Missing episode IDs:",
      int(train["episode_id"].isna().sum()))

print("\nLargest 10 episodes:")
print(groups.sort_values(
    "rows", ascending=False
).head(10).to_string())

print("\n=== 2. EPISODES PER FAMILY ===")

family_groups = {}

for family, df in train.groupby("label2"):
    count = int(df["episode_id"].nunique())
    family_groups[family] = count
    print(
        f"{family:12s} | rows={len(df):5d}"
        f" | episodes={count}"
    )

print("\n=== 3. SUBTYPE GROUP COVERAGE ===")

subtype_groups = train.groupby(
    "label4"
)["episode_id"].nunique()

few_groups = subtype_groups[subtype_groups < 2]

print("Total classes:", len(subtype_groups))
print("Classes with fewer than 2 episodes:",
      len(few_groups))
print(few_groups.to_string())

print("\n=== 4. TRAIN / TEST OVERLAP ===")

train_ids = set(train["episode_id"].dropna())
test_ids = set(test["episode_id"].dropna())

shared = train_ids & test_ids

print("Train groups:", len(train_ids))
print("Test groups:", len(test_ids))
print("Shared episode IDs:", len(shared))
print(
    "Test rows with shared episode IDs:",
    int(test["episode_id"].isin(shared).sum())
)

if shared:
    print("Example shared IDs:", sorted(map(str, shared))[:10])

print("\n=== 5. EPISODES ACROSS CLIENTS ===")

client_groups = {}

for i in range(1, 6):
    df = pd.read_csv(
        CLIENTS / f"client_{i}_train.csv",
        usecols=COLS
    )
    client_groups[i] = set(df["episode_id"].dropna())
    print(
        f"Client {i}: {len(df)} rows, "
        f"{len(client_groups[i])} episodes"
    )

overlaps = {}

for i in range(1, 6):
    for j in range(i + 1, 6):
        common = client_groups[i] & client_groups[j]
        overlaps[f"{i}-{j}"] = len(common)

print("\nShared episode IDs between clients:")
print(overlaps)

print("\n=== 6. SAVE REPORT ===")

report = {
    "train_episode_count": len(train_ids),
    "test_episode_count": len(test_ids),
    "train_test_shared_episode_count": len(shared),
    "test_rows_with_shared_episode_ids": int(
        test["episode_id"].isin(shared).sum()
    ),
    "family_episode_counts": family_groups,
    "subtypes_with_fewer_than_2_groups": {
        str(k): int(v) for k, v in few_groups.items()
    },
    "cross_client_episode_overlap": overlaps,
    "mixed_family_episode_groups": int(
        (groups["families"] > 1).sum()
    ),
    "mixed_subtype_episode_groups": int(
        (groups["subtypes"] > 1).sum()
    )
}

out = ROOT / "results" / "episode_group_feasibility.json"
out.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("Saved:", out)
