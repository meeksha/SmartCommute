
import pandas as pd
import osmnx as ox

GRAPH_FILE = "data/raw/walking/bengaluru_walking_network.graphml"

bmtc_file = "data/processed/walking/bmtc_walking_node_mapping.csv"
metro_file = "data/processed/walking/metro_walking_node_mapping.csv"

print("Loading walking graph...")
G = ox.load_graphml(GRAPH_FILE)

nodes, edges = ox.graph_to_gdfs(G)

min_lon = nodes.geometry.x.min()
max_lon = nodes.geometry.x.max()
min_lat = nodes.geometry.y.min()
max_lat = nodes.geometry.y.max()


def add_boundary_status(df):
    df = df.copy()

    df["inside_rectangle"] = (
        (df["stop_lat"] >= min_lat) &
        (df["stop_lat"] <= max_lat) &
        (df["stop_lon"] >= min_lon) &
        (df["stop_lon"] <= max_lon)
    )

    return df


# --------------------------------------------------
# BMTC: stops inside rectangle but over 250 m away
# --------------------------------------------------

bmtc = pd.read_csv(bmtc_file)
bmtc = add_boundary_status(bmtc)

bmtc_gaps = bmtc[
    bmtc["inside_rectangle"] &
    (bmtc["nearest_node_distance_m"] > 250)
].copy()

bmtc_gaps = bmtc_gaps.sort_values(
    "nearest_node_distance_m",
    ascending=False
)

print("\n" + "=" * 65)
print("BMTC: INSIDE RECTANGLE, DISTANCE > 250 METRES")
print("=" * 65)

print("Total:", len(bmtc_gaps))

print(
    bmtc_gaps[
        [
            "stop_name",
            "stop_id",
            "stop_lat",
            "stop_lon",
            "nearest_node_distance_m"
        ]
    ].head(40).to_string(index=False)
)


# --------------------------------------------------
# METRO: group problematic records by station
# --------------------------------------------------

metro = pd.read_csv(metro_file)
metro = add_boundary_status(metro)

metro_gaps = metro[
    metro["nearest_node_distance_m"] > 250
].copy()

metro_gaps["station_id"] = metro_gaps["parent_station"].fillna(
    metro_gaps["stop_id"]
)

station_summary = (
    metro_gaps.groupby("station_id")
    .agg(
        records=("stop_id", "count"),
        max_distance_m=("nearest_node_distance_m", "max"),
        min_distance_m=("nearest_node_distance_m", "min"),
        station_name=("stop_name", "first")
    )
    .sort_values("max_distance_m", ascending=False)
)

print("\n" + "=" * 65)
print("METRO: PROBLEMATIC STATIONS")
print("=" * 65)

print(station_summary.to_string())

print("\nUnique problematic Metro stations:", len(station_summary))
