from app.routing.journey_schema import build_journey


def _tag_legs(legs, transport_type):
    """Preserve planner fields and expose common, frontend-friendly names."""
    tagged = []
    for leg in legs or []:
        item = {"type": transport_type, **leg}
        if transport_type == "bmtc_bus":
            item["route_number"] = leg.get("route_short_name")
            item["boarding_stop"] = leg.get("from_stop_name")
            item["alighting_stop"] = leg.get("to_stop_name")
            item["from_stop_id"] = leg.get("from_stop")
            item["to_stop_id"] = leg.get("to_stop")
        elif transport_type == "metro":
            item["boarding_station"] = leg.get("from_station")
            item["alighting_station"] = leg.get("to_station")
            item["line"] = leg.get("route_id")
            item["direction"] = leg.get("headsign")
            item["from_stop_id"] = leg.get("from_stop")
            item["to_stop_id"] = leg.get("to_stop")
        tagged.append(item)
    return tagged


def _bus_path_is_contiguous(bus_legs, origin_access=None, destination_egress=None):
    if not bus_legs:
        return False
    if origin_access and origin_access.get("stop_id"):
        if str(origin_access["stop_id"]) != str(bus_legs[0].get("from_stop")):
            return False
    for previous, current in zip(bus_legs, bus_legs[1:]):
        if str(previous.get("to_stop")) != str(current.get("from_stop")):
            return False
    if destination_egress and destination_egress.get("stop_id"):
        if str(destination_egress["stop_id"]) != str(bus_legs[-1].get("to_stop")):
            return False
    return True


def adapt_walking_metro(result):
    """Convert valid walking + Metro planner output, rejecting zero-train paths."""
    if result.get("status") != "success":
        return []

    candidates = []
    if result.get("best_journey"):
        candidates.append(result["best_journey"])
    elif result.get("metro_journey"):
        candidates.append(result)

    candidates.extend(result.get("alternative_journeys", []))
    journeys = []

    for candidate in candidates:
        metro = candidate.get("metro_journey", {})
        metro_legs = metro.get("legs", [])
        if metro.get("status") not in (None, "success") or not metro_legs:
            continue

        origin = candidate.get("origin_metro", {})
        destination = candidate.get("destination_metro", {})
        legs = [{
            "type": "walking",
            "segment": "origin_access",
            "from": "Origin",
            "to": origin.get("station_name"),
            "distance_m": origin.get("walking_distance_m"),
            "duration_minutes": origin.get("walking_minutes"),
            "details": origin,
        }]
        legs.extend(_tag_legs(metro_legs, "metro"))
        legs.append({
            "type": "walking",
            "segment": "destination_egress",
            "from": destination.get("station_name"),
            "to": "Destination",
            "distance_m": destination.get("walking_distance_m"),
            "duration_minutes": destination.get("walking_minutes"),
            "details": destination,
        })

        journeys.append(build_journey(
            mode="Walking + Metro",
            duration_minutes=candidate.get("total_estimated_duration_minutes"),
            legs=legs,
            walking_distance_m=candidate.get("total_estimated_walking_metres"),
            fare=candidate.get("metro_fare"),
            transfers=max(0, len(metro_legs) - 1),
            data_sources=["OSM walking network", "Metro GTFS"],
            limitations=candidate.get("limitations", result.get("limitations", [])),
            raw_details=candidate,
        ))
    return journeys


def adapt_bmtc_journeys(result, fares=None, emissions=None):
    """Convert BMTC alternatives, retaining only physically continuous paths."""
    if result.get("status") != "success":
        return []

    candidates = []
    if result.get("best_journey"):
        candidates.append(result["best_journey"])
    candidates.extend(result.get("alternative_journeys", []))

    journeys = []
    for index, candidate in enumerate(candidates):
        bus = candidate.get("bmtc_journey", {})
        bus_legs = bus.get("legs", [])
        origin_access = candidate.get("origin_access", {})
        destination_egress = candidate.get("destination_egress", {})

        if not _bus_path_is_contiguous(
            bus_legs, origin_access, destination_egress
        ):
            continue

        legs = [{
            "type": "walking",
            "segment": "origin_access",
            "from": "Origin",
            "to": origin_access.get("stop_name"),
            "distance_m": origin_access.get("distance_m"),
            "duration_minutes": origin_access.get("walking_minutes"),
            "details": origin_access,
        }]
        legs.extend(_tag_legs(bus_legs, "bmtc_bus"))
        legs.append({
            "type": "walking",
            "segment": "destination_egress",
            "from": destination_egress.get("stop_name"),
            "to": "Destination",
            "distance_m": destination_egress.get("distance_m"),
            "duration_minutes": destination_egress.get("walking_minutes"),
            "details": destination_egress,
        })

        walking_distance = (
            float(origin_access.get("distance_m") or 0)
            + float(destination_egress.get("distance_m") or 0)
        )
        journeys.append(build_journey(
            mode="BMTC Bus",
            duration_minutes=candidate.get("total_estimated_duration_minutes"),
            legs=legs,
            walking_distance_m=round(walking_distance, 1),
            fare=fares[index] if fares and index < len(fares) else None,
            emissions=emissions[index] if emissions and index < len(emissions) else None,
            transfers=max(0, len(bus_legs) - 1),
            data_sources=["BMTC GTFS"],
            limitations=[
                "Scheduled BMTC timetable; no live bus positions."
            ],
            raw_details=candidate,
        ))
    return journeys


def adapt_bmtc_metro_journeys(result):
    """Convert BMTC + Metro options after checking all interchange endpoints."""
    if result.get("status") != "success":
        return []

    candidates = []
    if result.get("best_journey"):
        candidates.append(result["best_journey"])
    candidates.extend(result.get("alternative_journeys", []))

    journeys = []
    for candidate in candidates:
        bmtc = candidate.get("bmtc_journey", {})
        metro = candidate.get("metro_journey", {})
        bus_legs = bmtc.get("legs", [])
        metro_legs = metro.get("legs", [])
        origin_access = candidate.get("origin_access", {})
        interchange = candidate.get("interchange", {})
        destination_metro = candidate.get("destination_metro", {})

        if not _bus_path_is_contiguous(bus_legs, origin_access):
            continue
        if not metro_legs:
            continue
        if str(bus_legs[-1].get("to_stop")) != str(interchange.get("bmtc_stop_id")):
            continue
        if str(metro_legs[0].get("from_station")) != str(interchange.get("metro_station_name")):
            continue

        total_walking = candidate.get("total_estimated_walking_metres")
        interchange_walking = interchange.get("walking_distance_m")
        destination_walking = destination_metro.get("walking_distance_m")
        origin_walking = origin_access.get("distance_m")
        if origin_walking is None and all(
            value is not None for value in (
                total_walking, interchange_walking, destination_walking
            )
        ):
            origin_walking = round(
                float(total_walking)
                - float(interchange_walking)
                - float(destination_walking), 1
            )
        if origin_walking is None or origin_walking < 0:
            continue

        legs = [{
            "type": "walking",
            "segment": "origin_access",
            "from": "Origin",
            "to": origin_access.get("stop_name"),
            "distance_m": origin_walking,
            "duration_minutes": origin_access.get("walking_minutes"),
            "details": origin_access or {
                "source": "Derived from planner walking-distance total"
            },
        }]
        legs.extend(_tag_legs(bus_legs, "bmtc_bus"))
        legs.append({
            "type": "walking",
            "segment": "bmtc_metro_interchange",
            "from": interchange.get("bmtc_stop_name"),
            "to": interchange.get("metro_station_name"),
            "distance_m": interchange_walking,
            "duration_minutes": interchange.get("walking_minutes"),
            "details": interchange,
        })
        legs.extend(_tag_legs(metro_legs, "metro"))
        legs.append({
            "type": "walking",
            "segment": "destination_egress",
            "from": destination_metro.get("station_name"),
            "to": "Destination",
            "distance_m": destination_walking,
            "duration_minutes": destination_metro.get("walking_minutes"),
            "details": destination_metro,
        })

        journeys.append(build_journey(
            mode="BMTC + Metro",
            duration_minutes=candidate.get("total_estimated_duration_minutes"),
            legs=legs,
            walking_distance_m=total_walking,
            fare=candidate.get("fare"),
            emissions=candidate.get("emissions"),
            transfers=(
                max(0, len(bus_legs) - 1) + 1 + max(0, len(metro_legs) - 1)
            ),
            data_sources=[
                "BMTC GTFS", "Metro GTFS", "OSM walking network"
            ],
            limitations=[
                candidate.get("data_warning", ""),
                *result.get("limitations", []),
            ],
            raw_details=candidate,
        ))
    return journeys
