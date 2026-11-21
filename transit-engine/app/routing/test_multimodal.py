import pandas as pd
from app.routing.planner import plan_journey

path = "data/processed/metro/standard/stops.csv"
df = pd.read_csv(path)

df["location_type"] = pd.to_numeric(
    df["location_type"], errors="coerce"
)

stations = df[df["location_type"] == 1]
entrances = df[df["location_type"] == 2]

def get_entrance(search_name):
    matches = stations[
        stations["stop_name"].str.contains(
            search_name, case=False, na=False
        )
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Station lookup for {search_name} returned "
            f"{len(matches)} matches: {matches['stop_name'].tolist()}"
        )

    station = matches.iloc[0]

    entrance = entrances[
        entrances["parent_station"] == station["stop_id"]
    ]

    if entrance.empty:
        raise ValueError(f"No entrance found for {search_name}")

    return entrance.iloc[0]

origin = get_entrance("Attiguppe")
destination = get_entrance("Yeshwantpur")

print("ORIGIN:", origin["stop_name"])
print("DESTINATION:", destination["stop_name"])

result = plan_journey(
    origin_lat=origin["stop_lat"],
    origin_lon=origin["stop_lon"],
    destination_lat=destination["stop_lat"],
    destination_lon=destination["stop_lon"],
    travel_date="2026-11-19",
    departure_time="08:00"
)

print("\nMULTIMODAL JOURNEY TEST")
print("=======================")

for key, value in result.items():
    print(f"\n{key}: {value}")
