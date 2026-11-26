
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/all_attack_benign_samples"
OUT = ROOT / "data/splits_v1"
OUT.mkdir(parents=True, exist_ok=True)

THRESHOLD = 300

attack = pd.read_csv(
    DATA / "attack_data/attack_samples_5sec.csv"
)
benign = pd.read_csv(
    DATA / "benign_data/benign_samples_5sec.csv"
)

# Modelin kullanacagi ozellikler.
features = [
    c for c in attack.select_dtypes(include="number").columns
    if c.startswith(("network_", "log_"))
]

metadata = [
    "label1", "label2", "label3", "label4",
    "label_full", "device_name",
    "timestamp_start", "episode_id"
]

# 1. Saldiri oturum adaylarini olustur.
attack["time"] = pd.to_datetime(
    attack["timestamp_start"],
    format="ISO8601",
    utc=True
)

times = (
    attack[["label4", "timestamp_start", "time"]]
    .drop_duplicates()
    .sort_values(["label4", "time"])
    .copy()
)

gaps = (
    times.groupby("label4")["time"]
    .diff()
    .dt.total_seconds()
)

new_episode = gaps.isna() | (gaps > THRESHOLD)

times["episode_num"] = new_episode.groupby(
    times["label4"]
).cumsum()

times["episode_id"] = (
    times["label4"]
    + "::"
    + times["episode_num"].astype(str)
)

attack = attack.merge(
    times[["label4", "timestamp_start", "episode_id"]],
    on=["label4", "timestamp_start"],
    validate="many_to_one"
)

# 2. Her sinifin son oturumunu test icin ayir.
episode_times = (
    attack.groupby(["label4", "episode_id"], as_index=False)
    ["time"].min()
    .sort_values(["label4", "time"])
)

episode_counts = (
    episode_times.groupby("label4")["episode_id"]
    .nunique()
)

last_episodes = episode_times.groupby(
    "label4"
).tail(1)

eligible = last_episodes[
    last_episodes["label4"].map(episode_counts) >= 2
]

test_episodes = set(eligible["episode_id"])

attack["split"] = "train"
attack.loc[
    attack["episode_id"].isin(test_episodes),
    "split"
] = "test"

# 3. Benign verisini zamansal olarak ayir.
benign_times = (
    benign[["timestamp_start"]]
    .drop_duplicates()
    .copy()
)

benign_times["time"] = pd.to_datetime(
    benign_times["timestamp_start"],
    format="ISO8601",
    utc=True
)

benign_times = benign_times.sort_values("time")
n = len(benign_times)

benign_times["split"] = [
    "train" if i < int(n * 0.70)
    else "gap" if i < int(n * 0.80)
    else "test"
    for i in range(n)
]

benign = benign.merge(
    benign_times[["timestamp_start", "split"]],
    on="timestamp_start",
    validate="many_to_one"
)

benign["episode_id"] = "benign::continuous"

# 4. Verileri birlestir.
df = pd.concat([attack, benign], ignore_index=True)

train = df[df["split"] == "train"]
test = df[df["split"] == "test"]

# Saldiri oturumlari iki tarafa dagilmis mi?
train_attack = set(
    train.loc[train["label1"] == "attack", "episode_id"]
)

test_attack = set(
    test.loc[test["label1"] == "attack", "episode_id"]
)

assert not (train_attack & test_attack), (
    "Attack episode leakage detected!"
)

# Yalnizca gerekli kolonlari kaydet.
columns = metadata + features

train[columns].to_csv(
    OUT / "train.csv", index=False
)

test[columns].to_csv(
    OUT / "test.csv", index=False
)

# 5. Sonuclari raporla.
print("\n=== FL DATA SPLIT ===")
print("Features:", len(features))
print("Training samples:", len(train))
print("Test samples:", len(test))
print("Excluded benign gap samples:",
      (df["split"] == "gap").sum())

print("\n=== FAMILY COVERAGE ===")

summary = pd.crosstab(
    df["label2"], df["split"]
)

print(summary.to_string())

print("\n=== ATTACK EPISODES ===")
print("Attack episode candidates:",
      attack["episode_id"].nunique())
print("Held-out attack episodes:",
      len(test_episodes))
print("Attack labels without episode-level test:",
      (episode_counts == 1).sum())

print("\n=== TEST CLASSES ===")
print(test["label4"].value_counts().to_string())

print("\nFiles saved to:", OUT)
