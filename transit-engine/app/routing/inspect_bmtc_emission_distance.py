import zipfile
import pandas as pd
from pathlib import Path

zip_path = Path("data/raw/bmtc_latest/bmtc_latest.zip")

legs = {
    "49": ("gnsshtS5:PvJY5A3f", "Wh3C8cd1", "Afqg410p"),
    "258": ("EsN89EuY:xqFCUH8A", "Afqg410p", "Hgy30gEx"),
    "82-AR": ("HyxQsVK1:JVvOyeXm", "Hgy30gEx", "G3StG9Rs"),
}

with zipfile.ZipFile(zip_path) as archive:
    with archive.open("stop_times.txt") as file:
        header = pd.read_csv(file, nrows=0).columns.tolist()

    print("GTFS columns:", header)

    if "shape_dist_traveled" not in header:
        raise SystemExit("No shape_dist_traveled field in this feed.")

    found = []

    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("stop_times.txt") as file:
            for chunk in pd.read_csv(
                file,
                chunksize=300000,
                dtype={"trip_id": str, "stop_id": str}
            ):
                for route, (trip, origin, destination) in legs.items():
                    rows = chunk[
                        (chunk["trip_id"] == trip)
                        & (chunk["stop_id"].isin([origin, destination]))
                    ]

                    for _, row in rows.iterrows():
                        found.append({
                            "route": route,
                            "trip_id": trip,
                            "stop_id": row["stop_id"],
                            "shape_dist_traveled": row["shape_dist_traveled"]
                        })

    result = pd.DataFrame(found)

    print("\nBMTC LEG DISTANCES")
    print(result.to_string(index=False))

    for route, (trip, origin, destination) in legs.items():
        rows = result[result["route"] == route]

        start = rows[rows["stop_id"] == origin]
        end = rows[rows["stop_id"] == destination]

        if start.empty or end.empty:
            print(f"\nRoute {route}: distance unavailable")
            continue

        distance_m = (
            float(end.iloc[0]["shape_dist_traveled"])
            - float(start.iloc[0]["shape_dist_traveled"])
        )
        distance_km = distance_m / 1000.0

        print(f"\nRoute {route}: {distance_km:.3f} km")
