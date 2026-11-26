
from pathlib import Path
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TRAIN_PATH = ROOT / "data/splits_v2/train.csv"
CLIENT_DIR = ROOT / "data/fl_clients_v1"
OUTPUT = ROOT / "results/validation_group_audit.json"

train = pd.read_csv(TRAIN_PATH)

print("\n=== VALIDATION GROUP AUDIT ===")
print("Training rows:", len(train))
print("Columns:", len(train.columns))

print("\n=== POSSIBLE GROUPING COLUMNS ===")
keywords = (
    "time", "date", "episode", "session",
    "scenario", "capture", "device", "source",
    "file", "group", "attack"
)

candidates = [
    c for c in train.columns
    if any(word in c.lower() for word in keywords)
]

for col in candidates:
    print(
        f"{col}: unique={train[col].nunique(dropna=False)}, "
        f"missing={train[col].isna().sum()}"
    )
    print("  examples:", train[col].dropna().unique()[:3].tolist())

print("\n=== FAMILY DISTRIBUTION ===")
family_counts = train["label2"].value_counts()
print(family_counts.to_string())

print("\n=== SUBTYPE DISTRIBUTION ===")
subtype_counts = train["label4"].value_counts()
print("Subtypes:", len(subtype_counts))
print("Subtypes with fewer than 10 samples:",
      int((subtype_counts < 10).sum()))
print("Subtypes with fewer than 20 samples:",
      int((subtype_counts < 20).sum()))
print("\nRarest 15 subtypes:")
print(subtype_counts.tail(15).to_string())

print("\n=== CLIENT DATA CHECK ===")
client_counts = {}

for i in range(1, 6):
    path = CLIENT_DIR / f"client_{i}_train.csv"
    df = pd.read_csv(path)
    client_counts[f"client_{i}"] = len(df)
    print(f"Client {i}: {len(df)} rows")

print("Combined client rows:", sum(client_counts.values()))
print("Matches training row count:",
      sum(client_counts.values()) == len(train))

report = {
    "training_rows": len(train),
    "training_columns": len(train.columns),
    "columns": train.columns.tolist(),
    "candidate_group_columns": candidates,
    "family_counts": family_counts.to_dict(),
    "subtype_counts": subtype_counts.to_dict(),
    "client_counts": client_counts,
    "client_count_matches": sum(client_counts.values()) == len(train),
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("\nSaved:", OUTPUT)
