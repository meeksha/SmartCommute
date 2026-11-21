
import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN

FILE = "data/processed/walking/bmtc_walking_node_mapping.csv"

df = pd.read_csv(FILE)

# Keep only stops inside the graph rectangle
# but more than 250 metres from a walking node.
gaps = df[
    (df["nearest_node_distance_m"] > 250)
].copy()

# Haversine clustering using latitude and longitude.
coordinates = np.radians(
    gaps[["stop_lat", "stop_lon"]].values
)

# Group stops within approximately 1 km.
earth_radius_km = 6371.0088

model = DBSCAN(
    eps=1.0 / earth_radius_km,
    min_samples=3,
    metric="haversine"
)

gaps["cluster"] = model.fit_predict(coordinates)

print("\n" + "=" * 65)
print("BMTC GEOGRAPHICAL GAP CLUSTERS")
print("=" * 65)

cluster_summary = (
    gaps[gaps["cluster"] != -1]
    .groupby("cluster")
    .agg(
        stop_count=("stop_id", "count"),
        centre_lat=("stop_lat", "mean"),
        centre_lon=("stop_lon", "mean"),
        average_gap_m=("nearest_node_distance_m", "mean"),
        maximum_gap_m=("nearest_node_distance_m", "max")
    )
    .sort_values("stop_count", ascending=False)
)

print("\nNumber of clusters:", len(cluster_summary))
print("\nLargest clusters:")
print(cluster_summary.head(20).to_string())

print("\nUnclustered stops:", (gaps["cluster"] == -1).sum())

# Save cluster assignments for later geographical analysis.
output = "data/processed/walking/bmtc_gap_clusters.csv"
gaps.to_csv(output, index=False)

print("\nSaved cluster assignments to:", output)
