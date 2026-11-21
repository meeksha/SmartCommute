from pathlib import Path
import pandas as pd
from pyrosm import OSM

pbf = r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf"
bbox = [77.641748, 12.819710, 77.688746, 12.870746]

osm = OSM(pbf, bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

def clean(value):
    return "" if pd.isna(value) else str(value).strip().lower()

def classify(row):
    access = clean(row["access"])
    foot = clean(row["foot"])

    if foot in ("no", "private"):
        return "exclude_pedestrian_restricted"
    if foot in ("yes", "designated", "permissive"):
        return "include_explicit_pedestrian_access"
    if access == "permissive":
        return "include_permissive_access"
    if access in ("no", "private"):
        return "exclude_general_access_restricted"
    return "review_highway_default"

edges["access_class"] = edges.apply(classify, axis=1)

print("\n--- Cluster 21-2 access classification ---")
print(edges["access_class"].value_counts().to_string())

print("\n--- Access tag distribution ---")
print(edges["access"].fillna("missing").value_counts().to_string())

print("\n--- Foot tag distribution ---")
print(edges["foot"].fillna("missing").value_counts().to_string())

output = Path(
    "data/processed/walking/cluster_21_2_access_classified.csv"
)
edges.to_csv(output, index=False)

print("\nSaved:", output)