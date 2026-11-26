
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/all_attack_benign_samples"

columns = [
    "device_name",
    "label1",
    "label2",
    "label3",
    "label4",
    "network_packets_all_count",
    "log_messages_count",
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

print("TOPLAM KAYIT:", len(df))

# En az örneğe sahip sınıfları bulalım.
print("\nEN AZ ÖRNEK İÇEREN 10 SINIF:")
print(df["label4"].value_counts().tail(10))

# Aynı subtype birden fazla family altında var mı?
shared = attack.groupby("label3")["label2"].nunique()
shared = shared[shared > 1]

print("\nBİRDEN FAZLA FAMILY'DE BULUNAN SUBTYPE SAYISI:")
print(len(shared))
print(shared.head(10))

# Paket ve log gözlenmeyen zaman pencereleri.
df["no_activity"] = (
    (df["network_packets_all_count"] == 0)
    & (df["log_messages_count"] == 0)
)

print("\nPAKET VE LOG OLMAYAN KAYITLAR (%):")
print(
    (df.groupby("label1")["no_activity"].mean() * 100)
    .round(2)
)

print("\nSALDIRI AİLELERİNE GÖRE PAKET/LOG YOKLUĞU (%):")
print(
    (df.groupby("label2")["no_activity"].mean() * 100)
    .round(2)
)
