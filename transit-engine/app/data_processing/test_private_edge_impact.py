from pathlib import Path
import networkx as nx
from pyrosm import OSM

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
bbox = [77.736982, 12.998558, 77.783980, 13.049594]

osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

G_all = nx.MultiDiGraph()
G_public = nx.MultiDiGraph()

for row in nodes[["id"]].itertuples(index=False):
    node_id = str(row.id)
    G_all.add_node(node_id)
    G_public.add_node(node_id)

for row in edges[["u", "v", "length", "access"]].itertuples(index=False):
    u, v = str(row.u), str(row.v)
    length = float(row.length)
    access = str(row.access).lower()

    G_all.add_edge(u, v, length=length)

    if access != "private":
        G_public.add_edge(u, v, length=length)

def report(name, graph):
    components = sorted(
        nx.weakly_connected_components(graph),
        key=len,
        reverse=True
    )

    largest = len(components[0])

    print(f"\n--- {name} ---")
    print("Nodes:", graph.number_of_nodes())
    print("Edges:", graph.number_of_edges())
    print("Components:", len(components))
    print("Largest component:", largest)
    print("Largest component coverage: {:.2f}%".format(
        largest / graph.number_of_nodes() * 100
    ))
    print("Small components (10 nodes or fewer):",
          sum(len(c) <= 10 for c in components))

report("All extracted edges", G_all)
report("Excluding access=private", G_public)

print("\nPrivate edge records excluded:", len(edges) - len(
    edges[edges["access"].astype(str).str.lower() != "private"]
))

print("\nAnalysis completed. Original data unchanged.")
