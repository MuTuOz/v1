
from pathlib import Path
import pandas as pd

# Projenin ana klasörü
ROOT = Path(__file__).resolve().parents[1]

# Dataset klasörü
DATA = ROOT / "data" / "raw" / "all_attack_benign_samples"

files = {
    "Attack": DATA / "attack_data" / "attack_samples_5sec.csv",
    "Benign": DATA / "benign_data" / "benign_samples_5sec.csv",
}

# İlk aşamada sadece etiketleri ve cihaz bilgilerini inceliyoruz.
wanted_columns = [
    "device_name",
    "label1",
    "label2",
    "label3",
    "label4",
    "timestamp_start",
]

for name, filepath in files.items():

    # CSV'nin mevcut sütunlarını öğren.
    available = pd.read_csv(filepath, nrows=0).columns
    columns = [c for c in wanted_columns if c in available]

    # Yalnızca istediğimiz sütunları oku.
    df = pd.read_csv(filepath, usecols=columns)

    print(f"\n===== {name.upper()} DATASET =====")
    print("Satır sayısı:", len(df))
    print("İncelenen sütunlar:", list(df.columns))

    if "device_name" in df:
        print("Cihaz sayısı:", df["device_name"].nunique())

    for label in ["label1", "label2", "label3", "label4"]:
        if label in df:
            print(f"\n{label}:")
            print("Benzersiz değer sayısı:", df[label].nunique())
            print(df[label].value_counts(dropna=False).head(15))

    # Saldırı family-subtype dağılımını kaydet.
    if name == "Attack" and {"label2", "label3"}.issubset(df.columns):
        taxonomy = (
            df.groupby(["label2", "label3"], dropna=False)
            .size()
            .reset_index(name="sample_count")
            .sort_values("sample_count", ascending=False)
        )

        output = ROOT / "results"
        output.mkdir(exist_ok=True)

        taxonomy.to_csv(
            output / "attack_taxonomy_5sec.csv",
            index=False
        )

        print("\nTaxonomy dosyası oluşturuldu.")
