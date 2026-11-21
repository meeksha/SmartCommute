import pandas as pd
import networkx as nx
from pathlib import Path

BASE = Path("data/processed")
OUTPUT = Path("data/processed")

def gtfs_to_seconds(value):
    """Convert GTFS HH:MM:SS to seconds, including times beyond 24:00."""

    if pd.isna(value) or not str(value).strip():
        return None

    try:
        h, m, s = map(int, str(value).split(":"))
        return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return None


def build_bmtc_graph():

    print("\nLoading BMTC data...")

    stops = pd.read_csv(BASE / "bmtc_stops.csv", dtype=str)
    trips = pd.read_csv(BASE / "bmtc_trips.csv", dtype=str)
    stop_times = pd.read_csv(
        BASE / "bmtc_stop_times.csv",
        dtype=str
    )

    routes = pd.read_csv(BASE / "bmtc_routes.csv", dtype=str)

    # Validate required columns
    required_trips = {"trip_id", "route_id"}
    required_times = {
        "trip_id", "stop_id", "stop_sequence",
        "arrival_time", "departure_time"
    }

    if not required_trips.issubset(trips.columns):
        raise ValueError(
            f"Missing trip columns: {required_trips - set(trips.columns)}"
        )

    if not required_times.issubset(stop_times.columns):
        raise ValueError(
            f"Missing stop-time columns: {required_times - set(stop_times.columns)}"
        )

    print("Sorting stop times...")

    stop_times["stop_sequence"] = pd.to_numeric(
        stop_times["stop_sequence"],
        errors="coerce"
    )

    stop_times = stop_times.dropna(
        subset=["stop_sequence"]
    )

    stop_times = stop_times.sort_values(
        ["trip_id", "stop_sequence"]
    ).copy()

    # Obtain the next stop within the same trip
    grouped = stop_times.groupby("trip_id", sort=False)

    stop_times["next_stop_id"] = grouped["stop_id"].shift(-1)

    stop_times["next_arrival_time"] = (
        grouped["arrival_time"].shift(-1)
    )

    stop_times["next_stop_sequence"] = (
        grouped["stop_sequence"].shift(-1)
    )

    connections = stop_times.dropna(
        subset=["next_stop_id", "next_arrival_time"]
    ).copy()

    print("Creating consecutive-stop connections...")

    # Add route information
    trip_columns = ["trip_id", "route_id"]

    if "service_id" in trips.columns:
        trip_columns.append("service_id")

    connections = connections.merge(
        trips[trip_columns].drop_duplicates("trip_id"),
        on="trip_id",
        how="inner"
    )

    # Convert scheduled times to seconds
    connections["departure_seconds"] = (
        connections["departure_time"].map(gtfs_to_seconds)
    )

    connections["arrival_seconds"] = (
        connections["next_arrival_time"].map(gtfs_to_seconds)
    )

    connections = connections.dropna(
        subset=["departure_seconds", "arrival_seconds"]
    )

    connections["duration_seconds"] = (
        connections["arrival_seconds"]
        - connections["departure_seconds"]
    )

    # Remove invalid or zero-duration connections
    connections = connections[
        connections["duration_seconds"] > 0
    ].copy()

    # Attach route names
    connections = connections.merge(
        routes[
            ["route_id", "route_short_name", "route_long_name"]
        ],
        on="route_id",
        how="left"
    )

    # Store all scheduled connections
    columns = [
        "trip_id",
        "route_id",
        "route_short_name",
        "route_long_name",
        "stop_id",
        "next_stop_id",
        "departure_time",
        "next_arrival_time",
        "departure_seconds",
        "arrival_seconds",
        "duration_seconds"
    ]

    if "service_id" in connections.columns:
        columns.append("service_id")

    connections[columns].to_csv(
        OUTPUT / "bmtc_connections.csv",
        index=False
    )

    print("Building NetworkX topology...")

    # Compact topology: one edge per unique stop pair.
    # Individual trip schedules remain in bmtc_connections.csv.
    G = nx.DiGraph()

    for _, stop in stops.iterrows():

        G.add_node(
            stop["stop_id"],
            name=stop["stop_name"],
            lat=float(stop["stop_lat"]),
            lon=float(stop["stop_lon"])
        )

    summary = (
        connections.groupby(
            ["stop_id", "next_stop_id"],
            as_index=False
        )
        .agg(
            min_duration=("duration_seconds", "min"),
            trip_count=("trip_id", "nunique"),
            route_count=("route_id", "nunique")
        )
    )

    for row in summary.itertuples(index=False):

        G.add_edge(
            row.stop_id,
            row.next_stop_id,
            weight=row.min_duration,
            trip_count=row.trip_count,
            route_count=row.route_count
        )

    # Save graph statistics
    print("\n========== BMTC GRAPH RESULTS ==========")

    print("Stops (nodes):", G.number_of_nodes())
    print("Unique connections (edges):", G.number_of_edges())
    print("Scheduled connections:", len(connections))
    print("Unique trips:", connections["trip_id"].nunique())
    print("Unique routes:", connections["route_id"].nunique())

    print("\nSample connections:")

    print(
        connections[
            [
                "trip_id",
                "route_short_name",
                "stop_id",
                "next_stop_id",
                "departure_time",
                "next_arrival_time",
                "duration_seconds"
            ]
        ].head(10).to_string(index=False)
    )

    print("\nSaved: data/processed/bmtc_connections.csv")
    print("BMTC graph construction completed!")

    return G


if __name__ == "__main__":
    build_bmtc_graph()
