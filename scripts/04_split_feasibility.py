
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/all_attack_benign_samples"

columns = [
    "device_name",
    "label1",
    "label4",
    "label_full",
    "timestamp_start",
]

attack = pd.read_csv(
    DATA / "attack_data/attack_samples_5sec.csv",
    usecols=columns
)

benign = pd.read_csv(
    DATA / "benign_data/benign_samples_5sec.csv",
    usecols=columns
)

df = pd.concat([attack, benign], ignore_index=True)

# Her kaydın takvim gününü bul.
df["date"] = pd.to_datetime(
    df["timestamp_start"],
    format="ISO8601",
    utc=True
).dt.date

# Her sınıfın veri kapsamını ölç.
coverage = (
    df.groupby(["label1", "label4"])
    .agg(
        samples=("label4", "size"),
        devices=("device_name", "nunique"),
        days=("date", "nunique"),
        full_labels=("label_full", "nunique")
    )
    .reset_index()
)

print("\n=== SINIFLARIN GUN DAGILIMI ===")

print(
    coverage.groupby(["label1", "days"])
    .size()
)

print("\n=== TEK CIHAZDA BULUNAN SINIFLAR ===")

single_device = coverage[coverage["devices"] == 1]

print(single_device.to_string(index=False))

print("\n=== EN AZ ORNEKLI 15 SINIF ===")

print(
    coverage.sort_values("samples")
    .head(15)
    .to_string(index=False)
)

# label_full gerçekten tek cihaz mı içeriyor?
groups = (
    df.groupby("label_full")
    .agg(
        samples=("device_name", "size"),
        devices=("device_name", "nunique")
    )
    .sort_values("devices", ascending=False)
)

print("\n=== BIRDEN FAZLA CIHAZ ICEREN GRUPLAR ===")
print(groups.head(12).to_string())

# Araştırma sonucunu sakla.
results = ROOT / "results"
results.mkdir(exist_ok=True)

coverage.to_csv(
    results / "class_coverage_5sec.csv",
    index=False
)

print("\nAnaliz tamamlandi.")
