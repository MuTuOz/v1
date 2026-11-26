
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import onnxruntime as ort

from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

# 1. Egitilmis modeli yukle.
bundle = joblib.load(MODELS / "family_rf_5sec.joblib")

model = bundle["model"]
features = bundle["features"]

print("Feature sayisi:", len(features))
print("Siniflar:", model.classes_)

# 2. ONNX'e donustur.
onnx_model = convert_sklearn(
    model,
    initial_types=[
        ("features", FloatTensorType([None, len(features)]))
    ],
    options={id(model): {"zipmap": False}},
    target_opset=17
)

# 3. ONNX modelini kaydet.
output = MODELS / "family_rf_5sec.onnx"
output.write_bytes(onnx_model.SerializeToString())

print("\nONNX model kaydedildi:", output.name)
print("Boyut (MB):", round(output.stat().st_size / 1048576, 2))

# 4. Dönüşümün doğru olduğunu test et.
test = pd.read_csv(MODELS / "pi_test_samples_5sec.csv")

X = test[features]
X_onnx = X.to_numpy(dtype=np.float32)

sklearn_predictions = model.predict(X)

session = ort.InferenceSession(
    str(output),
    providers=["CPUExecutionProvider"]
)

input_name = session.get_inputs()[0].name

onnx_predictions = session.run(
    None,
    {input_name: X_onnx}
)[0]

# 5. Iki modelin tahminlerini karsilastir.
mismatches = np.sum(
    sklearn_predictions != onnx_predictions
)

print("\nTest ornegi:", len(test))
print("Farkli tahmin sayisi:", mismatches)

print("\nIlk 10 tahmin:")
for i in range(min(10, len(test))):
    print(
        f"Gercek: {test['label2'].iloc[i]:12s}"
        f" sklearn: {sklearn_predictions[i]:12s}"
        f" ONNX: {onnx_predictions[i]}"
    )
