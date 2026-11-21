"""Carpool recommendation orchestration over employee commute profiles.

This module connects employee matching with the fuel/emissions calculator.
It returns potential matches only; no booking or live driver availability.
"""
from app.routing.carpool_matching import match_employees
from app.routing.fuel_emissions import (
    calculate_vehicle_fuel_metrics,
    allocate_shared_trip_metrics,
)


def build_carpool_recommendations(
    employee_profiles,
    vehicle_profiles,
    fuel_prices=None,
    matching_limits=None,
):
    """Create potential carpool recommendations with estimated trip economics.

    vehicle_profiles is keyed by driver employee_id, e.g.:
      {
        "EMP001": {
          "distance_km": 18.4,
          "mileage_km_per_litre": 15,
          "fuel_type": "petrol"
        }
      }

    fuel_prices is keyed by driver employee_id and may contain:
      {"price_inr_per_litre": 105.0, "source": "...", "timestamp": "..."}
    A missing price produces emissions but leaves cost as None.
    """
    matches = match_employees(employee_profiles, **(matching_limits or {}))
    vehicle_profiles = vehicle_profiles or {}
    fuel_prices = fuel_prices or {}
    results = []

    for match in matches:
        driver_id = match["driver_employee_id"]
        vehicle = vehicle_profiles.get(driver_id)
        if not vehicle:
            match = dict(match)
            match["fuel_metrics"] = None
            match["cost_status"] = "vehicle_profile_missing"
            match["limitations"] = list(match.get("limitations", [])) + [
                "Vehicle fuel/mileage profile was not supplied; cost and emissions are unavailable."
            ]
            results.append(match)
            continue

        price = fuel_prices.get(driver_id, {})
        metrics = calculate_vehicle_fuel_metrics(
            distance_km=vehicle["distance_km"],
            mileage_km_per_litre=vehicle["mileage_km_per_litre"],
            fuel_type=vehicle["fuel_type"],
            fuel_price_inr_per_litre=price.get("price_inr_per_litre"),
            price_source=price.get("source"),
            price_timestamp=price.get("timestamp"),
            emission_factor_kg_co2_per_litre=vehicle.get(
                "emission_factor_kg_co2_per_litre"
            ),
        )

        # Split vehicle-trip cost and tailpipe CO2 among driver + matched riders.
        # The matching engine returns one driver/rider pair per result.
        metrics_per_occupant = allocate_shared_trip_metrics(metrics, passenger_count=2)

        enriched = dict(match)
        enriched["fuel_metrics"] = metrics
        enriched["per_occupant_metrics"] = metrics_per_occupant
        enriched["cost_status"] = (
            "priced_from_supplied_fuel_feed"
            if price.get("price_inr_per_litre") is not None
            else "fuel_price_unavailable_cost_not_estimated"
        )
        enriched["recommendation_type"] = "potential_carpool"
        results.append(enriched)

    return results


def summarize_carpool_recommendations(recommendations):
    """Return counts and transparent aggregate estimates."""
    priced = [
        item for item in recommendations
        if item.get("fuel_metrics", {}).get("estimated_fuel_cost_inr") is not None
    ]
    return {
        "potential_matches": len(recommendations),
        "matches_with_vehicle_metrics": sum(
            item.get("fuel_metrics") is not None for item in recommendations
        ),
        "matches_with_fuel_price": len(priced),
        "matches_without_fuel_price": sum(
            item.get("cost_status") == "fuel_price_unavailable_cost_not_estimated"
            for item in recommendations
        ),
        "note": "Potential matches require employee consent and confirmation; estimates are not bookings or live quotes."
    }
