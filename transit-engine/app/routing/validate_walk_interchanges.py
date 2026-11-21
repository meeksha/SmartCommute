from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox

BASE = Path("data/processed")
GRAPH_PATH = Path("data/raw/walking/bengaluru_walking_network.graphml")
OUTPUT = BASE / "bmtc_metro_walk_validation.csv"

MAX_STRAIGHT_DISTANCE = 600
MAX_SNAP_DISTANCE = 100
WALK_SPEED = 1.2


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(
        np.radians, [lat1, lon1, lat2, lon2]
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    )
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def main():
    if not GRAPH_PATH.exists():
        raise FileNotFoundError(f"Walking graph not found: {GRAPH_PATH}")

    print("Loading walking network...")
    graph = ox.load_graphml(GRAPH_PATH)
    graph = graph.to_undirected()

    print("Walking graph nodes:", graph.number_of_nodes())
    print("Walking graph edges:", graph.number_of_edges())

    bus = pd.read_csv(BASE / "bmtc_stops.csv", dtype=str)
    metro = pd.read_csv(
        BASE / "metro" / "standard" / "stops.csv", dtype=str
    )

    for col in ["stop_lat", "stop_lon"]:
        bus[col] = pd.to_numeric(bus[col], errors="coerce")
        metro[col] = pd.to_numeric(metro[col], errors="coerce")

    bus = bus.dropna(subset=["stop_lat", "stop_lon"]).reset_index(drop=True)

    # Use actual Metro entrance records, not station-centre coordinates.
    entrances = metro[
        metro["location_type"] == "2"
    ].dropna(subset=["stop_lat", "stop_lon"]).reset_index(drop=True)

    print("BMTC stops:", len(bus))
    print("Metro entrances:", len(entrances))

    # Find BMTC-stop / Metro-entrance pairs within 600 m straight-line.
    bus_lat = bus["stop_lat"].to_numpy()
    bus_lon = bus["stop_lon"].to_numpy()
    ent_lat = entrances["stop_lat"].to_numpy()
    ent_lon = entrances["stop_lon"].to_numpy()

    lat1 = np.radians(bus_lat[:, None])
    lon1 = np.radians(bus_lon[:, None])
    lat2 = np.radians(ent_lat[None, :])
    lon2 = np.radians(ent_lon[None, :])

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    )
    distances = 6371000 * 2 * np.arcsin(np.sqrt(a))

    bus_indices, entrance_indices = np.where(
        distances <= MAX_STRAIGHT_DISTANCE
    )

    print("Candidate stop-to-entrance pairs:", len(bus_indices))

    if len(bus_indices) == 0:
        print("No candidates found.")
        return

    # Snap every coordinate to its nearest pedestrian-network node.
    print("Snapping coordinates to walking-network nodes...")

    bus_nodes = ox.distance.nearest_nodes(
        graph,
        X=bus_lon,
        Y=bus_lat
    )

    entrance_nodes = ox.distance.nearest_nodes(
        graph,
        X=ent_lon,
        Y=ent_lat
    )

    bus_snap = np.array([
        haversine(
            bus.iloc[i]["stop_lat"],
            bus.iloc[i]["stop_lon"],
            graph.nodes[node]["y"],
            graph.nodes[node]["x"]
        )
        for i, node in enumerate(bus_nodes)
    ])

    entrance_snap = np.array([
        haversine(
            entrances.iloc[i]["stop_lat"],
            entrances.iloc[i]["stop_lon"],
            graph.nodes[node]["y"],
            graph.nodes[node]["x"]
        )
        for i, node in enumerate(entrance_nodes)
    ])

    # Cache shortest paths so repeated node pairs are not recalculated.
    path_cache = {}
    records = []

    print("Calculating pedestrian routes...")

    for bus_i, entrance_i in zip(bus_indices, entrance_indices):
        bus_node = bus_nodes[bus_i]
        entrance_node = entrance_nodes[entrance_i]

        direct_distance = float(distances[bus_i, entrance_i])

        record = {
            "bmtc_stop_id": bus.iloc[bus_i]["stop_id"],
            "bmtc_stop_name": bus.iloc[bus_i]["stop_name"],
            "metro_station_id": entrances.iloc[entrance_i]["parent_station"],
            "metro_entrance_id": entrances.iloc[entrance_i]["stop_id"],
            "metro_entrance_name": entrances.iloc[entrance_i]["stop_name"],
            "straight_line_distance_m": round(direct_distance, 1),
            "bmtc_snap_distance_m": round(float(bus_snap[bus_i]), 1),
            "entrance_snap_distance_m": round(float(entrance_snap[entrance_i]), 1),
            "walk_distance_m": None,
            "walk_minutes": None,
            "validation_status": None
        }

        if (
            bus_snap[bus_i] > MAX_SNAP_DISTANCE
            or entrance_snap[entrance_i] > MAX_SNAP_DISTANCE
        ):
            record["validation_status"] = "SNAP_TOO_FAR"
            records.append(record)
            continue

        key = (bus_node, entrance_node)

        if key not in path_cache:
            try:
                path_cache[key] = nx.shortest_path_length(
                    graph,
                    source=bus_node,
                    target=entrance_node,
                    weight="length"
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                path_cache[key] = None

        walk_distance = path_cache[key]

        if walk_distance is None:
            record["validation_status"] = "NO_OSM_PATH"
        else:
            record["walk_distance_m"] = round(float(walk_distance), 1)
            record["walk_minutes"] = round(
                float(walk_distance) / WALK_SPEED / 60, 1
            )

            if walk_distance <= 600:
                record["validation_status"] = "OSM_PATH_FOUND"
            else:
                record["validation_status"] = "LONG_WALK"

        records.append(record)

    result = pd.DataFrame(records)

    # Keep the best entrance for each BMTC-stop / Metro-station pair.
    result["_rank"] = result["walk_distance_m"].fillna(float("inf"))
    result = (
        result.sort_values("_rank")
        .drop_duplicates(
            ["bmtc_stop_id", "metro_station_id"],
            keep="first"
        )
        .drop(columns="_rank")
        .sort_values(["metro_station_id", "walk_distance_m"])
    )

    result.to_csv(OUTPUT, index=False)

    print("\nPEDESTRIAN NETWORK VALIDATION")
    print("--------------------------------")
    print("Validated stop-station pairs:", len(result))
    print("\nValidation status:")
    print(result["validation_status"].value_counts(dropna=False))
    print("\nAverage walk distance for OSM paths:")
    valid = result[result["validation_status"] == "OSM_PATH_FOUND"]
    if not valid.empty:
        print(round(valid["walk_distance_m"].mean(), 1), "metres")

    print("\nClosest real network connections:")
    print(
        valid.nsmallest(15, "walk_distance_m")[
            [
                "bmtc_stop_name",
                "metro_station_id",
                "metro_entrance_name",
                "straight_line_distance_m",
                "walk_distance_m",
                "walk_minutes"
            ]
        ].to_string(index=False)
    )

    print("\nSaved:", OUTPUT)
    print(
        "\nNOTE: OSM network paths are modelled pedestrian routes, "
        "not on-site verified paths."
    )


if __name__ == "__main__":
    main()
