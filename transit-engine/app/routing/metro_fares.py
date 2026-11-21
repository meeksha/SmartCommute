from pathlib import Path
from functools import lru_cache
import pandas as pd


METRO_DATA = Path("data/raw/metro/standard")


@lru_cache(maxsize=1)
def load_metro_stop_times():
    files = list(METRO_DATA.rglob("stop_times.txt"))

    if not files:
        raise FileNotFoundError("Metro stop_times.txt not found.")

    df = pd.read_csv(files[0])

    df["shape_dist_traveled"] = pd.to_numeric(
        df["shape_dist_traveled"], errors="coerce"
    )

    return df


def calculate_metro_distance(legs):
    stop_times = load_metro_stop_times()
    total_distance = 0.0
    details = []

    for leg in legs:
        trip_id = str(leg["trip_id"])
        from_stop = str(leg["from_stop"])
        to_stop = str(leg["to_stop"])

        rows = stop_times[
            stop_times["trip_id"].astype(str) == trip_id
        ]

        origin = rows[rows["stop_id"].astype(str) == from_stop]
        destination = rows[
            rows["stop_id"].astype(str) == to_stop
        ]

        if origin.empty or destination.empty:
            return {
                "status": "unavailable",
                "message": f"Could not match Metro distance for trip {trip_id}."
            }

        start_distance = origin.iloc[0]["shape_dist_traveled"]
        end_distance = destination.iloc[0]["shape_dist_traveled"]

        if pd.isna(start_distance) or pd.isna(end_distance):
            return {
                "status": "unavailable",
                "message": f"Missing track distance for trip {trip_id}."
            }

        distance = float(end_distance - start_distance)

        if distance < 0:
            return {
                "status": "unavailable",
                "message": f"Invalid track distance for trip {trip_id}."
            }

        total_distance += distance

        details.append({
            "trip_id": trip_id,
            "from_stop": from_stop,
            "to_stop": to_stop,
            "distance_km": round(distance, 3)
        })

    return {
        "status": "success",
        "distance_km": round(total_distance, 3),
        "legs": details
    }


# BMRCL fare slabs in force since 9 February 2025 (minimum Rs 10, maximum
# Rs 90). Smart cards get 5 % off at all times and 10 % off-peak (opening-8am,
# 12-4pm, 9pm-close) and on Sundays. Per-station-pair caps that BMRCL applied
# after the February 2025 review are not modelled, so a few pairs may be
# priced one slab high. Previously this used an older chart capped at Rs 60.
METRO_FARE_SLABS = [
    (2, 10), (4, 20), (6, 30), (8, 40), (10, 50),
    (15, 60), (20, 70), (25, 80), (30, 90), (float("inf"), 90),
]
METRO_FARE_SOURCE = "BMRCL fare slabs effective 9 Feb 2025 (Rs 10-90); smart card 5 % (10 % off-peak)"


def estimate_metro_fare(distance_km, off_peak=False):
    for upper_limit, token_fare in METRO_FARE_SLABS:
        if distance_km <= upper_limit:
            discount = 0.10 if off_peak else 0.05
            return {
                "distance_km": round(distance_km, 3),
                "token_fare_inr": token_fare,
                "smart_card_qr_fare_inr": round(token_fare * (1 - discount), 2),
                "fare_basis": METRO_FARE_SOURCE,
                "is_estimate": True
            }


def calculate_metro_journey_fare(legs):
    distance_result = calculate_metro_distance(legs)

    if distance_result["status"] != "success":
        return distance_result

    fare = estimate_metro_fare(distance_result["distance_km"])

    return {
        "status": "success",
        **fare,
        "leg_distances": distance_result["legs"]
    }


if __name__ == "__main__":
    test_legs = [{
        "trip_id": "t2549",
        "from_stop": "KRMT_PF1",
        "to_stop": "SSFY_PF1"
    }]

    result = calculate_metro_journey_fare(test_legs)

    print("\nMETRO FARE TEST")
    print("================")
    for key, value in result.items():
        print(f"{key}: {value}")
