import pandas as pd
import numpy as np
import joblib

from pathlib import Path
from sklearn.model_selection import GroupShuffleSplit
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

BASE = Path("data/processed")
MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)

print("Loading BMTC prediction dataset...")
df = pd.read_csv(BASE / "bmtc_prediction_dataset.csv")

original_count = len(df)

# Remove implausible segments.
df = df[
    df["distance_km"].between(0.05, 5.0)
    & df["scheduled_duration_min"].between(0.5, 20.0)
].copy()

print("\nDATA CLEANING")
print("Original records:", original_count)
print("Retained records:", len(df))
print("Removed records:", original_count - len(df))
print("Removal percentage:", round(
    100 * (original_count - len(df)) / original_count, 2
))

# Encode time as cyclical features.
df["hour_sin"] = np.sin(2 * np.pi * df["departure_hour"] / 24)
df["hour_cos"] = np.cos(2 * np.pi * df["departure_hour"] / 24)
df["minute_sin"] = np.sin(2 * np.pi * df["departure_minute"] / 60)
df["minute_cos"] = np.cos(2 * np.pi * df["departure_minute"] / 60)

features = [
    "distance_km",
    "trips_per_hour",
    "origin_lat",
    "origin_lon",
    "destination_lat",
    "destination_lon",
    "hour_sin",
    "hour_cos",
    "minute_sin",
    "minute_cos"
]

X = df[features].astype(float)
y = df["scheduled_duration_min"].astype(float)
groups = df["trip_id"]

# Split by trip, not by individual stop connection.
splitter = GroupShuffleSplit(
    n_splits=1,
    test_size=0.20,
    random_state=42
)

train_idx, test_idx = next(splitter.split(X, y, groups))

X_train = X.iloc[train_idx]
X_test = X.iloc[test_idx]
y_train = y.iloc[train_idx]
y_test = y.iloc[test_idx]

train_df = df.iloc[train_idx]
test_df = df.iloc[test_idx]

print("\nTRAINING")
print("Training records:", len(X_train))
print("Testing records:", len(X_test))
print("Training trips:", train_df["trip_id"].nunique())
print("Testing trips:", test_df["trip_id"].nunique())

# Baseline: median scheduled duration for the same stop pair.
pair_medians = (
    train_df.groupby(["stop_id", "next_stop_id"])
    ["scheduled_duration_min"]
    .median()
)

global_median = y_train.median()

baseline_predictions = [
    pair_medians.get((row.stop_id, row.next_stop_id), global_median)
    for row in test_df[["stop_id", "next_stop_id"]].itertuples(index=False)
]

# Train the ML model.
model = HistGradientBoostingRegressor(
    max_iter=150,
    learning_rate=0.08,
    max_leaf_nodes=31,
    l2_regularization=1.0,
    random_state=42
)

model.fit(X_train, y_train)

predictions = model.predict(X_test)

def report_metrics(name, actual, predicted):
    mae = mean_absolute_error(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))
    r2 = r2_score(actual, predicted)

    print(f"\n{name}")
    print("MAE:", round(mae, 3), "minutes")
    print("RMSE:", round(rmse, 3), "minutes")
    print("R2:", round(r2, 4))

    return mae

baseline_mae = report_metrics(
    "BASELINE: STOP-PAIR MEDIAN",
    y_test,
    baseline_predictions
)

model_mae = report_metrics(
    "HIST GRADIENT BOOSTING MODEL",
    y_test,
    predictions
)

print("\nMODEL COMPARISON")
if model_mae < baseline_mae:
    print("ML model performs better than the baseline.")
else:
    print("Baseline performs better. Do not claim ML improvement.")

# Save model and feature information.
joblib.dump(
    {
        "model": model,
        "features": features,
        "target": "scheduled_duration_min",
        "training_note": (
            "Predicts historical scheduled segment duration, "
            "not actual traffic-dependent bus travel time."
        )
    },
    MODEL_DIR / "bmtc_duration_model.joblib"
)

print("\nSaved model:", MODEL_DIR / "bmtc_duration_model.joblib")
