import zipfile
import pandas as pd
from pathlib import Path

zip_path = Path("data/raw/bmtc_latest/bmtc_latest.zip")

legs = [
    ("49", "BMTC:2e01e1746789", "Wh3C8cd1", "Afqg410p"),
    ("258", "BMTC:982fd8b71127", "Afqg410p", "Hgy30gEx"),
    ("82-AR", "BMTC:aa640702b176", "Hgy30gEx", "G3StG9Rs"),
]

with zipfile.ZipFile(zip_path) as archive:
    with archive.open("fare_attributes.txt") as file:
        fares = pd.read_csv(file)

    print("BMTC FARE MATCHING TEST")
    print("=======================")

    for route_name, route_id, origin, destination in legs:
        print(f"\nRoute {route_name}: {origin} -> {destination}")

        matches = []

        with archive.open("fare_rules.txt") as file:
            for chunk in pd.read_csv(
                file,
                chunksize=200000,
                dtype=str
            ):
                matched = chunk[
                    (chunk["route_id"] == route_id)
                    & (chunk["origin_id"] == origin)
                    & (chunk["destination_id"] == destination)
                ]

                if not matched.empty:
                    matches.append(matched)

        if not matches:
            print("No exact fare rule found.")
            continue

        result = pd.concat(matches).drop_duplicates()
        result = result.merge(fares, on="fare_id", how="left")

        print(result.to_string(index=False))
