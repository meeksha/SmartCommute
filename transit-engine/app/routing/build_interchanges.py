from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path("data/processed")
OUTPUT = BASE / "bmtc_metro_interchanges.csv"
MAX_DISTANCE_M = 600
WALKING_SPEED_MPS = 1.2


def haversine_matrix(bus_lat, bus_lon, metro_lat, metro_lon):
    lat1 = np.radians(bus_lat[:, None])
    lon1 = np.radians(bus_lon[:, None])
    lat2 = np.radians(metro_lat[None, :])
    lon2 = np.radians(metro_lon[None, :])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    )
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def main():
    bus = pd.read_csv(BASE / "bmtc_stops.csv", dtype=str)
    metro = pd.read_csv(
        BASE / "metro" / "standard" / "stops.csv", dtype=str
    )

    for col in ["stop_lat", "stop_lon"]:
        bus[col] = pd.to_numeric(bus[col], errors="coerce")
        metro[col] = pd.to_numeric(metro[col], errors="coerce")

    bus = bus.dropna(subset=["stop_lat", "stop_lon"]).copy()

    # Use station-level Metro records, not individual platforms or entrances.
    metro = metro[
        (metro["location_type"] == "1")
    ].dropna(subset=["stop_lat", "stop_lon"]).copy()

    distances = haversine_matrix(
        bus["stop_lat"].to_numpy(),
        bus["stop_lon"].to_numpy(),
        metro["stop_lat"].to_numpy(),
        metro["stop_lon"].to_numpy()
    )

    bus_indices, metro_indices = np.where(
        distances <= MAX_DISTANCE_M
    )

    result = pd.DataFrame({
        "bmtc_stop_id": bus.iloc[bus_indices]["stop_id"].to_numpy(),
        "bmtc_stop_name": bus.iloc[bus_indices]["stop_name"].to_numpy(),
        "metro_station_id": metro.iloc[metro_indices]["stop_id"].to_numpy(),
        "metro_station_name": metro.iloc[metro_indices]["stop_name"].to_numpy(),
        "straight_line_distance_m": distances[
            bus_indices, metro_indices
        ].round(1)
    })

    result["estimated_walk_minutes"] = (
        result["straight_line_distance_m"] / WALKING_SPEED_MPS / 60
    ).round(1)

    result = result.sort_values(
        ["metro_station_name", "straight_line_distance_m"]
    )

    result.to_csv(OUTPUT, index=False)

    print("\nBMTC-METRO INTERCHANGE RESULTS")
    print("--------------------------------")
    print("BMTC stops checked:", len(bus))
    print("Metro stations checked:", len(metro))
    print("Interchange candidates:", len(result))
    print("Metro stations with nearby BMTC stops:",
          result["metro_station_id"].nunique())
    print("Maximum straight-line distance:", MAX_DISTANCE_M, "m")
    print("Saved:", OUTPUT)

    print("\nClosest interchange candidates:")
    print(result.head(15).to_string(index=False))

    print(
        "\nNOTE: Distances are straight-line estimates, "
        "not actual pedestrian route distances."
    )


if __name__ == "__main__":
    main()
