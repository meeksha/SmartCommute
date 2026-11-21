import pandas as pd
import numpy as np
import joblib

from sklearn.model_selection import GroupShuffleSplit
from pathlib import Path

BASE = Path("data/processed")
MODEL_PATH = Path("models/bmtc_duration_model.joblib")
ARTIFACT_PATH = Path("models/bmtc_hybrid_predictor.joblib")

print("Loading BMTC dataset...")

df = pd.read_csv(BASE / "bmtc_prediction_dataset.csv")

df = df[
    df["distance_km"].between(0.05, 5.0)
    & df["scheduled_duration_min"].between(0.5, 20.0)
].copy()

splitter = GroupShuffleSplit(
    n_splits=1,
    test_size=0.20,
    random_state=42
)

train_idx, _ = next(
    splitter.split(
        df,
        df["scheduled_duration_min"],
        groups=df["trip_id"]
    )
)

train = df.iloc[train_idx].copy()

print("Creating historical lookups...")

pair_medians = (
    train.groupby(["stop_id", "next_stop_id"])
    ["scheduled_duration_min"]
    .median()
    .to_dict()
)

frequency_lookup = (
    train.groupby(
        ["route_id", "stop_id", "next_stop_id", "departure_hour"]
    )["trip_id"]
    .nunique()
    .to_dict()
)

stops = pd.read_csv(BASE / "bmtc_stops.csv")

stop_coordinates = {
    str(row.stop_id): (float(row.stop_lat), float(row.stop_lon))
    for row in stops.itertuples(index=False)
}

model_bundle = joblib.load(MODEL_PATH)

artifact = {
    "model": model_bundle["model"],
    "features": model_bundle["features"],
    "pair_medians": pair_medians,
    "frequency_lookup": frequency_lookup,
    "stop_coordinates": stop_coordinates,
    "global_median": float(
        train["scheduled_duration_min"].median()
    ),
    "version": 2,
    "note": (
        "Historical scheduled BMTC segment duration estimates. "
        "Not live traffic or actual observed bus travel times."
    )
}

joblib.dump(artifact, ARTIFACT_PATH)

print("\nUPDATED HYBRID PREDICTOR")
print("Stop-pair medians:", len(pair_medians))
print("Frequency records:", len(frequency_lookup))
print("Stop coordinates:", len(stop_coordinates))
print("Saved:", ARTIFACT_PATH)
