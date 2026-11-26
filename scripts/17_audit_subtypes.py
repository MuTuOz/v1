
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "data/splits_v2"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

train = pd.read_csv(SPLITS / "train.csv")
test = pd.read_csv(SPLITS / "test_episode.csv")

def count_subtypes(df):
    attacks = df[df["label2"] != "benign"]
    labels = (
        attacks["label4"]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
    )
    return labels.value_counts(), int(labels.isna().sum())

train_counts, train_missing = count_subtypes(train)
test_counts, test_missing = count_subtypes(test)

train_labels = set(train_counts.index)
test_labels = set(test_counts.index)

print("\n=== LABEL4 SUBTYPE AUDIT ===")
print("Train subtypes:", len(train_labels))
print("Test subtypes:", len(test_labels))
print("Shared subtypes:", len(train_labels & test_labels))
print("Train-only subtypes:", len(train_labels - test_labels))
print("Test-only subtypes:", len(test_labels - train_labels))
print("Missing attack label4 in train:", train_missing)
print("Missing attack label4 in test:", test_missing)

print("\n=== RARE TRAIN SUBTYPES ===")
for threshold in (5, 10, 20):
    print(
        f"Classes with fewer than {threshold} samples:",
        int((train_counts < threshold).sum())
    )

print("\n=== TEST-ONLY SUBTYPES ===")
for label in sorted(test_labels - train_labels):
    print(label, ":", int(test_counts[label]))

print("\n=== LABEL4 TO FAMILY CONSISTENCY ===")
combined = pd.concat([train, test], ignore_index=True)
attacks = combined[combined["label2"] != "benign"].copy()
attacks["label4"] = (
    attacks["label4"]
    .astype("string")
    .str.strip()
    .replace("", pd.NA)
)
family_counts = (
    attacks.dropna(subset=["label4"])
    .groupby("label4")["label2"]
    .nunique()
)

print(
    "Subtypes mapped to multiple families:",
    int((family_counts > 1).sum())
)

summary = pd.DataFrame({
    "label4": sorted(train_labels | test_labels)
})
summary["train_count"] = (
    summary["label4"].map(train_counts).fillna(0).astype(int)
)
summary["test_count"] = (
    summary["label4"].map(test_counts).fillna(0).astype(int)
)

summary.to_csv(
    RESULTS / "label4_split_audit.csv",
    index=False
)

print("\nAudit saved to results/label4_split_audit.csv")
