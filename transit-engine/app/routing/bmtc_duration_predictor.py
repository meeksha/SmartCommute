import joblib
import numpy as np
import pandas as pd

from pathlib import Path
from functools import lru_cache

ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "bmtc_hybrid_predictor.joblib"
)


@lru_cache(maxsize=1)
def load_predictor():
    return joblib.load(ARTIFACT_PATH)


def parse_departure_time(value):
    parts = str(value).split(":")
    hour, minute = int(parts[0]), int(parts[1])

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Invalid departure time")

    return hour, minute


def haversine_km(a, b):
    lat1, lon1 = np.radians(a)
    lat2, lon2 = np.radians(b)

    value = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2)
        * np.sin((lon2 - lon1) / 2) ** 2
    )

    return float(6371 * 2 * np.arcsin(np.sqrt(value)))


def predict_segment_duration(
    route_id, stop_id, next_stop_id, departure_time
):
    data = load_predictor()

    route_id = str(route_id)
    stop_id = str(stop_id)
    next_stop_id = str(next_stop_id)

    hour, minute = parse_departure_time(departure_time)

    pair_key = (stop_id, next_stop_id)

    if pair_key in data["pair_medians"]:
        return {
            "status": "success",
            "predicted_duration_min": round(
                float(data["pair_medians"][pair_key]), 2
            ),
            "method": "historical_stop_pair_median",
            "confidence_note": "Historical scheduled stop-pair median.",
            "is_live": False
        }

    coordinates = data["stop_coordinates"]

    if stop_id not in coordinates or next_stop_id not in coordinates:
        return {
            "status": "unavailable",
            "reason": "Stop coordinates are unavailable."
        }

    distance = haversine_km(
        coordinates[stop_id], coordinates[next_stop_id]
    )

    if not 0.05 <= distance <= 5.0:
        return {
            "status": "unavailable",
            "reason": "Segment is outside the validated distance range."
        }

    frequency_key = (route_id, stop_id, next_stop_id, hour)
    trips_per_hour = data["frequency_lookup"].get(frequency_key, 1)

    values = {
        "distance_km": distance,
        "trips_per_hour": trips_per_hour,
        "origin_lat": coordinates[stop_id][0],
        "origin_lon": coordinates[stop_id][1],
        "destination_lat": coordinates[next_stop_id][0],
        "destination_lon": coordinates[next_stop_id][1],
        "hour_sin": np.sin(2 * np.pi * hour / 24),
        "hour_cos": np.cos(2 * np.pi * hour / 24),
        "minute_sin": np.sin(2 * np.pi * minute / 60),
        "minute_cos": np.cos(2 * np.pi * minute / 60)
    }

    X = pd.DataFrame(
        [[values[name] for name in data["features"]]],
        columns=data["features"]
    )

    prediction = float(data["model"].predict(X)[0])
    prediction = float(np.clip(prediction, 0.5, 20.0))

    return {
        "status": "success",
        "predicted_duration_min": round(prediction, 2),
        "method": "gradient_boosting_fallback",
        "distance_km": round(distance, 3),
        "confidence_note": "ML estimate for an unseen stop pair; limited validation.",
        "is_live": False
    }


if __name__ == "__main__":
    print("BMTC hybrid predictor loaded.")
    print("Artifact:", ARTIFACT_PATH)
    print("Live traffic prediction: not supported.")
