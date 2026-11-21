
import pandas as pd
import osmnx as ox

GRAPH_FILE = "data/raw/walking/bengaluru_walking_network.graphml"
INPUT = "data/processed/walking/bmtc_gap_clusters.csv"
OUTPUT = "data/processed/walking/walking_expansion_areas.csv"

print("Loading walking graph...")
G = ox.load_graphml(GRAPH_FILE)
nodes, edges = ox.graph_to_gdfs(G)

min_lon = nodes.geometry.x.min()
max_lon = nodes.geometry.x.max()
min_lat = nodes.geometry.y.min()
max_lat = nodes.geometry.y.max()

print("Loading BMTC gap clusters...")
df = pd.read_csv(INPUT)

df["inside_rectangle"] = (
    (df["stop_lat"] >= min_lat) &
    (df["stop_lat"] <= max_lat) &
    (df["stop_lon"] >= min_lon) &
    (df["stop_lon"] <= max_lon)
)

# Select the five largest clusters based on their
# number of stops inside the original graph rectangle.
inside = df[
    (df["cluster"] != -1) &
    df["inside_rectangle"]
]

priority_clusters = (
    inside.groupby("cluster")
    .size()
    .sort_values(ascending=False)
    .head(5)
    .index
)

# IMPORTANT: Include ALL stops in those clusters,
# including stops outside the original rectangle.
selected = df[df["cluster"].isin(priority_clusters)].copy()

summary = (
    selected.groupby("cluster")
    .agg(
        total_stops=("stop_id", "count"),
        inside_stops=("inside_rectangle", "sum"),
        south=("stop_lat", "min"),
        north=("stop_lat", "max"),
        west=("stop_lon", "min"),
        east=("stop_lon", "max")
    )
)

summary["outside_stops"] = (
    summary["total_stops"] - summary["inside_stops"]
)

# Add approximately 1 km margin.
lat_margin = 1.0 / 111.0
lon_margin = 1.0 / (111.0 * 0.974)

summary["south"] -= lat_margin
summary["north"] += lat_margin
summary["west"] -= lon_margin
summary["east"] += lon_margin

summary = summary.reset_index()

summary.to_csv(OUTPUT, index=False)

print("\n" + "=" * 70)
print("COMPLETE EXPANSION AREAS")
print("=" * 70)
print(summary.to_string(index=False))

print("\nTotal stops covered by selected clusters:",
      summary["total_stops"].sum())

print("\nSaved to:", OUTPUT)
