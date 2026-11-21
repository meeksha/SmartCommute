from pathlib import Path
from datetime import datetime, timedelta
from functools import lru_cache
import math

import pandas as pd
import networkx as nx
import osmnx as ox

from app.routing.metro_planner import plan_metro
from app.routing.metro_fares import calculate_metro_journey_fare


BASE = Path("data")
WALK_GRAPH = BASE / "raw/walking/bengaluru_walking_network.graphml"
METRO_STOPS = BASE / "processed/metro/standard/stops.csv"
INTERCHANGES = BASE / "processed/metro_bmtc_all_station_interchanges.csv"

WALKING_SPEED_M_PER_MIN = 80


def haversine(lat1, lon1, lat2, lon2):
    """Straight-line distance between two coordinates, in metres."""
    radius = 6371000

    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )

    return 2 * radius * math.asin(math.sqrt(a))


# Walking searches never need to go further than this; bounding Dijkstra
# keeps a single-origin search from exploring the whole city graph.
MAX_WALK_SEARCH_M = 5000


@lru_cache(maxsize=1)
def load_walking_data():
    """Load the OSM walking graph and Metro entrances once per process."""
    print("Loading walking network...")
    graph = ox.load_graphml(WALK_GRAPH).to_undirected()

    print("Loading Metro entrances...")
    stops = pd.read_csv(METRO_STOPS)
    stops["location_type"] = pd.to_numeric(
        stops["location_type"], errors="coerce"
    )

    stations = stops[stops["location_type"] == 1].copy()
    entrances = stops[stops["location_type"] == 2].copy()

    entrances = entrances.dropna(
        subset=["parent_station", "stop_lat", "stop_lon"]
    )

    entrances["stop_lat"] = pd.to_numeric(entrances["stop_lat"])
    entrances["stop_lon"] = pd.to_numeric(entrances["stop_lon"])

    print("Metro stations:", len(stations))
    print("Metro entrances:", len(entrances))

    return graph, stations, entrances


def nearest_reachable_stations(
    lat, lon, graph, stations, entrances, limit=5
):
    """Return the nearest distinct reachable Metro stations by walking distance."""
    origin_node = ox.distance.nearest_nodes(
        graph, X=float(lon), Y=float(lat)
    )
    origin_data = graph.nodes[origin_node]
    origin_snap = haversine(
        lat, lon, origin_data["y"], origin_data["x"]
    )
    network_distances = nx.single_source_dijkstra_path_length(
        graph, origin_node, cutoff=MAX_WALK_SEARCH_M, weight="length"
    )
    entrance_nodes = _entrance_nodes()
    station_names = stations.set_index("stop_id")["stop_name"].to_dict()
    best_by_station = {}

    for (_, entrance), entrance_node in zip(
        entrances.iterrows(), entrance_nodes
    ):
        if entrance_node not in network_distances:
            continue
        entrance_data = graph.nodes[entrance_node]
        entrance_snap = haversine(
            entrance["stop_lat"], entrance["stop_lon"],
            entrance_data["y"], entrance_data["x"]
        )
        total_distance = (
            origin_snap + network_distances[entrance_node] + entrance_snap
        )
        station_id = str(entrance["parent_station"])
        candidate = {
            "station_id": station_id,
            "station_name": station_names.get(station_id),
            "entrance_name": entrance["stop_name"],
            "walking_distance_m": round(float(total_distance), 1),
            "walking_minutes": round(
                float(total_distance) / WALKING_SPEED_M_PER_MIN, 1
            ),
        }
        if not candidate["station_name"]:
            continue
        old = best_by_station.get(station_id)
        if old is None or candidate["walking_distance_m"] < old["walking_distance_m"]:
            best_by_station[station_id] = candidate

    candidates = sorted(
        best_by_station.values(),
        key=lambda item: item["walking_distance_m"]
    )
    if not candidates:
        raise ValueError("No Metro station is reachable in the walking network.")
    return candidates[:max(1, int(limit))]


@lru_cache(maxsize=1)
def _entrance_nodes():
    """Snap every Metro entrance to the walking graph once."""
    graph, _stations, entrances = load_walking_data()
    return tuple(ox.distance.nearest_nodes(
        graph,
        X=entrances["stop_lon"].to_numpy(),
        Y=entrances["stop_lat"].to_numpy()
    ))


@lru_cache(maxsize=1)
def _interchange_table():
    if not INTERCHANGES.exists():
        return None
    return pd.read_csv(INTERCHANGES)


def nearest_reachable_station(lat, lon, graph, stations, entrances):
    """Backward-compatible helper returning the nearest reachable station."""
    return nearest_reachable_stations(
        lat, lon, graph, stations, entrances, limit=1
    )[0]


def get_bmtc_interchange(station_id):
    """Attach the nearest qualifying BMTC stop, if one is available."""

    data = _interchange_table()
    if data is None:
        return None

    match = data[
        (data["metro_station_id"].astype(str) == str(station_id))
        & (data["interchange_status"] == "OSM_MODELLED_CONNECTION")
    ]

    if match.empty:
        return None

    row = match.iloc[0]

    return {
        "stop_id": row["bmtc_stop_id"],
        "stop_name": row["bmtc_stop_name"],
        "estimated_walk_m": row["estimated_total_walk_m"],
        "estimated_walk_minutes": row["estimated_walk_minutes"],
        "note": "BMTC interchange candidate only; no current BMTC timetable verified."
    }


def plan_journey(
    origin_lat,
    origin_lon,
    destination_lat,
    destination_lon,
    travel_date,
    departure_time,
    station_candidates_per_side=5,
):
    """Find valid walking + Metro options across multiple station pairs."""
    graph, stations, entrances = load_walking_data()
    origin_candidates = nearest_reachable_stations(
        origin_lat, origin_lon, graph, stations, entrances,
        limit=station_candidates_per_side
    )
    destination_candidates = nearest_reachable_stations(
        destination_lat, destination_lon, graph, stations, entrances,
        limit=station_candidates_per_side
    )
    start = datetime.strptime(
        f"{travel_date} {departure_time}", "%Y-%m-%d %H:%M"
    )
    journeys = []
    checked_pairs = 0
    unavailable_pairs = []

    for origin_metro in origin_candidates:
        for destination_metro in destination_candidates:
            if origin_metro["station_id"] == destination_metro["station_id"]:
                continue
            raw_metro_start = start + timedelta(
                minutes=origin_metro["walking_minutes"]
            )
            metro_start = raw_metro_start.replace(second=0, microsecond=0)
            if metro_start < raw_metro_start:
                metro_start += timedelta(minutes=1)
            metro_result = plan_metro(
                origin_metro["station_name"],
                destination_metro["station_name"],
                metro_start.strftime("%Y-%m-%d"),
                metro_start.strftime("%H:%M")
            )
            checked_pairs += 1
            if (
                metro_result.get("status") != "success"
                or not metro_result.get("legs")
            ):
                unavailable_pairs.append({
                    "origin_station": origin_metro["station_name"],
                    "destination_station": destination_metro["station_name"],
                    "reason": metro_result.get("message", "No train legs found"),
                })
                continue

            egress_minutes = destination_metro["walking_minutes"]
            total_minutes = (
                origin_metro["walking_minutes"]
                + metro_result["duration_minutes"]
                + egress_minutes
            )
            metro_fare = calculate_metro_journey_fare(
                metro_result.get("legs", [])
            )
            journeys.append({
                "origin_metro": origin_metro,
                "destination_metro": destination_metro,
                "walking_access_minutes": origin_metro["walking_minutes"],
                "walking_egress_minutes": egress_minutes,
                "metro_journey": metro_result,
                "metro_fare": metro_fare,
                "total_estimated_duration_minutes": round(total_minutes, 1),
                "total_estimated_walking_metres": round(
                    origin_metro["walking_distance_m"]
                    + destination_metro["walking_distance_m"], 1
                ),
                "limitations": [
                    "Walking distances are OSM model estimates, not field verified.",
                    "Metro times use the published standard GTFS timetable.",
                    "Live delays, vehicle positions and real-time traffic are unavailable.",
                ],
            })

    if not journeys:
        return {
            "status": "unavailable",
            "message": (
                "No valid Metro journey with at least one train leg was found "
                "between the reachable station combinations."
            ),
            "origin_station_candidates": origin_candidates,
            "destination_station_candidates": destination_candidates,
            "station_pairs_checked": checked_pairs,
            "unavailable_pairs": unavailable_pairs,
        }

    journeys.sort(
        key=lambda item: (
            item["total_estimated_duration_minutes"],
            item["total_estimated_walking_metres"],
        )
    )
    best = journeys[0]
    return {
        "status": "success",
        "travel_date": travel_date,
        "origin_coordinates": [origin_lat, origin_lon],
        "destination_coordinates": [destination_lat, destination_lon],
        "departure_time": departure_time,
        **best,
        "best_journey": best,
        "alternative_journeys": journeys[1:],
        "journeys_compared": len(journeys),
        "station_pairs_checked": checked_pairs,
        "origin_station_candidates": origin_candidates,
        "destination_station_candidates": destination_candidates,
        "origin_bmtc_interchange": get_bmtc_interchange(
            best["origin_metro"]["station_id"]
        ),
        "destination_bmtc_interchange": get_bmtc_interchange(
            best["destination_metro"]["station_id"]
        ),
    }
