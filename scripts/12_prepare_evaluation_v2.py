
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/splits_v1"
OUT = ROOT / "data/splits_v2"
OUT.mkdir(parents=True, exist_ok=True)

train = pd.read_csv(SOURCE / "train.csv")
test = pd.read_csv(SOURCE / "test.csv")

# Web disindaki train verilerini koru.
other_train = train[train["label2"] != "web"].copy()
web = train[train["label2"] == "web"].copy()

# Her web alt turundeki zaman pencerelerini sirala.
windows = (
    web[["label4", "timestamp_start"]]
    .drop_duplicates()
    .sort_values(["label4", "timestamp_start"])
    .copy()
)

windows["rank"] = windows.groupby("label4").cumcount()
windows["count"] = windows.groupby(
    "label4"
)["timestamp_start"].transform("size")

# Ilk %70 egitim, sonraki %10 bosluk,
# son %20 tanilama testi.
windows["web_split"] = np.where(
    windows["rank"] < np.floor(windows["count"] * 0.70),
    "train",
    np.where(
        windows["rank"] >= np.ceil(windows["count"] * 0.80),
        "test",
        "gap"
    )
)

web = web.merge(
    windows[["label4", "timestamp_start", "web_split"]],
    on=["label4", "timestamp_start"],
    validate="many_to_one"
)

# Ana egitim setini yeniden olustur.
web_train = web.loc[
    web["web_split"] == "train", train.columns
]

new_train = pd.concat(
    [other_train, web_train],
    ignore_index=True
)

# Sadece web kayitlari: ayri, daha zayif test.
web_test = web.loc[
    web["web_split"] == "test", train.columns
].copy()

# Ana episode testine dokunmuyoruz.
episode_test = test.copy()

assert set(new_train.columns) == set(episode_test.columns)
assert len(web_test) > 0
assert (web_test["label2"] == "web").all()

new_train.to_csv(OUT / "train.csv", index=False)
episode_test.to_csv(
    OUT / "test_episode.csv", index=False
)
web_test.to_csv(
    OUT / "test_web_diagnostic.csv", index=False
)

print("\n=== EVALUATION V2 ===")
print("Training samples:", len(new_train))
print("Episode test:", len(episode_test))
print("Web diagnostic test:", len(web_test))
print("Web gap excluded:",
      (web["web_split"] == "gap").sum())

print("\n=== TRAIN FAMILY COVERAGE ===")
print(new_train["label2"].value_counts().to_string())

print("\n=== EPISODE TEST FAMILY COVERAGE ===")
print(episode_test["label2"].value_counts().to_string())

print("\n=== WEB DIAGNOSTIC SUBTYPES ===")
print(web_test["label4"].value_counts().to_string())

print("\nSaved to:", OUT)
