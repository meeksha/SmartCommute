
import pandas as pd
import osmnx as ox

GRAPH_FILE = "data/raw/walking/bengaluru_walking_network.graphml"
CLUSTER_FILE = "data/processed/walking/bmtc_gap_clusters.csv"

print("Loading graph and cluster data...")

G = ox.load_graphml(GRAPH_FILE)
nodes, edges = ox.graph_to_gdfs(G)

min_lon = nodes.geometry.x.min()
max_lon = nodes.geometry.x.max()
min_lat = nodes.geometry.y.min()
max_lat = nodes.geometry.y.max()

df = pd.read_csv(CLUSTER_FILE)

# Determine whether each stop is inside the graph rectangle.
df["inside_rectangle"] = (
    (df["stop_lat"] >= min_lat) &
    (df["stop_lat"] <= max_lat) &
    (df["stop_lon"] >= min_lon) &
    (df["stop_lon"] <= max_lon)
)

print("\n" + "=" * 65)
print("OVERALL COVERAGE")
print("=" * 65)

print(df["inside_rectangle"].value_counts().rename({
    True: "Inside rectangle",
    False: "Outside rectangle"
}))

print("\n" + "=" * 65)
print("CLUSTER COUNTS BY COVERAGE")
print("=" * 65)

cluster_coverage = (
    df[df["cluster"] != -1]
    .groupby(["cluster", "inside_rectangle"])
    .size()
    .unstack(fill_value=0)
)

cluster_coverage.columns = [
    "outside_rectangle" if not col else "inside_rectangle"
    for col in cluster_coverage.columns
]

for col in ["inside_rectangle", "outside_rectangle"]:
    if col not in cluster_coverage.columns:
        cluster_coverage[col] = 0

cluster_coverage["total_stops"] = (
    cluster_coverage["inside_rectangle"] +
    cluster_coverage["outside_rectangle"]
)

cluster_coverage = cluster_coverage.sort_values(
    "total_stops",
    ascending=False
)

print(cluster_coverage.head(25).to_string())

print("\n" + "=" * 65)
print("LARGEST CLUSTERS INSIDE GRAPH RECTANGLE")
print("=" * 65)

inside = df[
    (df["inside_rectangle"]) &
    (df["cluster"] != -1)
]

inside_summary = (
    inside.groupby("cluster")
    .agg(
        stop_count=("stop_id", "count"),
        centre_lat=("stop_lat", "mean"),
        centre_lon=("stop_lon", "mean"),
        average_gap_m=("nearest_node_distance_m", "mean")
    )
    .sort_values("stop_count", ascending=False)
)

print(inside_summary.head(20).to_string())

print("\n" + "=" * 65)
print("LARGEST CLUSTERS OUTSIDE GRAPH RECTANGLE")
print("=" * 65)

outside = df[
    (~df["inside_rectangle"]) &
    (df["cluster"] != -1)
]

outside_summary = (
    outside.groupby("cluster")
    .agg(
        stop_count=("stop_id", "count"),
        centre_lat=("stop_lat", "mean"),
        centre_lon=("stop_lon", "mean"),
        average_gap_m=("nearest_node_distance_m", "mean")
    )
    .sort_values("stop_count", ascending=False)
)

print(outside_summary.head(20).to_string())
