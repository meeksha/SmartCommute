from pathlib import Path
import networkx as nx
import osmnx as ox
import pandas as pd

path = Path("data/processed/walking/cluster_21_2_pbf_candidate.graphml")

print("Loading candidate GraphML...")
G = ox.load_graphml(path)

print("\n--- Graph structure ---")
print("Nodes:", G.number_of_nodes())
print("Edges:", G.number_of_edges())
print("CRS:", G.graph.get("crs"))

invalid_coords = [
    n for n, d in G.nodes(data=True)
    if not (-180 <= float(d["x"]) <= 180)
    or not (-90 <= float(d["y"]) <= 90)
]

edge_data = [d for _, _, _, d in G.edges(keys=True, data=True)]
lengths = pd.to_numeric([d.get("length") for d in edge_data], errors="coerce")

print("\n--- Integrity ---")
print("Invalid coordinates:", len(invalid_coords))
print("Missing length:", sum("length" not in d for d in edge_data))
print("Missing access class:", sum("access_class" not in d for d in edge_data))
print("Invalid lengths:", pd.isna(lengths).sum() + (lengths <= 0).sum())

print("\n--- Access classification ---")
print(pd.Series([d["access_class"] for d in edge_data]).value_counts().to_string())

components = sorted(nx.weakly_connected_components(G), key=len, reverse=True)

print("\n--- Connectivity ---")
print("Components:", len(components))
print("Largest component:", len(components[0]))
print("Coverage: {:.2f}%".format(len(components[0]) / G.number_of_nodes() * 100))

print("\nValidation completed.")
