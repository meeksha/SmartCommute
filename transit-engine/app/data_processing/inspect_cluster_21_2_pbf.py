from pathlib import Path
import networkx as nx
from pyrosm import OSM

pbf = r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf"

# Expanded Cluster 21-2 bounding box
bbox = [
    77.641748,  # west
    12.819710,  # south
    77.688746,  # east
    12.870746   # north
]

print("Extracting Cluster 21-2...")
osm = OSM(pbf, bounding_box=bbox)
nodes, edges = osm.get_network(
    network_type="walking",
    nodes=True
)

G = nx.MultiDiGraph()
G.add_nodes_from(str(n) for n in nodes["id"])

for row in edges[["u", "v", "length"]].itertuples(index=False):
    G.add_edge(str(row.u), str(row.v), length=float(row.length))

components = sorted(
    nx.weakly_connected_components(G),
    key=len,
    reverse=True
)

print("\n--- Cluster 21-2 results ---")
print("Nodes:", len(nodes))
print("Edges:", len(edges))
print("Components:", len(components))
print("Largest component:", len(components[0]) if components else 0)

if components:
    print("Largest component coverage: {:.2f}%".format(
        len(components[0]) / G.number_of_nodes() * 100
    ))

print("Invalid lengths:", (
    edges["length"].isna() | (edges["length"] <= 0)
).sum())

print("Extraction completed.")
