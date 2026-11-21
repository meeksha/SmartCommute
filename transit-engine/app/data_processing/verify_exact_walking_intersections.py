
from pathlib import Path

import osmnx as ox
import pandas as pd
from pyrosm import OSM
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import transform


PBF = r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf"

BBOX = [77.736982, 12.998558, 77.783980, 13.049594]

CANDIDATE_PATH = Path(
    "data/processed/walking/cluster_32_2_pbf_candidate.graphml"
)

CITY_PATH = Path(
    "data/raw/walking/bengaluru_walking_network.graphml"
)

# Candidate and city edge pairs identified in the previous analysis.
TARGETS = [
    {
        "name": "Component 52",
        "candidate": (13347448025, 13347448024),
        "city": ("7398250033", "13347448073"),
    },
    {
        "name": "Component 52",
        "candidate": (13347448026, 13347448025),
        "city": ("7398250033", "13347448073"),
    },
    {
        "name": "Component 32",
        "candidate": (11007226847, 11007226846),
        "city": ("6536537216", "6536537221"),
    },
]

transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:32643",
    always_xy=True
)


def project_geometry(geometry):
    return transform(
        lambda x, y, z=None: transformer.transform(x, y),
        geometry
    )


def make_line(u, v, graph):
    return LineString([
        (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
        (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"]))
    ])


print("Extracting original Cluster 32-2 PBF edges...")
osm = OSM(PBF, bounding_box=BBOX)
nodes, pbf_edges = osm.get_network(
    network_type="walking",
    nodes=True
)

print("PBF edge columns:", pbf_edges.columns.tolist())

print("\nLoading candidate and city graphs...")
candidate = ox.load_graphml(CANDIDATE_PATH)
city = ox.load_graphml(CITY_PATH)

for target in TARGETS:
    print("\n" + "=" * 65)
    print(target["name"])
    print("=" * 65)

    cu, cv = target["candidate"]
    city_u, city_v = target["city"]

    # Locate the exact original PBF directed edge.
    pbf_match = pbf_edges[
        (pbf_edges["u"] == cu) &
        (pbf_edges["v"] == cv)
    ]

    print("\nCandidate PBF edge:")
    if pbf_match.empty:
        print("Exact directed edge not found in PBF extraction.")
        continue

    for _, row in pbf_match.iterrows():
        print(row.drop(labels=["geometry"], errors="ignore").to_dict())

        pbf_geometry = row.get("geometry")

        if pbf_geometry is not None:
            print("PBF geometry type:", pbf_geometry.geom_type)
            print("PBF geometry length:", pbf_geometry.length)

    # Locate the original city edge.
    city_matches = [
        (u, v, key, data)
        for u, v, key, data in city.edges(
            keys=True,
            data=True
        )
        if str(u) == city_u and str(v) == city_v
    ]

    if not city_matches:
        city_matches = [
            (u, v, key, data)
            for u, v, key, data in city.edges(
                keys=True,
                data=True
            )
            if str(u) == city_v and str(v) == city_u
        ]

    print("\nOriginal city edge attributes:")
    if not city_matches:
        print("City edge not found.")
        continue

    for u, v, key, data in city_matches:
        print({
            key: data.get(key)
            for key in [
                "osmid", "highway", "access", "foot",
                "bridge", "tunnel", "layer", "oneway",
                "name", "length"
            ]
        })

        city_geometry = data.get("geometry")

        if city_geometry is None:
            city_geometry = make_line(u, v, city)

        for _, pbf_row in pbf_match.iterrows():
            pbf_geometry = pbf_row.get("geometry")

            if pbf_geometry is None:
                continue

            pbf_projected = project_geometry(pbf_geometry)
            city_projected = project_geometry(city_geometry)

            print("\nExact geometry comparison:")
            print(
                "Distance (m):",
                round(pbf_projected.distance(city_projected), 3)
            )
            print(
                "Intersects:",
                pbf_projected.intersects(city_projected)
            )
            print(
                "Overlaps:",
                pbf_projected.overlaps(city_projected)
            )

print("\nVerification completed. No graph files were modified.")
