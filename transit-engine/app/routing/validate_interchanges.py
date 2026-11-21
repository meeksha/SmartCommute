import pandas as pd

df = pd.read_csv("data/processed/bmtc_metro_interchanges.csv")

bins = [0, 200, 300, 400, 500, 600]
labels = ["0-200 m", "200-300 m", "300-400 m", "400-500 m", "500-600 m"]

df["distance_band"] = pd.cut(
    df["straight_line_distance_m"],
    bins=bins,
    labels=labels,
    include_lowest=True
)

print("\nINTERCHANGE DISTANCE DISTRIBUTION")
print(df["distance_band"].value_counts().sort_index())

print("\nSTATIONS WITH FEWEST NEARBY BMTC STOPS")
print(
    df.groupby("metro_station_name")
      .size()
      .sort_values()
      .head(10)
)

print("\nCLOSEST BMTC STOP PER METRO STATION")
print(
    df.loc[df.groupby("metro_station_id")["straight_line_distance_m"].idxmin()]
      [["metro_station_name", "bmtc_stop_name",
        "straight_line_distance_m", "estimated_walk_minutes"]]
      .to_string(index=False)
)
