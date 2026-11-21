from pathlib import Path
import pandas as pd
from pyrosm import OSM

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
bbox = [77.736982, 12.998558, 77.783980, 13.049594]

osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()

def classify(row):
    access = clean(row["access"])
    foot = clean(row["foot"])

    # Explicit pedestrian-specific tags take precedence.
    if foot in ("no", "private"):
        return "exclude_pedestrian_restricted"

    if foot in ("yes", "designated", "permissive"):
        return "include_explicit_pedestrian_access"

    if access == "no":
        return "exclude_general_access_prohibited"

    if access == "private":
        return "exclude_general_private_access"

    if access == "permissive":
        return "include_permissive_access"

    return "review_highway_default"

edges["access_class"] = edges.apply(classify, axis=1)

summary = (
    edges.groupby("access_class")
    .agg(
        edge_records=("length", "size"),
        unique_ways=("id", "nunique"),
        total_length_m=("length", "sum")
    )
    .reset_index()
)

print("\n--- Preliminary pedestrian access classification ---")
print(summary.to_string(index=False))

output_dir = Path("data/processed/walking")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "cluster_32_2_walking_access_classified.csv"

columns = [
    "id", "u", "v", "length", "highway",
    "access", "foot", "motorroad", "name", "access_class"
]

edges[columns].to_csv(output_file, index=False)

print("\nTotal edge records:", len(edges))
print("Saved:", output_file)
