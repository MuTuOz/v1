
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/all_attack_benign_samples"

# 1. Attack ve benign verilerini oku.
attack = pd.read_csv(
    DATA / "attack_data/attack_samples_5sec.csv"
)

benign = pd.read_csv(
    DATA / "benign_data/benign_samples_5sec.csv"
)

df = pd.concat([attack, benign], ignore_index=True)

# 2. Yalnızca sayısal feature'ları seç.
features = attack.select_dtypes(include="number").columns.tolist()

print("Feature sayısı:", len(features))

# 3. Aynı senaryo ve zamandaki cihaz kayıtlarını
# aynı split içerisinde tut.
windows = (
    df[["label_full", "timestamp_start"]]
    .drop_duplicates()
    .sort_values(["label_full", "timestamp_start"])
    .copy()
)

windows["rank"] = windows.groupby("label_full").cumcount()

windows["count"] = (
    windows.groupby("label_full")["timestamp_start"]
    .transform("size")
)

# İlk %70 train, sonraki %10 boşluk,
# son %20 test.
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

# 0 = Benign, 1 = Attack
y_train = (train["label1"] == "attack").astype(int)
y_test = (test["label1"] == "attack").astype(int)

print("Training samples:", len(train))
print("Test samples:", len(test))

# 4. İlk modelimizi eğit.
model = RandomForestClassifier(
    n_estimators=80,
    max_depth=12,
    class_weight="balanced_subsample",
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

# 5. Daha önce eğitimde kullanılmayan
# zaman pencerelerinde test et.
predictions = model.predict(X_test)

print("\n=== CLASSIFICATION REPORT ===")

print(
    classification_report(
        y_test,
        predictions,
        target_names=["Benign", "Attack"],
        zero_division=0
    )
)

print("\n=== CONFUSION MATRIX ===")
print(confusion_matrix(y_test, predictions))

# 6. Modeli ve feature sırasını birlikte kaydet.
output = ROOT / "models"
output.mkdir(exist_ok=True)

joblib.dump(
    {"model": model, "features": features},
    output / "binary_rf_5sec.joblib"
)

print("\nModel kaydedildi.")
