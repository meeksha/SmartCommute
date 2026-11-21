import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from app.routing.bmtc_duration_predictor import (
    predict_segment_duration
)

print("Loading test records...")

df = pd.read_csv("data/processed/bmtc_prediction_dataset.csv")

df = df[
    df["distance_km"].between(0.05, 5.0)
    & df["scheduled_duration_min"].between(0.5, 20.0)
].copy()

splitter = GroupShuffleSplit(
    n_splits=1,
    test_size=0.20,
    random_state=42
)

train_idx, test_idx = next(
    splitter.split(
        df,
        df["scheduled_duration_min"],
        groups=df["trip_id"]
    )
)

train = df.iloc[train_idx]
test = df.iloc[test_idx]

known_pairs = set(zip(train["stop_id"], train["next_stop_id"]))

known = train.iloc[0]

unseen = test[
    ~test.apply(
        lambda row: (
            row["stop_id"], row["next_stop_id"]
        ) in known_pairs,
        axis=1
    )
]

if unseen.empty:
    raise RuntimeError("No unseen stop pair found.")

unseen = unseen.iloc[0]

def run_test(label, row):
    print(f"\n--- {label} ---")

    result = predict_segment_duration(
        route_id=row["route_id"],
        stop_id=row["stop_id"],
        next_stop_id=row["next_stop_id"],
        departure_time=(
            f'{int(row["departure_hour"]):02d}:'
            f'{int(row["departure_minute"]):02d}'
        )
    )

    print("Route:", row["route_short_name"])
    print("From stop ID:", row["stop_id"])
    print("To stop ID:", row["next_stop_id"])
    print("Actual scheduled duration:",
          round(row["scheduled_duration_min"], 2), "minutes")
    print("Prediction result:", result)

run_test("KNOWN STOP PAIR", known)
run_test("UNSEEN STOP PAIR", unseen)

print("\nBoth prediction tests completed.")
