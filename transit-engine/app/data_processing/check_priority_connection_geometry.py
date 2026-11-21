
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString
from shapely.ops import nearest_points
from pyproj import Transformer


CITY_PATH = Path(
    "data/raw/walking/bengaluru_walking_network.graphml"
)

CANDIDATES = {
    ("21-2", 44): (
        "data/processed/walking/cluster_21_2_pbf_candidate.graphml"
    ),
    ("32-2", 52): (
        "data/processed/walking/cluster_32_2_pbf_candidate.graphml"
    ),
    ("32-2", 32): (
        "data/processed/walking/cluster_32_2_pbf_candidate.graphml"
    ),
}

# Use projected coordinates in metres.
transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:32643",
    always_xy=True
)


def projected_node(graph, node):
    data = graph.nodes[node]
    return transformer.transform(
        float(data["x"]),
        float(data["y"])
    )


def edge_geometry(graph, u, v, data):
    if data.get("geometry") is not None:
        geometry = data["geometry"]
        return geometry

    return LineString([
        (graph.nodes[u]["x"], graph.nodes[u]["y"]),
        (graph.nodes[v]["x"], graph.nodes[v]["y"])
    ])


def project_geometry(geometry):
    from shapely.ops import transform

    return transform(
        lambda x, y, z=None: transformer.transform(x, y),
        geometry
    )


print("Loading original city graph...")
city = ox.load_graphml(CITY_PATH)
city_projected = ox.project_graph(city)

city_edges = []

for u, v, key, data in city_projected.edges(
    keys=True,
    data=True
):
    geometry = data.get("geometry")

    if geometry is None:
        geometry = LineString([
            (city_projected.nodes[u]["x"], city_projected.nodes[u]["y"]),
            (city_projected.nodes[v]["x"], city_projected.nodes[v]["y"])
        ])

    city_edges.append({
        "u": str(u),
        "v": str(v),
        "key": key,
        "geometry": geometry,
        "highway": str(data.get("highway", "")),
        "access": str(data.get("access", "")),
    })


for (cluster, component_number), path in CANDIDATES.items():

    print("\n" + "=" * 65)
    print(f"CLUSTER {cluster} | COMPONENT {component_number}")
    print("=" * 65)

    G = ox.load_graphml(path)

    components = list(nx.weakly_connected_components(G))
    component = components[component_number - 1]

    for u, v, key, data in G.edges(
        component,
        keys=True,
        data=True
    ):

        candidate_line = LineString([
            projected_node(G, u),
            projected_node(G, v)
        ])

        # Find the nearest original city edge to this candidate edge.
        nearest = min(
            city_edges,
            key=lambda edge: candidate_line.distance(edge["geometry"])
        )

        city_line = nearest["geometry"]

        distance = candidate_line.distance(city_line)
        intersection = candidate_line.intersects(city_line)

        point_candidate, point_city = nearest_points(
            candidate_line,
            city_line
        )

        print("\nCandidate edge:", u, "->", v)
        print("Candidate highway:", data.get("highway"))
        print("Candidate access class:", data.get("access_class"))
        print("City edge:", nearest["u"], "->", nearest["v"])
        print("City highway:", nearest["highway"])
        print("Geometry distance: {:.3f} m".format(distance))
        print("Geometries intersect:", intersection)
        print(
            "Nearest candidate point:",
            tuple(round(x, 3) for x in point_candidate.coords[0])
        )
        print(
            "Nearest city point:",
            tuple(round(x, 3) for x in point_city.coords[0])
        )

print("\nGeometry inspection completed.")
print("No graph files were modified.")
