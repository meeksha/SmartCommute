
import pandas as pd
import numpy as np
import osmnx as ox
from sklearn.cluster import DBSCAN

INPUT = "data/processed/walking/bmtc_gap_clusters.csv"
GRAPH_FILE = "data/raw/walking/bengaluru_walking_network.graphml"

OUTPUT = "data/processed/walking/walking_expansion_subclusters.csv"

print("Loading walking graph...")
G = ox.load_graphml(GRAPH_FILE)
nodes, edges = ox.graph_to_gdfs(G)

min_lon = nodes.geometry.x.min()
max_lon = nodes.geometry.x.max()
min_lat = nodes.geometry.y.min()
max_lat = nodes.geometry.y.max()

df = pd.read_csv(INPUT)

df["inside_rectangle"] = (
    (df["stop_lat"] >= min_lat) &
    (df["stop_lat"] <= max_lat) &
    (df["stop_lon"] >= min_lon) &
    (df["stop_lon"] <= max_lon)
)

# Select the five priority clusters using their
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

selected = df[df["cluster"].isin(priority_clusters)].copy()

earth_radius_km = 6371.0088
results = []
noise_count = {}

print("\nSplitting large clusters into 500 m groups...")

for parent_id in priority_clusters:

    group = selected[selected["cluster"] == parent_id].copy()

    coordinates = np.radians(
        group[["stop_lat", "stop_lon"]].values
    )

    model = DBSCAN(
        eps=0.5 / earth_radius_km,
        min_samples=3,
        metric="haversine"
    )

    group["subcluster"] = model.fit_predict(coordinates)

    noise_count[parent_id] = int(
        (group["subcluster"] == -1).sum()
    )

    for sub_id, sub in group[
        group["subcluster"] != -1
    ].groupby("subcluster"):

        results.append({
            "parent_cluster": int(parent_id),
            "subcluster": int(sub_id),
            "stop_count": len(sub),
            "inside_stops": int(sub["inside_rectangle"].sum()),
            "outside_stops": int((~sub["inside_rectangle"]).sum()),
            "south": sub["stop_lat"].min(),
            "north": sub["stop_lat"].max(),
            "west": sub["stop_lon"].min(),
            "east": sub["stop_lon"].max(),
            "centre_lat": sub["stop_lat"].mean(),
            "centre_lon": sub["stop_lon"].mean(),
            "average_gap_m": sub["nearest_node_distance_m"].mean(),
            "maximum_gap_m": sub["nearest_node_distance_m"].max()
        })

result = pd.DataFrame(results)

if not result.empty:
    result = result.sort_values(
        ["parent_cluster", "stop_count"],
        ascending=[True, False]
    )

    result.to_csv(OUTPUT, index=False)

    print("\n" + "=" * 75)
    print("COMPACT EXPANSION AREAS")
    print("=" * 75)

    print(result.to_string(index=False))

    print("\nTotal compact groups:", len(result))
    print("Total stops in compact groups:", result["stop_count"].sum())

    print("\nUnclustered stops by original cluster:")
    print(noise_count)

    print("\nSaved to:", OUTPUT)

else:
    print("No compact groups were found.")
