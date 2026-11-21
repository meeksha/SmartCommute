from pathlib import Path
from pyrosm import OSM
import pandas as pd

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
bbox = [77.736982, 12.998558, 77.783980, 13.049594]

osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

def clean(value):
    if pd.isna(value):
        return "missing"
    return str(value).strip().lower()

edges["access_clean"] = edges["access"].apply(clean)
edges["foot_clean"] = edges["foot"].apply(clean)
edges["highway_clean"] = edges["highway"].apply(clean)

print("\n--- Access tag distribution ---")
print(edges["access_clean"].value_counts(dropna=False).to_string())

print("\n--- Foot tag distribution ---")
print(edges["foot_clean"].value_counts(dropna=False).to_string())

print("\n--- Highway distribution ---")
print(edges["highway_clean"].value_counts(dropna=False).to_string())

summary = (
    edges.groupby(
        ["highway_clean", "access_clean", "foot_clean"],
        dropna=False
    )
    .agg(
        edge_records=("length", "size"),
        total_length=("length", "sum"),
        unique_ways=("id", "nunique")
    )
    .reset_index()
    .sort_values("edge_records", ascending=False)
)

output = Path("data/processed/walking/cluster_32_2_access_classification.csv")
summary.to_csv(output, index=False)

print("\n--- Combined tag classification ---")
print(summary.to_string(index=False))

print("\nSaved:", output)
