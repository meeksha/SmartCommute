def estimate_auto_fare(
    distance_km,
    waiting_minutes=0,
    pickup_fee_inr=0
):
    """
    Provisional Namma Yatri Bengaluru Auto fare reference.
    Reported August 2026:
    Rs. 40 for first 2 km, then Rs. 19/km.
    Waiting charge: Rs. 1.50/min after first 3 minutes.
    """

    if distance_km <= 0:
        raise ValueError("Distance must be greater than zero.")

    if waiting_minutes < 0 or pickup_fee_inr < 0:
        raise ValueError("Waiting and pickup fee cannot be negative.")

    distance_fare = (
        40 if distance_km <= 2
        else 40 + (distance_km - 2) * 19
    )

    waiting_charge = max(0, waiting_minutes - 3) * 1.50

    total = distance_fare + waiting_charge + pickup_fee_inr

    return {
        "status": "success",
        "mode": "Auto",
        "distance_km": distance_km,
        "distance_fare_inr": round(distance_fare, 2),
        "waiting_charge_inr": round(waiting_charge, 2),
        "pickup_fee_inr": round(pickup_fee_inr, 2),
        "estimated_total_inr": round(total, 2),
        "source": "Reported Namma Yatri Bengaluru pricing, August 2026",
        "is_estimate": True
    }


CAB_RATES = {
    "up_to_10_lakh": {
        "base_fare": 100,
        "included_distance_km": 4,
        "additional_per_km": 24
    },
    "10_to_15_lakh": {
        "base_fare": 115,
        "included_distance_km": 4,
        "additional_per_km": 28
    },
    "above_15_lakh": {
        "base_fare": 130,
        "included_distance_km": 4,
        "additional_per_km": 32
    }
}


def estimate_cab_fare(
    distance_km,
    vehicle_cost_category,
    waiting_minutes=0,
    pickup_fee_inr=0,
    is_night=False
):
    """
    Karnataka notified cab fare reference, reported September 2026.
    This is NOT a Namma Yatri-specific fare chart.
    """

    if distance_km <= 0:
        raise ValueError("Distance must be greater than zero.")

    if waiting_minutes < 0 or pickup_fee_inr < 0:
        raise ValueError("Waiting and pickup fee cannot be negative.")

    if vehicle_cost_category not in CAB_RATES:
        raise ValueError(
            "Choose one of: " + ", ".join(CAB_RATES.keys())
        )

    rate = CAB_RATES[vehicle_cost_category]

    extra_distance = max(
        0, distance_km - rate["included_distance_km"]
    )

    distance_fare = (
        rate["base_fare"]
        + extra_distance * rate["additional_per_km"]
    )

    waiting_charge = waiting_minutes * 1.0
    night_charge = 0.10 * distance_fare if is_night else 0

    total = (
        distance_fare
        + waiting_charge
        + night_charge
        + pickup_fee_inr
    )

    return {
        "status": "success",
        "mode": "Cab",
        "distance_km": distance_km,
        "vehicle_cost_category": vehicle_cost_category,
        "distance_fare_inr": round(distance_fare, 2),
        "waiting_charge_inr": round(waiting_charge, 2),
        "night_charge_inr": round(night_charge, 2),
        "pickup_fee_inr": round(pickup_fee_inr, 2),
        "estimated_total_inr": round(total, 2),
        "source": "Karnataka notified cab rates, reported September 2026",
        "is_estimate": True
    }


if __name__ == "__main__":
    print("AUTO TEST")
    print(estimate_auto_fare(8))

    print("\nCAB TEST")
    print(estimate_cab_fare(8, "up_to_10_lakh"))

    print("\nNIGHT CAB TEST")
    print(estimate_cab_fare(8, "10_to_15_lakh", is_night=True))
