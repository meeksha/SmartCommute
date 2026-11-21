from pyrosm import OSM
from pathlib import Path
import pandas as pd

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")

bbox = [
    77.736982,
    12.998558,
    77.783980,
    13.049594
]

osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(
    network_type="walking",
    nodes=True
)

node_ids = set(nodes["id"])
edge_u = set(edges["u"])
edge_v = set(edges["v"])

missing_u = edge_u - node_ids
missing_v = edge_v - node_ids

print("\n--- PBF Walking Network Validation ---")
print("Nodes:", len(nodes))
print("Edges:", len(edges))
print("Unique node IDs:", len(node_ids))
print("Unique edge IDs:", edges["id"].nunique())

print("\nEndpoint integrity:")
print("Unique u endpoints:", len(edge_u))
print("Unique v endpoints:", len(edge_v))
print("Missing u endpoints:", len(missing_u))
print("Missing v endpoints:", len(missing_v))

print("\nDuplicate checks:")
print("Duplicate node IDs:", nodes["id"].duplicated().sum())
print("Duplicate directed edge pairs:", edges.duplicated(subset=["u", "v"]).sum())
print("Self-loop edges:", (edges["u"] == edges["v"]).sum())

print("\nEdge length statistics (metres):")
print(edges["length"].describe())

print("\nInvalid lengths:", (
    edges["length"].isna() |
    (edges["length"] <= 0)
).sum())

print("\nSample edge attributes:")
print(edges.drop(columns="geometry").head(3).to_string())

print("\nSample node attributes:")
print(nodes.drop(columns="geometry").head(3).to_string())

print("\nValidation completed.")
