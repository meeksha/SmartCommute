from pathlib import Path
from functools import lru_cache

import numpy as np
import pandas as pd

BASE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "processed"
    / "bmtc_latest"
)

STOPS_FILE = BASE / "bmtc_stops.csv"


@lru_cache(maxsize=1)
def load_bmtc_stops():
    if not STOPS_FILE.exists():
        raise FileNotFoundError(STOPS_FILE)

    stops = pd.read_csv(STOPS_FILE)

    stops["stop_lat"] = pd.to_numeric(
        stops["stop_lat"], errors="coerce"
    )
    stops["stop_lon"] = pd.to_numeric(
        stops["stop_lon"], errors="coerce"
    )

    stops = stops.dropna(
        subset=["stop_id", "stop_name", "stop_lat", "stop_lon"]
    ).copy()

    return stops.reset_index(drop=True)


def calculate_distances_m(lat, lon, stop_lats, stop_lons):
    earth_radius = 6371000

    lat1 = np.radians(float(lat))
    lon1 = np.radians(float(lon))
    lat2 = np.radians(stop_lats)
    lon2 = np.radians(stop_lons)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    a = np.clip(a, 0, 1)

    return 2 * earth_radius * np.arcsin(np.sqrt(a))


def find_nearby_bmtc_stops(
    latitude,
    longitude,
    radius_m=1000,
    limit=5
):
    latitude = float(latitude)
    longitude = float(longitude)

    if not -90 <= latitude <= 90:
        raise ValueError("Invalid latitude.")

    if not -180 <= longitude <= 180:
        raise ValueError("Invalid longitude.")

    if radius_m <= 0 or limit < 1:
        raise ValueError("Invalid radius or result limit.")

    stops = load_bmtc_stops()

    distances = calculate_distances_m(
        latitude,
        longitude,
        stops["stop_lat"].to_numpy(),
        stops["stop_lon"].to_numpy()
    )

    nearest_indices = np.argsort(distances)[:limit]
    matches = []

    for index in nearest_indices:
        distance = float(distances[index])

        if distance > radius_m:
            continue

        row = stops.iloc[index]

        matches.append({
            "stop_id": str(row["stop_id"]),
            "stop_name": str(row["stop_name"]),
            "latitude": float(row["stop_lat"]),
            "longitude": float(row["stop_lon"]),
            "straight_line_distance_m": round(distance, 1)
        })

    nearest_index = int(np.argmin(distances))
    nearest_row = stops.iloc[nearest_index]

    if not matches:
        return {
            "status": "no_nearby_stop",
            "message": f"No BMTC stop within {radius_m} metres.",
            "nearest_candidate": {
                "stop_id": str(nearest_row["stop_id"]),
                "stop_name": str(nearest_row["stop_name"]),
                "distance_m": round(float(distances[nearest_index]), 1)
            },
            "matches": []
        }

    return {
        "status": "success",
        "search_radius_m": radius_m,
        "matches_found": len(matches),
        "matches": matches,
        "distance_type": "straight_line",
        "feed_version": "2026-11-09"
    }


if __name__ == "__main__":
    stops = load_bmtc_stops()

    print("NEW BMTC GPS STOP MATCHER")
    print("=========================")
    print("Feed: 2026-2027")
    print("Available stops:", len(stops))

    tests = [
        ("Chamarajapet", 12.9585, 77.5635),
        ("Orion Mall area", 13.0105, 77.5540)
    ]

    for name, lat, lon in tests:
        result = find_nearby_bmtc_stops(lat, lon)

        print(f"\n{name}: {result['status']}")

        for match in result["matches"]:
            print(
                match["stop_name"],
                "|",
                match["stop_id"],
                "|",
                match["straight_line_distance_m"],
                "m"
            )
