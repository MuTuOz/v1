
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/splits_v2/train.csv"
OUT = ROOT / "data/fl_clients_v1"
OUT.mkdir(parents=True, exist_ok=True)

SEED = 42
rng = np.random.default_rng(SEED)

train = pd.read_csv(SOURCE)
train["_row_id"] = np.arange(len(train))

# Hangi aile hangi client'larda bulunabilir?
family_clients = {
    "dos": [1, 5],
    "ddos": [1, 4],
    "recon": [2, 4],
    "mitm": [2],
    "web": [3, 5],
    "bruteforce": [3],
    "malware": [4, 5],
}

attack = train[train["label2"] != "benign"].copy()
benign = train[train["label2"] == "benign"].copy()

# 1. Saldiri oturumlarini client'lara dagit.
assignments = {}

for family, allowed_clients in family_clients.items():

    family_data = attack[attack["label2"] == family]

    episodes = (
        family_data.groupby("episode_id")
        .size()
        .sort_values(ascending=False)
    )

    sizes = {c: 0 for c in allowed_clients}

    for episode_id, count in episodes.items():

        chosen = min(
            allowed_clients,
            key=lambda c: (sizes[c], c)
        )

        assignments[episode_id] = chosen
        sizes[chosen] += count

attack["client_id"] = attack["episode_id"].map(assignments)

assert attack["client_id"].notna().all()

# 2. Benign zaman pencerelerini dagit.
time_counts = benign.groupby("timestamp_start").size()

benign_sizes = {c: 0 for c in range(1, 6)}
benign_assignments = {}

shuffled_times = rng.permutation(time_counts.index.to_numpy())

for timestamp in shuffled_times:

    chosen = min(
        benign_sizes,
        key=lambda c: (benign_sizes[c], c)
    )

    benign_assignments[timestamp] = chosen
    benign_sizes[chosen] += int(time_counts[timestamp])

benign["client_id"] = benign["timestamp_start"].map(
    benign_assignments
)

# 3. Client verilerini birlestir.
assigned = pd.concat(
    [attack, benign],
    ignore_index=True
)

assigned["client_id"] = assigned["client_id"].astype(int)

# 4. Tum kayitlar tam olarak bir client'ta olmali.
assert len(assigned) == len(train)
assert assigned["_row_id"].is_unique
assert assigned["_row_id"].nunique() == len(train)

# Ayni saldiri oturumu iki client'a bolunmesin.
assert (
    attack.groupby("episode_id")["client_id"]
    .nunique().max() == 1
)

# Ayni benign zaman penceresi bolunmesin.
assert (
    benign.groupby("timestamp_start")["client_id"]
    .nunique().max() == 1
)

# 5. Client CSV'lerini kaydet.
for client_id in range(1, 6):

    client_data = assigned[
        assigned["client_id"] == client_id
    ].drop(columns=["client_id", "_row_id"])

    client_data.to_csv(
        OUT / f"client_{client_id}_train.csv",
        index=False
    )

# 6. Dagilimi raporla.
classes = [
    "benign", "bruteforce", "ddos", "dos",
    "malware", "mitm", "recon", "web"
]

distribution = pd.crosstab(
    assigned["client_id"],
    assigned["label2"]
).reindex(
    index=range(1, 6),
    columns=classes,
    fill_value=0
)

distribution["TOTAL"] = distribution.sum(axis=1)

print("\n=== NON-IID CLIENT DISTRIBUTION ===")
print(distribution.to_string())

distribution.to_csv(
    OUT / "client_distribution.csv"
)

print("\n=== LOCALLY UNSEEN ATTACK FAMILIES ===")

all_families = set(attack["label2"].unique())

for client_id in range(1, 6):

    local = set(
        attack.loc[
            attack["client_id"] == client_id,
            "label2"
        ]
    )

    unseen = sorted(all_families - local)

    print(f"Client {client_id}: {', '.join(unseen)}")

print("\nTotal distributed:", len(assigned))
print("Files saved to:", OUT)
