
import pandas as pd
import torch
from torch import nn

from seniorfl.task import ROOT, FEATURES, prepare

DATA_DIR = ROOT / "data" / "validation_v1"

# Class labels come ONLY from the training dataset.
metadata = pd.read_csv(
    DATA_DIR / "train.csv",
    usecols=["label2", "label4"]
)

assert metadata[["label2", "label4"]].notna().all().all()

# Each subtype must belong to exactly one family.
family_counts = metadata.groupby("label4")["label2"].nunique()
assert family_counts.max() == 1

FAMILY_OF = (
    metadata.drop_duplicates("label4")
    .set_index("label4")["label2"]
    .to_dict()
)

CLASSES = ["benign"] + sorted(
    label for label in metadata["label4"].unique()
    if label != "benign"
)

CLASS_TO_ID = {
    label: i for i, label in enumerate(CLASSES)
}

assert len(CLASSES) == 84
assert FAMILY_OF["benign"] == "benign"
assert len(FEATURES) == 71


class SubtypeMLP(nn.Module):
    def __init__(self):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(71, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 84),
        )

    def forward(self, x):
        return self.net(x)


def make_labels(df):
    mapped = df["label4"].map(CLASS_TO_ID)

    if mapped.isna().any():
        unknown = df.loc[
            mapped.isna(), "label4"
        ].unique()
        raise ValueError(
            f"Unknown subtype labels: {unknown}"
        )

    return torch.tensor(
        mapped.to_numpy(),
        dtype=torch.long
    )
