"""Efficient shared connection scan for the current BMTC GTFS feed."""
from bisect import bisect_left
from collections import defaultdict


_COLUMN_CACHE = {}


def _column_lists(connections):
    """Extract plain Python lists once per timetable frame (cached by identity)."""
    key = id(connections)
    cached = _COLUMN_CACHE.get(key)
    if cached is not None and cached[0] is connections:
        return cached[1]
    names = ["stop_id", "next_stop_id", "trip_id", "route_id",
             "route_short_name", "route_long_name"]
    cols = {name: connections[name].astype(str).tolist() for name in names}
    cols["departure_seconds"] = connections["departure_seconds"].astype(int).tolist()
    cols["arrival_seconds"] = connections["arrival_seconds"].astype(int).tolist()
    if len(_COLUMN_CACHE) > 8:
        _COLUMN_CACHE.clear()
    _COLUMN_CACHE[key] = (connections, cols)
    return cols


def _reconstruct(node):
    path = []
    while node is not None:
        path.append(node["segment"])
        node = node["previous"]
    path.reverse()
    return path


def scan_bmtc_connections(
    connections,
    origin_candidates,
    transfer_buffer_seconds=300,
    target_stop_ids=None,
    progress_label="Scanning BMTC connections",
    max_journey_seconds=3 * 3600,
):
    """Scan scheduled connections while keeping each path tied to its true origin.

    Labels are stored by (stop, last trip), plus the earliest general label at
    each stop. A linked predecessor chain avoids repeatedly copying full paths.
    """
    labels = defaultdict(dict)
    best_general = {}

    for candidate in origin_candidates:
        stop_id = str(candidate["stop_id"])
        ready = int(candidate["ready_seconds"])
        current = best_general.get(stop_id)
        if current is None or ready < current["arrival"]:
            seed = {
                "arrival": ready,
                "origin_id": stop_id,
                "last_trip_id": None,
                "node": None,
            }
            labels[stop_id][None] = seed
            best_general[stop_id] = seed

    if not labels:
        return {}

    # The timetable loader already sorts this frame. Avoid another full sort.
    if not connections["departure_seconds"].is_monotonic_increasing:
        connections = connections.sort_values(
            ["departure_seconds", "arrival_seconds"]
        )

    cols = _column_lists(connections)
    departures = cols["departure_seconds"]

    # No connection departing before the earliest ready time can be used, and
    # a commute search does not need to look past a bounded horizon.
    earliest_ready = min(int(c["ready_seconds"]) for c in origin_candidates)
    latest_ready = max(int(c["ready_seconds"]) for c in origin_candidates)
    start_index = bisect_left(departures, earliest_ready)
    horizon = latest_ready + int(max_journey_seconds)

    targets = {str(value) for value in (target_stop_ids or [])}
    target_arrivals = {}
    print(
        f"{progress_label}: scanning connections from index {start_index} "
        f"(horizon {horizon // 3600:02d}:{horizon % 3600 // 60:02d}) "
        f"for {len(targets) if targets else 'all'} target stops...",
        flush=True,
    )

    stop_ids = cols["stop_id"]
    next_stop_ids = cols["next_stop_id"]
    trip_ids = cols["trip_id"]
    route_ids = cols["route_id"]
    short_names = cols["route_short_name"]
    long_names = cols["route_long_name"]
    arrivals = cols["arrival_seconds"]

    for index in range(start_index, len(departures)):
        departure = departures[index]
        if departure > horizon:
            break
        from_stop = stop_ids[index]
        states = labels.get(from_stop)
        if not states:
            continue
        to_stop = next_stop_ids[index]
        trip_id = trip_ids[index]
        arrival = arrivals[index]

        # Prefer an already-boarded instance of this exact trip. Otherwise,
        # transfer from the earliest reachable label at this stop.
        base = states.get(trip_id)
        if base is None or base["arrival"] > departure:
            base = best_general.get(from_stop)
            if base is None:
                continue
            required_wait = (
                0 if base["last_trip_id"] is None
                else transfer_buffer_seconds
            )
            if base["arrival"] + required_wait > departure:
                continue

        segment = {
            "trip_id": trip_id,
            "route_id": route_ids[index],
            "route_short_name": short_names[index],
            "route_long_name": long_names[index],
            "from_stop": from_stop,
            "to_stop": to_stop,
            "departure": departure,
            "arrival": arrival,
        }
        node = {"segment": segment, "previous": base["node"]}
        new_label = {
            "arrival": arrival,
            "origin_id": base["origin_id"],
            "last_trip_id": trip_id,
            "node": node,
        }

        old_trip_label = labels[to_stop].get(trip_id)
        if old_trip_label is None or arrival < old_trip_label["arrival"]:
            labels[to_stop][trip_id] = new_label

        old_general = best_general.get(to_stop)
        if old_general is None or arrival < old_general["arrival"]:
            best_general[to_stop] = new_label
            if to_stop in targets:
                target_arrivals[to_stop] = arrival

        # Connections are ordered by departure. Once every requested target
        # has a journey arriving no later than the next departure, no later
        # connection can improve any target (arrival cannot precede departure).
        # This is a safe termination condition, unlike stopping on first reach.
        if targets and len(target_arrivals) == len(targets):
            if all(value <= departure for value in target_arrivals.values()):
                break

    return {stop: dict(states) for stop, states in labels.items()}


def earliest_label(labels_by_stop, stop_id):
    """Return the earliest non-empty journey label for a stop, with its path."""
    states = labels_by_stop.get(str(stop_id), {})
    usable = [
        label for label in states.values()
        if label.get("node") is not None
    ]
    if not usable:
        return None
    best = min(usable, key=lambda item: item["arrival"])
    return {
        "arrival": best["arrival"],
        "origin_id": best["origin_id"],
        "last_trip_id": best["last_trip_id"],
        "path": _reconstruct(best["node"]),
    }
