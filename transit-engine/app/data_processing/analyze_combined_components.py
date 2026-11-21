from pathlib import Path
import pandas as pd
import networkx as nx
import osmnx as ox
from pyrosm import OSM

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
pilot_path = Path("data/raw/walking/expansions/bmtc_cluster_32_2.graphml")

bbox = [77.736982, 12.998558, 77.783980, 13.049594]

print("Extracting PBF network...")
osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

print("Loading pilot graph...")
pilot = ox.load_graphml(pilot_path)

G = nx.MultiDiGraph()

# Add PBF nodes with coordinates.
for row in nodes[["id", "lon", "lat"]].itertuples(index=False):
    G.add_node(str(row.id), x=float(row.lon), y=float(row.lat), source="pbf")

# Add PBF edges.
for row in edges[["u", "v", "length"]].itertuples(index=False):
    G.add_edge(str(row.u), str(row.v), length=float(row.length), source="pbf")

# Add pilot nodes and edges.
for node_id, data in pilot.nodes(data=True):
    G.add_node(str(node_id), **data)

for u, v, key, data in pilot.edges(keys=True, data=True):
    G.add_edge(str(u), str(v), **data, source="pilot")

pbf_ids = set(str(n) for n in nodes["id"])
pilot_ids = set(str(n) for n in pilot.nodes)

components = sorted(
    nx.weakly_connected_components(G),
    key=len,
    reverse=True
)

rows = []

for index, component in enumerate(components, start=1):
    subgraph = G.subgraph(component)

    pbf_count = len(component & pbf_ids)
    pilot_count = len(component & pilot_ids)

    pbf_edges = 0
    pilot_edges = 0

    for u, v, key, data in subgraph.edges(keys=True, data=True):
        if data.get("source") == "pbf":
            pbf_edges += 1
        elif data.get("source") == "pilot":
            pilot_edges += 1

    coordinates = [
        (data.get("x"), data.get("y"))
        for _, data in subgraph.nodes(data=True)
        if data.get("x") is not None and data.get("y") is not None
    ]

    if coordinates:
        mean_lon = sum(p[0] for p in coordinates) / len(coordinates)
        mean_lat = sum(p[1] for p in coordinates) / len(coordinates)
    else:
        mean_lon = None
        mean_lat = None

    rows.append({
        "component_id": index,
        "node_count": len(component),
        "pbf_nodes": pbf_count,
        "pilot_nodes": pilot_count,
        "pilot_only_nodes": len(component - pbf_ids),
        "pbf_edges": pbf_edges,
        "pilot_edges": pilot_edges,
        "mean_lat": mean_lat,
        "mean_lon": mean_lon
    })

df = pd.DataFrame(rows)

output_dir = Path("data/processed/walking")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "cluster_32_2_combined_components.csv"
df.to_csv(output_file, index=False)

print("\n--- Component summary ---")
print("Total components:", len(df))
print("Largest component:")
print(df.head(1).to_string(index=False))

print("\nComponents containing pilot-only nodes:")
print(
    df[df["pilot_only_nodes"] > 0]
    .to_string(index=False)
)

print("\nSmallest 15 components:")
print(df.tail(15).to_string(index=False))

print("\nSaved:", output_file)
