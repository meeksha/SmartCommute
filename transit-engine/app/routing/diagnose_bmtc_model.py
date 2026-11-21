import pandas as pd
import numpy as np
import joblib

from pathlib import Path
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import mean_absolute_error

BASE = Path("data/processed")

print("Loading dataset...", flush=True)

df = pd.read_csv(BASE / "bmtc_prediction_dataset.csv")

df = df[
    df["distance_km"].between(0.05, 5.0)
    & df["scheduled_duration_min"].between(0.5, 20.0)
].copy()

df["hour_sin"] = np.sin(2 * np.pi * df["departure_hour"] / 24)
df["hour_cos"] = np.cos(2 * np.pi * df["departure_hour"] / 24)
df["minute_sin"] = np.sin(2 * np.pi * df["departure_minute"] / 60)
df["minute_cos"] = np.cos(2 * np.pi * df["departure_minute"] / 60)

features = [
    "distance_km", "trips_per_hour",
    "origin_lat", "origin_lon",
    "destination_lat", "destination_lon",
    "hour_sin", "hour_cos",
    "minute_sin", "minute_cos"
]

X = df[features]
y = df["scheduled_duration_min"]

print("Creating trip-based split...", flush=True)

splitter = GroupShuffleSplit(
    n_splits=1, test_size=0.2, random_state=42
)

train_idx, test_idx = next(
    splitter.split(X, y, groups=df["trip_id"])
)

train = df.iloc[train_idx]
test = df.iloc[test_idx]

print("Loading trained model...", flush=True)

bundle = joblib.load("models/bmtc_duration_model.joblib")
model = bundle["model"]

print("Predicting test records...", flush=True)
predictions = model.predict(test[features])

print("Calculating baseline...", flush=True)

pair_medians = train.groupby(
    ["stop_id", "next_stop_id"]
)["scheduled_duration_min"].median()

global_median = train["scheduled_duration_min"].median()

test_pairs = pd.MultiIndex.from_frame(
    test[["stop_id", "next_stop_id"]]
)

baseline = pair_medians.reindex(test_pairs).fillna(global_median).to_numpy()

train_pairs = pd.MultiIndex.from_frame(
    train[["stop_id", "next_stop_id"]]
).unique()

seen_mask = test_pairs.isin(train_pairs)

def report(label, mask):
    if mask.sum() == 0:
        print(f"\n{label}: no records")
        return

    actual = test["scheduled_duration_min"].to_numpy()[mask]

    print(f"\n{label}")
    print("Records:", int(mask.sum()))
    print("ML MAE:", round(
        mean_absolute_error(actual, predictions[mask]), 3
    ))
    print("Baseline MAE:", round(
        mean_absolute_error(actual, baseline[mask]), 3
    ))

report("STOP PAIRS SEEN IN TRAINING", seen_mask)
report("STOP PAIRS NOT SEEN IN TRAINING", ~seen_mask)

print("\nSeen-pair percentage:", round(seen_mask.mean() * 100, 2))
print("Unseen-pair percentage:", round((~seen_mask).mean() * 100, 2))
