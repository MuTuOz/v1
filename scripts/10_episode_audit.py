
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/all_attack_benign_samples"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

columns = [
    "label4",
    "label_full",
    "device_name",
    "timestamp_start"
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

df["time"] = pd.to_datetime(
    df["timestamp_start"],
    format="ISO8601",
    utc=True
)

df = df.sort_values(["label4", "time"]).copy()

# Farkli zaman boslugu esikleriyle
# olasi oturumlari incele.
for threshold in [60, 300]:

    gap = (
        df.groupby("label4")["time"]
        .diff()
        .dt.total_seconds()
    )

    new_episode = gap.isna() | (gap > threshold)

    df["episode"] = new_episode.groupby(
        df["label4"]
    ).cumsum()

    episodes = (
        df.groupby(["label4", "episode"])
        .agg(
            rows=("label4", "size"),
            devices=("device_name", "nunique"),
            first_seen=("time", "min"),
            last_seen=("time", "max")
        )
        .reset_index()
    )

    counts = (
        episodes.groupby("label4")
        .size()
        .sort_values()
    )

    print(f"\n=== GAP THRESHOLD: {threshold} saniye ===")
    print("Toplam sinif:", len(counts))
    print("Tahmini oturum sayisi:", len(episodes))
    print("Tek oturumlu sinif:", (counts == 1).sum())
    print("2+ oturumlu sinif:", (counts >= 2).sum())
    print("3+ oturumlu sinif:", (counts >= 3).sum())

    print("\nEn az oturumlu 15 sinif:")
    print(counts.head(15).to_string())

    print("\nEn fazla oturumlu 10 sinif:")
    print(counts.tail(10).to_string())

    episodes.to_csv(
        RESULTS / f"candidate_episodes_{threshold}s_5sec.csv",
        index=False
    )

print("\nOturum analizi tamamlandi.")
