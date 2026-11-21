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
        "status": "success",
        "vehicle_type": vehicle_type,
        "distance_km": round(distance_km, 3),
        "emission_factor_g_per_passenger_km": factor,
        "emissions_kg_co2e": round(emissions, 4),
        "source": SOURCE,
        "calculation_basis": "Life-cycle emissions per passenger-km",
        "is_estimate": True,
    }


SHAPE_DIST_INDEX = Path("data/processed/bmtc_latest/bmtc_shape_dist_index.pkl")


@lru_cache(maxsize=1)
def _shape_distance_index():
    """(trip_id, stop_id) -> shape_dist_traveled, built once and cached on disk.

    The raw stop_times.txt is ~130 MB; scanning it for every candidate journey
    made one recommendation request take minutes.
    """
    if SHAPE_DIST_INDEX.exists():
        return pd.read_pickle(SHAPE_DIST_INDEX)

    import zipfile
    print("Building BMTC shape-distance index (one-time)...", flush=True)
    with zipfile.ZipFile(BMTC_STOP_TIMES) as archive:
        with archive.open("stop_times.txt") as file:
            frame = pd.read_csv(
                file,
                usecols=["trip_id", "stop_id", "shape_dist_traveled"],
                dtype={"trip_id": str, "stop_id": str},
            )
    frame["shape_dist_traveled"] = pd.to_numeric(
        frame["shape_dist_traveled"], errors="coerce"
    )
    frame = frame.dropna(subset=["shape_dist_traveled"])
    frame["shape_dist_traveled"] = frame["shape_dist_traveled"].astype("float32")
    series = frame.drop_duplicates(["trip_id", "stop_id"]).set_index(
        ["trip_id", "stop_id"]
    )["shape_dist_traveled"].sort_index()
    try:
        series.to_pickle(SHAPE_DIST_INDEX)
    except OSError:
        pass
    return series


def get_bmtc_trip_stop_distances(trip_ids):
    index = _shape_distance_index()
    found = {}
    for trip_id in set(trip_ids):
        try:
            sub = index.loc[str(trip_id)]
        except KeyError:
            continue
        for stop_id, value in sub.items():
            found[(str(trip_id), str(stop_id))] = float(value)
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
