"""Employee-aware carpool candidate matching.

This is a first-stage matching engine. It ranks compatible driver/rider pairs
using proximity, departure-time difference, destination proximity and
estimated detour. It does not claim seat booking or driver availability.
"""
from math import radians, sin, cos, asin, sqrt


def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0088
    dlat = radians(float(lat2) - float(lat1))
    dlon = radians(float(lon2) - float(lon1))
    a = sin(dlat / 2) ** 2 + cos(radians(float(lat1))) * cos(radians(float(lat2))) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def _minutes(value):
    if isinstance(value, (int, float)):
        return int(value)
    parts = str(value).split(":")
    if len(parts) < 2:
        raise ValueError("departure_time must be minutes or HH:MM")
    return int(parts[0]) * 60 + int(parts[1])


def match_employees(
    employees,
    max_origin_distance_km=3.0,
    max_destination_distance_km=3.0,
    max_departure_difference_minutes=30,
    max_detour_km=5.0,
    max_detour_ratio=0.35,
):
    """Return ranked potential driver/rider matches.

    Expected employee fields:
      employee_id, origin_lat, origin_lon, destination_lat, destination_lon,
      departure_time ('HH:MM' or minutes since midnight), role ('driver'/'rider'),
      available_seats for drivers.
    """
    if max_origin_distance_km < 0 or max_destination_distance_km < 0:
        raise ValueError("Distance thresholds cannot be negative")
    if max_departure_difference_minutes < 0 or max_detour_km < 0:
        raise ValueError("Time/detour thresholds cannot be negative")

    drivers = [e for e in employees if e.get("role") == "driver"]
    riders = [e for e in employees if e.get("role") == "rider"]
    matches = []

    for driver in drivers:
        seats = int(driver.get("available_seats", 0))
        if seats <= 0:
            continue
        driver_direct = haversine_km(
            driver["origin_lat"], driver["origin_lon"],
            driver["destination_lat"], driver["destination_lon"]
        )
        for rider in riders:
            if driver["employee_id"] == rider["employee_id"]:
                continue
            origin_gap = haversine_km(
                driver["origin_lat"], driver["origin_lon"],
                rider["origin_lat"], rider["origin_lon"]
            )
            destination_gap = haversine_km(
                driver["destination_lat"], driver["destination_lon"],
                rider["destination_lat"], rider["destination_lon"]
            )
            time_gap = abs(
                _minutes(driver["departure_time"]) -
                _minutes(rider["departure_time"])
            )
            # Approximate pickup + drop-off detour using straight-line distances.
            detour = origin_gap + destination_gap
            detour_ratio = detour / max(driver_direct, 0.1)

            if origin_gap > max_origin_distance_km:
                continue
            if destination_gap > max_destination_distance_km:
                continue
            if time_gap > max_departure_difference_minutes:
                continue
            if detour > max_detour_km or detour_ratio > max_detour_ratio:
                continue

            # Lower score is better; transparent components retained.
            score = (
                0.35 * (origin_gap / max(max_origin_distance_km, 0.1)) +
                0.20 * (destination_gap / max(max_destination_distance_km, 0.1)) +
                0.20 * (time_gap / max(max_departure_difference_minutes, 1)) +
                0.25 * (detour_ratio / max(max_detour_ratio, 0.01))
            )
            matches.append({
                "driver_employee_id": driver["employee_id"],
                "rider_employee_id": rider["employee_id"],
                "origin_gap_km": round(origin_gap, 3),
                "destination_gap_km": round(destination_gap, 3),
                "departure_difference_minutes": time_gap,
                "estimated_detour_km": round(detour, 3),
                "estimated_detour_ratio": round(detour_ratio, 4),
                "available_seats_reported": seats,
                "matching_score": round(score, 4),
                "matching_status": "potential_match_requires_confirmation",
                "limitations": [
                    "Straight-line proximity is a screening proxy, not road-network distance.",
                    "No live driver availability or booking is performed.",
                    "Seat count is user-reported and must be confirmed."
                ]
            })

    return sorted(matches, key=lambda item: item["matching_score"])
