DEFAULT_PETROL_PRICE_INR_PER_LITRE = 110.44

# Illustrative default. Change this to the actual vehicle mileage.
DEFAULT_MILEAGE_KM_PER_LITRE = 45.0


def calculate_two_wheeler_fuel_cost(
    distance_km,
    mileage_km_per_litre=DEFAULT_MILEAGE_KM_PER_LITRE,
    petrol_price_inr=DEFAULT_PETROL_PRICE_INR_PER_LITRE
):
    """
    Estimate private two-wheeler petrol consumption and fuel cost.

    Maintenance, insurance and depreciation are excluded.
    """

    distance_km = float(distance_km)
    mileage_km_per_litre = float(mileage_km_per_litre)
    petrol_price_inr = float(petrol_price_inr)

    if distance_km <= 0:
        raise ValueError("Distance must be greater than zero.")

    if mileage_km_per_litre <= 0:
        raise ValueError("Mileage must be greater than zero.")

    if petrol_price_inr <= 0:
        raise ValueError("Petrol price must be greater than zero.")

    fuel_consumed_litres = distance_km / mileage_km_per_litre
    fuel_cost = fuel_consumed_litres * petrol_price_inr

    return {
        "status": "success",
        "vehicle_type": "Private petrol two-wheeler",
        "distance_km": round(distance_km, 2),
        "assumed_mileage_km_per_litre": mileage_km_per_litre,
        "petrol_price_inr_per_litre": petrol_price_inr,
        "fuel_consumed_litres": round(fuel_consumed_litres, 3),
        "fuel_cost_inr": round(fuel_cost, 2),
        "cost_scope": "Petrol only",
        "is_estimate": True
    }


if __name__ == "__main__":
    print("TWO-WHEELER FUEL COST TEST")
    print("==========================")

    for distance in [5, 10, 15, 20]:
        result = calculate_two_wheeler_fuel_cost(distance)

        print(
            f"{distance} km: "
            f"Fuel = {result['fuel_consumed_litres']} L, "
            f"Cost = Rs. {result['fuel_cost_inr']}"
        )

    print("\nCUSTOM VEHICLE TEST")
    print(
        calculate_two_wheeler_fuel_cost(
            distance_km=10,
            mileage_km_per_litre=55,
            petrol_price_inr=110.44
        )
    )
