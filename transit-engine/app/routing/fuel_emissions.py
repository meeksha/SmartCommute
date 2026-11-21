"""Fuel cost and tailpipe-emissions calculations for road journeys.

Fuel prices affect cost, not emissions. Emissions are calculated from fuel
consumption and a fuel-specific combustion factor. Factors here are defaults
for approximate direct tailpipe CO2 only; replace/configure them from a
documented source before production use.
"""
from datetime import datetime, timezone

DEFAULT_EMISSION_FACTORS_KG_CO2_PER_LITRE = {
    "petrol": 2.31,
    "diesel": 2.68,
}


def calculate_vehicle_fuel_metrics(
    distance_km,
    mileage_km_per_litre,
    fuel_type,
    fuel_price_inr_per_litre=None,
    price_source=None,
    price_timestamp=None,
    emission_factor_kg_co2_per_litre=None,
):
    distance = float(distance_km)
    mileage = float(mileage_km_per_litre)
    fuel = str(fuel_type).strip().lower()

    if distance <= 0:
        raise ValueError("distance_km must be greater than zero")
    if mileage <= 0:
        raise ValueError("mileage_km_per_litre must be greater than zero")
    if fuel not in DEFAULT_EMISSION_FACTORS_KG_CO2_PER_LITRE:
        raise ValueError("fuel_type must be 'petrol' or 'diesel'")

    litres = distance / mileage
    factor = (
        float(emission_factor_kg_co2_per_litre)
        if emission_factor_kg_co2_per_litre is not None
        else DEFAULT_EMISSION_FACTORS_KG_CO2_PER_LITRE[fuel]
    )
    if factor <= 0:
        raise ValueError("Emission factor must be greater than zero")

    cost = None
    if fuel_price_inr_per_litre is not None:
        price = float(fuel_price_inr_per_litre)
        if price <= 0:
            raise ValueError("Fuel price must be greater than zero")
        cost = round(litres * price, 2)

    return {
        "status": "success",
        "distance_km": round(distance, 3),
        "fuel_type": fuel,
        "assumed_mileage_km_per_litre": mileage,
        "estimated_fuel_consumed_litres": round(litres, 4),
        "fuel_price_inr_per_litre": (
            float(fuel_price_inr_per_litre)
            if fuel_price_inr_per_litre is not None else None
        ),
        "estimated_fuel_cost_inr": cost,
        "fuel_price_source": price_source,
        "fuel_price_timestamp": price_timestamp,
        "emission_factor_kg_co2_per_litre": factor,
        "estimated_tailpipe_co2_kg": round(litres * factor, 4),
        "emissions_scope": "direct fuel-combustion CO2; excludes upstream fuel lifecycle",
        "is_estimate": True,
    }


def allocate_shared_trip_metrics(vehicle_metrics, passenger_count):
    """Allocate one vehicle's trip metrics equally across occupants."""
    count = int(passenger_count)
    if count < 1:
        raise ValueError("passenger_count must be at least 1")
    result = dict(vehicle_metrics)
    result["occupant_count"] = count
    result["cost_per_occupant_inr"] = (
        round(vehicle_metrics["estimated_fuel_cost_inr"] / count, 2)
        if vehicle_metrics.get("estimated_fuel_cost_inr") is not None else None
    )
    result["tailpipe_co2_kg_per_occupant"] = round(
        vehicle_metrics["estimated_tailpipe_co2_kg"] / count, 4
    )
    result["allocation_method"] = "equal split across driver and passengers"
    return result
