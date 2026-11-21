"""Scheduled BMTC + Metro + BMTC journey composition.

This is an opt-in orchestration layer. Existing planners are left unchanged.
It uses the existing BMTC GPS planner and Metro timetable planner and applies
conservative walking/transfer limits before returning a combined itinerary.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from app.routing.bmtc_latest_planner import (
    plan_bmtc_latest_from_gps, _cached_bmtc_result,
)
from app.routing.metro_planner import plan_metro

DEFAULT_LIMITS = {
    "origin_access_m": 1200,
    "feeder_egress_m": 1800,
    "metro_to_feeder_access_m": 1200,
    "destination_egress_m": 1800,
    "minimum_transfer_minutes": 5,
}


def _clock(value: str) -> datetime:
    value = str(value)
    fmt = "%H:%M:%S" if len(value.split(":")) == 3 else "%H:%M"
    return datetime.strptime(value, fmt)


def _plus_minutes(value: str, minutes: float) -> str:
    # Round up to the next whole minute so the next timetable search never
    # boards before the passenger can physically reach the platform/stop.
    import math
    result = _clock(value) + timedelta(minutes=math.ceil(float(minutes)))
    return result.strftime("%H:%M")


def _bmtc_best(result: dict) -> dict | None:
    if not isinstance(result, dict) or result.get("status") != "success":
        return None
    return result.get("best_journey")


def _walk_m(section: dict | None) -> float:
    if not section:
        return float("inf")
    return float(section.get("distance_m", float("inf")))


def plan_bmtc_metro_bmtc(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    travel_date: str,
    departure_time: str,
    metro_origin_station: str,
    metro_origin_lat: float,
    metro_origin_lon: float,
    metro_destination_station: str,
    metro_destination_lat: float,
    metro_destination_lon: float,
    *,
    limits: dict | None = None,
    bmtc_planner: Callable = plan_bmtc_latest_from_gps,
    metro_planner: Callable = plan_metro,
) -> dict:
    """Compose scheduled BMTC feeder, Metro, and BMTC feeder legs.

    Metro station names and coordinates must refer to the same physical
    stations/entrances. Coordinates are used by BMTC feeder searches; station
    names are used by the Metro timetable planner.
    """
    active = {**DEFAULT_LIMITS, **(limits or {})}
    coords = [origin_lat, origin_lon, destination_lat, destination_lon,
              metro_origin_lat, metro_origin_lon,
              metro_destination_lat, metro_destination_lon]
    if any(value is None for value in coords):
        raise ValueError("All origin, destination, and Metro coordinates are required")
    if not metro_origin_station or not metro_destination_station:
        raise ValueError("Both Metro station names are required")

    # Feeder 1: employee origin -> Metro origin station.
    first_result = bmtc_planner(
        origin_lat, origin_lon, metro_origin_lat, metro_origin_lon,
        travel_date, departure_time,
    )
    first = _bmtc_best(first_result)
    if first is None:
        return {"status": "unavailable", "stage": "origin_feeder",
                "message": first_result.get("message", "No BMTC feeder found"),
                "details": first_result}
    first_access = first.get("origin_access", {})
    first_egress = first.get("destination_egress", {})
    if _walk_m(first_access) > active["origin_access_m"]:
        return {"status": "rejected", "stage": "origin_feeder",
                "message": "Origin walk to the first BMTC stop exceeds the configured limit"}
    if _walk_m(first_egress) > active["feeder_egress_m"]:
        return {"status": "rejected", "stage": "origin_feeder",
                "message": "Walk from the first BMTC feeder to Metro exceeds the configured limit"}

    first_bmtc = first.get("bmtc_journey", {})
    # Include the walk from the first feeder stop to the Metro entrance,
    # then add the interchange buffer.
    first_egress_walk = float(first_egress.get("walking_minutes", 0) or 0)
    metro_ready = _plus_minutes(
        first_bmtc.get("arrival", departure_time),
        first_egress_walk + active["minimum_transfer_minutes"],
    )

    # Metro: next scheduled train after the first feeder reaches the station.
    metro = metro_planner(
        metro_origin_station, metro_destination_station,
        travel_date, metro_ready,
    )
    if not isinstance(metro, dict) or metro.get("status") != "success":
        return {"status": "unavailable", "stage": "metro",
                "message": (metro or {}).get("message", "No scheduled Metro journey"),
                "details": metro}

    # Feeder 2: Metro destination station -> employee destination.
    second_ready = _plus_minutes(
        metro.get("arrival", metro_ready), active["minimum_transfer_minutes"]
    )
    second_result = bmtc_planner(
        metro_destination_lat, metro_destination_lon,
        destination_lat, destination_lon,
        travel_date, second_ready,
    )
    second = _bmtc_best(second_result)
    if second is None:
        return {"status": "unavailable", "stage": "destination_feeder",
                "message": second_result.get("message", "No destination BMTC feeder found"),
                "details": second_result}
    second_access = second.get("origin_access", {})
    second_egress = second.get("destination_egress", {})
    if _walk_m(second_access) > active["metro_to_feeder_access_m"]:
        return {"status": "rejected", "stage": "destination_feeder",
                "message": "Walk from Metro to the second BMTC boarding stop exceeds the configured limit"}
    if _walk_m(second_egress) > active["destination_egress_m"]:
        return {"status": "rejected", "stage": "destination_feeder",
                "message": "Final walk from BMTC to destination exceeds the configured limit"}

    final_bus_arrival = second.get("bmtc_journey", {}).get("arrival")
    if not final_bus_arrival:
        return {"status": "unavailable", "stage": "destination_feeder",
                "message": "Destination feeder did not provide a final arrival time"}
    start_dt = datetime.strptime(f"{travel_date} {departure_time}", "%Y-%m-%d %H:%M")
    end_dt = datetime.strptime(f"{travel_date} {final_bus_arrival}", "%Y-%m-%d %H:%M:%S" if len(final_bus_arrival.split(":")) == 3 else "%Y-%m-%d %H:%M")
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    # Final walking egress is part of the door-to-door journey duration.
    end_dt += timedelta(minutes=float(second_egress.get("walking_minutes", 0) or 0))
    final_arrival = end_dt.strftime("%H:%M:%S")

    return {
        "status": "success",
        "journey_type": "BMTC + Metro + BMTC",
        "travel_date": travel_date,
        "departure": departure_time,
        "arrival": final_arrival,
        "total_duration_minutes": round((end_dt - start_dt).total_seconds() / 60, 1),
        "legs": [
            {"mode": "BMTC feeder", "from": "Origin", "to": metro_origin_station,
             "journey": first},
            {"mode": "Metro", "from": metro_origin_station,
             "to": metro_destination_station, "journey": metro},
            {"mode": "BMTC feeder", "from": metro_destination_station,
             "to": "Destination", "journey": second},
        ],
        "walking_m": round(sum(_walk_m(section) for section in
            (first_access, first_egress, second_access, second_egress)), 1),
        "transfer_buffer_minutes": active["minimum_transfer_minutes"],
        "data_warnings": [
            "BMTC and Metro legs use scheduled GTFS data, not live vehicle positions.",
            "BMTC access/egress distances inherit the existing planner's straight-line distance approximation.",
            "Metro station coordinates must represent practical BMTC boarding/alighting points near the station.",
            "This module is opt-in and is not yet connected to the main recommendation pipeline.",
        ],
    }


def get_bmtc_feeder_cache_info():
    """Expose cache statistics while evaluating dynamically discovered station pairs."""
    return _cached_bmtc_result.cache_info()._asdict()
