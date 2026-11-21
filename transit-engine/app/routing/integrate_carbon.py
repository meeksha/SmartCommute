from pathlib import Path

carbon_code = r'''
from pathlib import Path
from functools import lru_cache
import pandas as pd

EMISSION_FACTORS = {
    "private_car_petrol": 162,
    "ride_hailing_diesel": 318,
    "private_scooter_petrol": 74,
    "private_motorcycle_petrol": 65,
    "shared_scooter_petrol": 71,
    "shared_motorcycle_petrol": 62,
    "auto_diesel": 104,
    "auto_cng": 75,
    "auto_electric_ips": 44,
    "bmtc_diesel": 28,
    "bmtc_cng": 31,
    "bmtc_electric_ips": 26,
    "bmtc_electric_net_zero": 24,
    "bmtc_electric_renewable": 6,
    "metro_ips": 24,
    "metro_net_zero": 20,
}

SOURCE = (
    "International Transport Forum / World Bank, "
    "Life-Cycle Assessment of Passenger Transport: "
    "An Indian Case Study (2023)"
)

BMTC_STOP_TIMES = Path("data/raw/bmtc_latest/bmtc_latest.zip")


def calculate_emissions(distance_km, vehicle_type):
    if vehicle_type not in EMISSION_FACTORS:
        raise ValueError(f"Unknown vehicle type: {vehicle_type}")

    distance_km = float(distance_km)

    if distance_km < 0:
        raise ValueError("Distance cannot be negative.")

    factor = EMISSION_FACTORS[vehicle_type]
    emissions = distance_km * factor / 1000

    return {
        "vehicle_type": vehicle_type,
        "distance_km": round(distance_km, 3),
        "emission_factor_g_per_passenger_km": factor,
        "emissions_kg_co2e": round(emissions, 4),
        "source": SOURCE,
        "calculation_basis": "Life-cycle emissions per passenger-km",
        "is_estimate": True,
    }


@lru_cache(maxsize=16)
def get_bmtc_trip_stop_distances(trip_ids):
    import zipfile

    wanted = set(trip_ids)
    found = {}

    with zipfile.ZipFile(BMTC_STOP_TIMES) as archive:
        with archive.open("stop_times.txt") as file:
            for chunk in pd.read_csv(
                file,
                chunksize=300000,
                usecols=[
                    "trip_id",
                    "stop_id",
                    "shape_dist_traveled"
                ],
                dtype={"trip_id": str, "stop_id": str}
            ):
                chunk = chunk[chunk["trip_id"].isin(wanted)]

                for row in chunk.itertuples(index=False):
                    value = pd.to_numeric(
                        row.shape_dist_traveled,
                        errors="coerce"
                    )

                    if pd.notna(value):
                        found[(row.trip_id, row.stop_id)] = float(value)

    return found


def calculate_bmtc_journey_distance(legs):
    trip_ids = tuple(sorted(set(str(x["trip_id"]) for x in legs)))
    distances = get_bmtc_trip_stop_distances(trip_ids)

    leg_details = []
    total_km = 0.0

    for leg in legs:
        trip_id = str(leg["trip_id"])
        origin = str(leg["from_stop"])
        destination = str(leg["to_stop"])

        start = distances.get((trip_id, origin))
        end = distances.get((trip_id, destination))

        if start is None or end is None:
            return {
                "status": "unavailable",
                "message": f"GTFS shape distance missing for trip {trip_id}."
            }

        distance_m = end - start

        if distance_m < 0:
            return {
                "status": "unavailable",
                "message": f"Invalid shape distance for trip {trip_id}."
            }

        distance_km = distance_m / 1000
        total_km += distance_km

        leg_details.append({
            "route": leg.get("route_short_name"),
            "trip_id": trip_id,
            "distance_km": round(distance_km, 3)
        })

    return {
        "status": "success",
        "distance_km": round(total_km, 3),
        "legs": leg_details,
        "distance_basis": "GTFS shape_dist_traveled, metres converted to km"
    }


def calculate_bmtc_emission_scenarios(distance_km):
    scenarios = {}

    for vehicle_type in [
        "bmtc_diesel",
        "bmtc_cng",
        "bmtc_electric_ips"
    ]:
        scenarios[vehicle_type] = calculate_emissions(
            distance_km,
            vehicle_type
        )

    values = [
        item["emissions_kg_co2e"]
        for item in scenarios.values()
    ]

    return {
        "status": "success",
        "distance_km": round(float(distance_km), 3),
        "scenarios": scenarios,
        "minimum_kg_co2e": min(values),
        "maximum_kg_co2e": max(values),
        "fleet_fuel_type_verified": False,
        "note": "Fuel scenarios are alternatives, not a measured BMTC fleet average."
    }
'''

Path("app/services/carbon.py").write_text(
    carbon_code.strip() + "\n",
    encoding="utf-8"
)

path = Path("app/routing/recommendation_engine.py")
content = path.read_text(encoding="utf-8")

import_line = "from app.routing.tomtom_traffic import calculate_road_route"
new_import = import_line + '''
from app.services.carbon import (
    calculate_emissions,
    calculate_bmtc_journey_distance,
    calculate_bmtc_emission_scenarios
)'''

if "calculate_bmtc_journey_distance" not in content:
    if import_line not in content:
        raise SystemExit("TomTom import not found. Recommendation engine unchanged.")
    content = content.replace(import_line, new_import, 1)

# Metro emissions
metro_old = '''            recommendations.append({
                "mode": "Walking + Metro",
                "duration_minutes": metro[
                    "total_estimated_duration_minutes"
                ],
                "distance_walking_m": metro[
                    "total_estimated_walking_metres"
                ],
                "fare": metro.get("metro_fare"),
                "data_type": "Scheduled Metro + modelled walking",
                "details": metro
            })'''

metro_new = '''            metro_distance = metro.get("metro_fare", {}).get("distance_km")

            metro_emissions = (
                calculate_emissions(metro_distance, "metro_ips")
                if metro_distance is not None else None
            )

            recommendations.append({
                "mode": "Walking + Metro",
                "duration_minutes": metro[
                    "total_estimated_duration_minutes"
                ],
                "distance_walking_m": metro[
                    "total_estimated_walking_metres"
                ],
                "fare": metro.get("metro_fare"),
                "emissions": metro_emissions,
                "data_type": "Scheduled Metro + modelled walking",
                "details": metro
            })'''

if metro_old in content:
    content = content.replace(metro_old, metro_new, 1)
elif '"mode": "Walking + Metro"' not in content:
    raise SystemExit("Metro recommendation block not found.")

# BMTC emissions
bmtc_old = '''            bmtc_fare = calculate_bmtc_journey_fare(
                best["bmtc_journey"].get("legs", [])
            )

            recommendations.append({
                "mode": "BMTC Bus",
                "duration_minutes": best[
                    "total_estimated_duration_minutes"
                ],
                "distance_walking_m": (
                    best["origin_access"]["distance_m"]
                    + best["destination_egress"]["distance_m"]
                ),
                "fare": bmtc_fare,
                "data_type": "2026-2027 BMTC scheduled timetable",
                "details": bmtc
            })'''

bmtc_new = '''            bmtc_legs = best["bmtc_journey"].get("legs", [])

            bmtc_fare = calculate_bmtc_journey_fare(bmtc_legs)
            bmtc_distance = calculate_bmtc_journey_distance(bmtc_legs)

            bmtc_emissions = (
                calculate_bmtc_emission_scenarios(
                    bmtc_distance["distance_km"]
                )
                if bmtc_distance.get("status") == "success"
                else bmtc_distance
            )

            recommendations.append({
                "mode": "BMTC Bus",
                "duration_minutes": best[
                    "total_estimated_duration_minutes"
                ],
                "distance_walking_m": (
                    best["origin_access"]["distance_m"]
                    + best["destination_egress"]["distance_m"]
                ),
                "bus_distance_km": bmtc_distance.get("distance_km"),
                "fare": bmtc_fare,
                "emissions": bmtc_emissions,
                "data_type": "2026-2027 BMTC scheduled timetable",
                "details": bmtc
            })'''

if bmtc_old in content:
    content = content.replace(bmtc_old, bmtc_new, 1)
elif '"mode": "BMTC Bus"' not in content:
    raise SystemExit("BMTC recommendation block not found.")

# Road emissions
road_old = '''            recommendations.append({
                "mode": label,
                "duration_minutes": road["traffic_duration_min"],
                "distance_km": road["distance_km"],
                "traffic_delay_minutes": road["traffic_delay_min"],
                "data_type": "TomTom live-traffic routing estimate",
                "details": road
            })'''

road_new = '''            vehicle_type = (
                "private_car_petrol"
                if mode == "car"
                else "ride_hailing_diesel"
            )

            road_emissions = calculate_emissions(
                road["distance_km"],
                vehicle_type
            )

            recommendations.append({
                "mode": label,
                "duration_minutes": road["traffic_duration_min"],
                "distance_km": road["distance_km"],
                "traffic_delay_minutes": road["traffic_delay_min"],
                "emissions": road_emissions,
                "data_type": "TomTom live-traffic routing estimate",
                "details": road
            })'''

if road_old in content:
    content = content.replace(road_old, road_new, 1)
elif '"emissions": road_emissions' not in content:
    raise SystemExit("Road recommendation block not found.")

# Display emissions
print_old = '''        if "distance_walking_m" in option:
            print("Walking:", option["distance_walking_m"], "m")
'''

print_new = '''        if "distance_walking_m" in option:
            print("Walking:", option["distance_walking_m"], "m")

        if option.get("bus_distance_km") is not None:
            print("Bus distance:", option["bus_distance_km"], "km")

        emissions = option.get("emissions")

        if emissions and emissions.get("status") == "success":
            if option["mode"] == "BMTC Bus":
                print("BMTC emissions scenarios:")
                for name, scenario in emissions["scenarios"].items():
                    print(
                        " ", name, ":",
                        scenario["emissions_kg_co2e"], "kg CO2e"
                    )
            else:
                print(
                    "Estimated emissions:",
                    emissions["emissions_kg_co2e"],
                    "kg CO2e/passenger"
                )
'''

if print_old in content:
    content = content.replace(print_old, print_new, 1)

path.write_text(content, encoding="utf-8")
print("Carbon calculations integrated into recommendations.")
