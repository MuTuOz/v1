
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/all_attack_benign_samples"

columns = [
    "device_name",
    "label_full",
    "label1",
    "label2",
    "label3",
    "label4",
    "timestamp_start",
    "timestamp_end",
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

# Zaman bilgisini Python datetime formatına dönüştür.
df["start"] = pd.to_datetime(
    df["timestamp_start"],
    format="ISO8601",
    utc=True,
    errors="coerce"
)

df["end"] = pd.to_datetime(
    df["timestamp_end"],
    format="ISO8601",
    utc=True,
    errors="coerce"
)

# 1. Kayıtların zaman aralıklarını incele.
df["window_seconds"] = (
    df["end"] - df["start"]
).dt.total_seconds()

print("\n=== 1. ZAMAN ANALIZI ===")
print("En eski kayıt:", df["start"].min())
print("En yeni kayıt:", df["end"].max())
print("Geçersiz başlangıç zamanı:", df["start"].isna().sum())
print("Pencere süreleri:")
print(df["window_seconds"].value_counts().head(10))

# 2. Aynı senaryo/cihaz tanımındaki kayıtları incele.
scenario_summary = (
    df.groupby("label_full")
    .agg(
        records=("label_full", "size"),
        device=("device_name", "first"),
        attack_type=("label4", "first"),
        first_seen=("start", "min"),
        last_seen=("end", "max")
    )
    .sort_values("records", ascending=False)
)

print("\n=== 2. SENARYO ANALIZI ===")
print("Farklı label_full sayısı:", len(scenario_summary))
print(scenario_summary.head(10).to_string())

# 3. Tamamen aynı cihaz, zaman ve sınıf bilgisi
# tekrar ediyor mu?
duplicate_columns = [
    "device_name",
    "timestamp_start",
    "timestamp_end",
    "label4",
]

duplicates = df.duplicated(
    subset=duplicate_columns,
    keep=False
)

print("\n=== 3. TEKRAR EDEN METADATA ===")
print("Tekrarlanan metadata içeren satır:", duplicates.sum())

# 4. Aynı cihaz ve zaman penceresinde birden fazla
# sınıf etiketi bulunuyor mu?
time_groups = df.groupby([
    "device_name",
    "timestamp_start",
    "timestamp_end"
])["label4"].nunique()

conflicts = time_groups[time_groups > 1]

print("\n=== 4. ZAMAN / ETIKET CAKISMASI ===")
print("Birden fazla sınıf bulunan pencere:", len(conflicts))
print(conflicts.head(10).to_string())

# 5. Sonucu dosyaya kaydet.
results = ROOT / "results"
results.mkdir(exist_ok=True)

scenario_summary.to_csv(
    results / "scenario_timeline_5sec.csv"
)

print("\nAnaliz tamamlandı.")
