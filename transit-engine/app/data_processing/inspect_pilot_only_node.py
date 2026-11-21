from pathlib import Path
import osmnx as ox
from pyrosm import OSM

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
pilot_path = Path("data/raw/walking/expansions/bmtc_cluster_32_2.graphml")

bbox = [77.736982, 12.998558, 77.783980, 13.049594]

print("Extracting PBF nodes...")
osm = OSM(str(pbf_path), bounding_box=bbox)
pbf_nodes, pbf_edges = osm.get_network(
    network_type="walking",
    nodes=True
)

print("Loading pilot graph...")
pilot = ox.load_graphml(pilot_path)

pbf_ids = {int(n) for n in pbf_nodes["id"]}
pilot_ids = {int(n) for n in pilot.nodes}

pilot_only = pilot_ids - pbf_ids

print("\nPilot-only node count:", len(pilot_only))

for node_id in sorted(pilot_only):
    print("\n--- Pilot-only node ---")
    print("OSM node ID:", node_id)
    print("Node attributes:")
    print(pilot.nodes[node_id])

    print("\nConnected edges:")
    for u, v, key, data in pilot.edges(node_id, keys=True, data=True):
        print(f"{u} -> {v}: {data}")

    print("\nIncoming edges:")
    for u, v, key, data in pilot.in_edges(node_id, keys=True, data=True):
        print(f"{u} -> {v}: {data}")

print("\nInspection completed. No source files modified.")
