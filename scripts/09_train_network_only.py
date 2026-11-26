
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/all_attack_benign_samples"
OUTPUT = ROOT / "models"
OUTPUT.mkdir(exist_ok=True)

# 1. Verileri yukle
attack = pd.read_csv(
    DATA / "attack_data/attack_samples_5sec.csv"
)
benign = pd.read_csv(
    DATA / "benign_data/benign_samples_5sec.csv"
)

df = pd.concat([attack, benign], ignore_index=True)

# 2. Modelin gorebilecegi sayisal feature'lar
features = [
    col for col in attack.select_dtypes(include="number").columns
    if col.startswith("network_")
]

# 3. Onceki deneyle ayni zaman tabanli ayirim
windows = (
    df[["label_full", "timestamp_start"]]
    .drop_duplicates()
    .sort_values(["label_full", "timestamp_start"])
    .copy()
)

windows["rank"] = windows.groupby(
    "label_full"
).cumcount()

windows["count"] = windows.groupby(
    "label_full"
)["timestamp_start"].transform("size")

windows["split"] = np.where(
    windows["rank"] < np.floor(windows["count"] * 0.70),
    "train",
    np.where(
        windows["rank"] >= np.ceil(windows["count"] * 0.80),
        "test",
        "gap"
    )
)

df = df.merge(
    windows[["label_full", "timestamp_start", "split"]],
    on=["label_full", "timestamp_start"],
    validate="many_to_one"
)

train = df[df["split"] == "train"]
test = df[df["split"] == "test"]

X_train = train[features]
X_test = test[features]

# Fark: artik binary label1 yerine family label2!
y_train = train["label2"]
y_test = test["label2"]

print("Feature sayisi:", len(features))
print("Training:", len(train))
print("Test:", len(test))

# 4. Model
model = RandomForestClassifier(
    n_estimators=80,
    max_depth=12,
    class_weight="balanced_subsample",
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

# 5. Test
pred = model.predict(X_test)

print("\n=== 8-CLASS RESULTS ===")
print(classification_report(y_test, pred, zero_division=0))

print("\nSinif sirasi:")
print(model.classes_)

print("\nConfusion Matrix:")
print(confusion_matrix(
    y_test,
    pred,
    labels=model.classes_
))

# 6. Model ve feature listesini kaydet
joblib.dump(
    {"model": model, "features": features},
    OUTPUT / "family_rf_network_only_5sec.joblib"
)

# 7. Pi'ye goturmek icin kucuk test seti
batch = test.groupby(
    "label2",
    group_keys=False
).sample(n=20, random_state=42)

batch[features + ["label2"]].to_csv(
    OUTPUT / "pi_test_samples_5sec_network_only.csv",
    index=False
)

print("\nModel ve Pi test dosyasi kaydedildi.")
