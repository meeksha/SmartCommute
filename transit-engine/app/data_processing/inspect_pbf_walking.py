from pyrosm import OSM
from pathlib import Path

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")

bbox = [
    77.736982,
    12.998558,
    77.783980,
    13.049594
]

print("Loading regional OSM PBF...")
osm = OSM(str(pbf_path), bounding_box=bbox)

print("Extracting walking network...")
nodes, edges = osm.get_network(
    network_type="walking",
    nodes=True
)

print("\n--- Corrected extraction results ---")
print("Node records:", len(nodes))
print("Edge records:", len(edges))

print("\nNode geometry types:")
print(nodes.geometry.geom_type.value_counts())

print("\nEdge geometry types:")
print(edges.geometry.geom_type.value_counts())

print("\nNode coordinate bounds:")
print(nodes.total_bounds)

print("\nEdge coordinate bounds:")
print(edges.total_bounds)

print("\nSample edge records:")
print(edges[["id", "u", "v", "length"]].head(5).to_string())

print("\nVerification completed.")
