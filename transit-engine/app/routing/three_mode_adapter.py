"""Adapt BMTC + Metro + BMTC output and attach defensible emissions scenarios."""
from app.routing.journey_schema import build_journey
from app.routing.three_mode_emissions import calculate_three_mode_emissions
from app.routing.fare_estimator import calculate_three_mode_fare


def adapt_bmtc_metro_bmtc(result: dict, *, fare_data: dict | None = None) -> dict | None:
    if not isinstance(result, dict) or result.get("status") != "success":
        return None

    legs = []
    transfers = 2  # BMTC -> Metro and Metro -> BMTC
    for index, section in enumerate(result.get("legs", [])):
        mode = section.get("mode")
        journey = section.get("journey") or {}
        if mode == "BMTC feeder":
            bus = journey.get("bmtc_journey") or {}
            access = journey.get("origin_access") or {}
            egress = journey.get("destination_egress") or {}
            legs.append({
                "type": "walking",
                "segment": "origin_access" if index == 0 else "transfer_walk",
                "distance_m": access.get("distance_m"),
                "duration_minutes": access.get("walking_minutes"),
                "details": access,
            })
            bus_legs = bus.get("legs") or []
            legs.extend({"type": "bmtc_bus", **leg} for leg in bus_legs)
            transfers += max(0, len(bus_legs) - 1)
            legs.append({
                "type": "walking",
                "segment": "transfer_walk" if index == 0 else "destination_egress",
                "distance_m": egress.get("distance_m"),
                "duration_minutes": egress.get("walking_minutes"),
                "details": egress,
            })
        elif mode == "Metro":
            metro_legs = journey.get("legs") or []
            legs.extend({"type": "metro", **leg} for leg in metro_legs)
            transfers += max(0, len(metro_legs) - 1)

    walking = result.get("walking_m")
    duration = result.get("total_duration_minutes")
    if walking is None or duration is None:
        return None

    # If source GTFS shape distances are missing, retain emissions as unknown.
    # Never insert zero or substitute straight-line distance.
    emissions = calculate_three_mode_emissions(result)
    fare_result = calculate_three_mode_fare(result, fare_data)
    if emissions.get("status") != "success":
        emissions_value = None
        emissions_limitations = [
            "Three-mode emissions unavailable: " + emissions.get("message", "distance data unavailable")
        ]
    else:
        emissions_value = dict(emissions)
        # Expose scenario totals at the root so recommendation_quality's
        # conservative emissions extractor can compare this mode fairly.
        nested_scenarios = emissions.get("emissions_kg_co2e", {}).get("scenarios", {})
        emissions_value["scenarios"] = {
            name: {"total_emissions_kg_co2e": scenario.get("total_emissions_kg_co2e")}
            for name, scenario in nested_scenarios.items()
        }
        emissions_limitations = list(emissions.get("limitations") or [])

    limitations = list(result.get("data_warnings") or []) + emissions_limitations
    if fare_result.get("status") != "success":
        limitations.append("Combined fare remains unknown: " + fare_result.get("message", "fare data incomplete"))
    common = build_journey(
        mode="BMTC + Metro + BMTC",
        duration_minutes=duration,
        legs=legs,
        walking_distance_m=walking,
        distance_km=(
            emissions_value["distance_km"]["combined_motorized"]
            if emissions_value is not None else None
        ),
        fare=(
            {"total_fare_inr": fare_result["total_fare_inr"],
             "currency": "INR", "source": fare_result.get("source"),
             "effective_date": fare_result.get("effective_date"),
             "components": fare_result.get("components")}
            if fare_result.get("status") == "success" else None
        ),
        emissions=emissions_value,
        transfers=transfers,
        data_sources=["BMTC GTFS 2026-2027", "Namma Metro GTFS", "Project life-cycle emission factors"],
        limitations=limitations,
        raw_details=result,
    )
    return {
        "mode": common["mode"],
        "duration_minutes": common["duration_minutes"],
        "distance_walking_m": common["walking_distance_m"],
        "fare": (
            {"total_fare_inr": fare_result["total_fare_inr"],
             "currency": "INR", "source": fare_result.get("source"),
             "effective_date": fare_result.get("effective_date"),
             "components": fare_result.get("components")}
            if fare_result.get("status") == "success" else None
        ),
        "fare_calculation": fare_result,
        "emissions": emissions_value,
        "data_type": "Scheduled BMTC + Metro + BMTC GTFS",
        "journey": common,
        "details": result,
        "emissions_calculation": emissions,
        "limitations": limitations,
    }
