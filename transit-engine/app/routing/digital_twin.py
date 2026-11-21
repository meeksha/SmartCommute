"""Organization-level commute digital twin and scenario simulator.

This is a planning/simulation layer, not a live operational twin. It consumes
an organization-provided employee snapshot and scenario assumptions, then
estimates daily commute trips, fuel cost and direct tailpipe CO2.
"""
from copy import deepcopy
from app.routing.carpool_matching import match_employees
from app.routing.fuel_emissions import calculate_vehicle_fuel_metrics


def _employee_baseline(employee, vehicle_profiles, fuel_prices):
    """Return one employee's baseline emissions/cost when enough data exists."""
    explicit_emissions = employee.get("baseline_emissions_kg")
    explicit_cost = employee.get("baseline_cost_inr")
    if explicit_emissions is not None:
        return float(explicit_emissions), (float(explicit_cost) if explicit_cost is not None else None), "employee_baseline_input"

    vehicle = vehicle_profiles.get(employee["employee_id"])
    if not vehicle:
        return None, None, "baseline_data_missing"
    price = fuel_prices.get(employee["employee_id"], {})
    metrics = calculate_vehicle_fuel_metrics(
        distance_km=vehicle["distance_km"],
        mileage_km_per_litre=vehicle["mileage_km_per_litre"],
        fuel_type=vehicle["fuel_type"],
        fuel_price_inr_per_litre=price.get("price_inr_per_litre"),
        price_source=price.get("source"),
        price_timestamp=price.get("timestamp"),
        emission_factor_kg_co2_per_litre=vehicle.get("emission_factor_kg_co2_per_litre"),
    )
    return metrics["estimated_tailpipe_co2_kg"], metrics["estimated_fuel_cost_inr"], "vehicle_fuel_model"


def simulate_organization_commute(
    employee_profiles,
    vehicle_profiles,
    fuel_prices=None,
    carpool_participation_rate=0.0,
    matching_limits=None,
):
    """Simulate one representative one-way commute for an organization.

    Employee profiles require the matching engine's fields. For a baseline,
    provide either baseline_emissions_kg (and optionally baseline_cost_inr)
    or a vehicle profile keyed by employee_id. Carpooling is modeled as a
    driver/rider pair; one employee can participate in at most one pair.
    Participation rate controls the share of feasible matched pairs adopted.
    """
    rate = float(carpool_participation_rate)
    if not 0.0 <= rate <= 1.0:
        raise ValueError("carpool_participation_rate must be between 0 and 1")
    employees = list(employee_profiles)
    if not employees:
        raise ValueError("employee_profiles cannot be empty")
    ids = [e.get("employee_id") for e in employees]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Each employee must have a unique non-empty employee_id")

    prices = fuel_prices or {}
    vehicles = vehicle_profiles or {}
    baseline_rows = {}
    baseline_emissions = 0.0
    baseline_cost = 0.0
    cost_known_count = 0
    emissions_known_count = 0
    for employee in employees:
        emissions, cost, source = _employee_baseline(employee, vehicles, prices)
        baseline_rows[employee["employee_id"]] = {
            "emissions_kg": emissions, "cost_inr": cost, "source": source
        }
        if emissions is not None:
            baseline_emissions += emissions
            emissions_known_count += 1
        if cost is not None:
            baseline_cost += cost
            cost_known_count += 1

    candidate_pairs = match_employees(employees, **(matching_limits or {}))
    # Greedy disjoint matching: no employee is assigned to more than one pair.
    used = set()
    feasible = []
    for pair in candidate_pairs:
        driver_id = pair["driver_employee_id"]
        rider_id = pair["rider_employee_id"]
        if driver_id in used or rider_id in used:
            continue
        vehicle = vehicles.get(driver_id)
        if not vehicle:
            continue
        feasible.append(pair)
        used.update((driver_id, rider_id))

    adopted_count = int(len(feasible) * rate)
    adopted_pairs = feasible[:adopted_count]
    employee_by_id = {e["employee_id"]: e for e in employees}
    adopted_employee_ids = set()
    carpool_emissions = 0.0
    carpool_cost = 0.0
    carpool_cost_known = True
    for pair in adopted_pairs:
        driver_id, rider_id = pair["driver_employee_id"], pair["rider_employee_id"]
        vehicle = vehicles[driver_id]
        price = prices.get(driver_id, {})
        metrics = calculate_vehicle_fuel_metrics(
            distance_km=vehicle["distance_km"],
            mileage_km_per_litre=vehicle["mileage_km_per_litre"],
            fuel_type=vehicle["fuel_type"],
            fuel_price_inr_per_litre=price.get("price_inr_per_litre"),
            price_source=price.get("source"),
            price_timestamp=price.get("timestamp"),
            emission_factor_kg_co2_per_litre=vehicle.get("emission_factor_kg_co2_per_litre"),
        )
        carpool_emissions += metrics["estimated_tailpipe_co2_kg"]
        if metrics["estimated_fuel_cost_inr"] is None:
            carpool_cost_known = False
        else:
            carpool_cost += metrics["estimated_fuel_cost_inr"]
        adopted_employee_ids.update((driver_id, rider_id))

    # Employees not in an adopted pair retain their baseline commute.
    scenario_emissions = carpool_emissions
    scenario_cost = carpool_cost
    scenario_cost_known = carpool_cost_known
    scenario_emissions_known = True
    for employee in employees:
        employee_id = employee["employee_id"]
        if employee_id in adopted_employee_ids:
            continue
        row = baseline_rows[employee_id]
        if row["emissions_kg"] is None:
            scenario_emissions_known = False
        else:
            scenario_emissions += row["emissions_kg"]
        if row["cost_inr"] is None:
            scenario_cost_known = False
        else:
            scenario_cost += row["cost_inr"]

    baseline_emissions_value = round(baseline_emissions, 4) if emissions_known_count == len(employees) else None
    scenario_emissions_value = round(scenario_emissions, 4) if scenario_emissions_known else None
    baseline_cost_value = round(baseline_cost, 2) if cost_known_count == len(employees) else None
    scenario_cost_value = round(scenario_cost, 2) if scenario_cost_known else None

    savings_emissions = (
        round(baseline_emissions_value - scenario_emissions_value, 4)
        if baseline_emissions_value is not None and scenario_emissions_value is not None else None
    )
    savings_cost = (
        round(baseline_cost_value - scenario_cost_value, 2)
        if baseline_cost_value is not None and scenario_cost_value is not None else None
    )

    # Peak-hour demand profile: count employee trips by departure hour.
    peak_profile = {}
    for employee in employees:
        departure = str(employee.get("departure_time", "unknown"))
        hour = departure.split(":")[0] if ":" in departure else "unknown"
        peak_profile[hour] = peak_profile.get(hour, 0) + 1

    return {
        "simulation_type": "organization_commute_digital_twin",
        "is_live_twin": False,
        "scenario": {"carpool_participation_rate": rate},
        "organization_metrics": {
            "employee_count": len(employees),
            "feasible_disjoint_carpool_pairs": len(feasible),
            "adopted_carpool_pairs": len(adopted_pairs),
            "employees_in_adopted_carpools": len(adopted_employee_ids),
            "estimated_vehicle_trips_reduced": len(adopted_pairs),
            "peak_departure_hour_employee_counts": peak_profile,
        },
        "baseline": {
            "one_way_tailpipe_co2_kg": baseline_emissions_value,
            "one_way_fuel_cost_inr": baseline_cost_value,
            "employees_with_emissions_data": emissions_known_count,
            "employees_with_cost_data": cost_known_count,
        },
        "scenario_result": {
            "one_way_tailpipe_co2_kg": scenario_emissions_value,
            "one_way_fuel_cost_inr": scenario_cost_value,
        },
        "estimated_savings": {
            "tailpipe_co2_kg": savings_emissions,
            "fuel_cost_inr": savings_cost,
        },
        "potential_matches": deepcopy(feasible),
        "adopted_matches": deepcopy(adopted_pairs),
        "data_quality": {
            "fuel_price_missing_for_some_vehicles": any(
                not prices.get(eid, {}).get("price_inr_per_litre") for eid in vehicles
            ),
            "baseline_emissions_missing": emissions_known_count != len(employees),
            "baseline_cost_missing": cost_known_count != len(employees),
        },
        "limitations": [
            "One representative one-way commute is simulated, not a full daily round trip.",
            "Carpool pairs are greedily matched; multi-rider groups are not yet modeled.",
            "Matching proximity uses straight-line distances, not road-network detours.",
            "Fuel cost and direct tailpipe CO2 are estimates; upstream fuel lifecycle emissions are excluded.",
            "This is an offline scenario model, not a live synchronized digital twin.",
            "Results depend on employee consent, profile accuracy and actual carpool adoption."
        ]
    }


def run_participation_scenarios(
    employee_profiles,
    vehicle_profiles,
    fuel_prices=None,
    participation_rates=(0.0, 0.25, 0.5, 0.75, 1.0),
    matching_limits=None,
):
    """Run comparable organization scenarios at multiple adoption rates."""
    return [
        simulate_organization_commute(
            employee_profiles=employee_profiles,
            vehicle_profiles=vehicle_profiles,
            fuel_prices=fuel_prices,
            carpool_participation_rate=rate,
            matching_limits=matching_limits,
        )
        for rate in participation_rates
    ]
