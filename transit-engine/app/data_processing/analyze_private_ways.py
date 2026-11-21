from pathlib import Path
from pyrosm import OSM
import pandas as pd

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
bbox = [77.736982, 12.998558, 77.783980, 13.049594]

osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

private = edges[
    edges["access"].astype(str).str.lower() == "private"
].copy()

summary = (
    private.groupby(["id", "highway", "name", "access", "foot"], dropna=False)
    .agg(
        edge_records=("length", "size"),
        total_length=("length", "sum"),
        min_length=("length", "min"),
        max_length=("length", "max")
    )
    .reset_index()
    .sort_values("edge_records", ascending=False)
)

print("\n--- Private OSM way summary ---")
print("Private edge records:", len(private))
print("Unique OSM ways:", private["id"].nunique())
print(summary.to_string(index=False))

output = Path("data/processed/walking/cluster_32_2_private_way_summary.csv")
summary.to_csv(output, index=False)

print("\nSaved:", output)
