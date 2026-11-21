from app.routing.digital_twin import (
    simulate_organization_commute,
    run_participation_scenarios,
)


def fixture_data():
    employees = [
        {"employee_id": "D1", "role": "driver", "available_seats": 2,
         "origin_lat": 12.9716, "origin_lon": 77.5946,
         "destination_lat": 13.0358, "destination_lon": 77.5970,
         "departure_time": "08:30", "baseline_emissions_kg": 2.0,
         "baseline_cost_inr": 90.0},
        {"employee_id": "R1", "role": "rider",
         "origin_lat": 12.9760, "origin_lon": 77.5960,
         "destination_lat": 13.0370, "destination_lon": 77.5990,
         "departure_time": "08:40", "baseline_emissions_kg": 1.8,
         "baseline_cost_inr": 85.0},
        {"employee_id": "R2", "role": "rider",
         "origin_lat": 12.9000, "origin_lon": 77.5000,
         "destination_lat": 13.2000, "destination_lon": 77.7000,
         "departure_time": "09:10", "baseline_emissions_kg": 1.5,
         "baseline_cost_inr": 70.0},
    ]
    vehicles = {"D1": {"distance_km": 18.4, "mileage_km_per_litre": 15,
                       "fuel_type": "petrol"}}
    prices = {"D1": {"price_inr_per_litre": 105, "source": "test fixture",
                     "timestamp": "2026-11-18T09:00:00+05:30"}}
    return employees, vehicles, prices


def test_zero_participation_baseline():
    employees, vehicles, prices = fixture_data()
    result = simulate_organization_commute(employees, vehicles, prices, 0.0)
    assert result["organization_metrics"]["adopted_carpool_pairs"] == 0
    assert result["baseline"]["one_way_tailpipe_co2_kg"] == result["scenario_result"]["one_way_tailpipe_co2_kg"]
    assert result["estimated_savings"]["tailpipe_co2_kg"] == 0.0


def test_full_participation_scenario():
    employees, vehicles, prices = fixture_data()
    result = simulate_organization_commute(employees, vehicles, prices, 1.0)
    assert result["organization_metrics"]["adopted_carpool_pairs"] == 1
    assert result["organization_metrics"]["employees_in_adopted_carpools"] == 2
    assert result["estimated_savings"]["tailpipe_co2_kg"] > 0
    assert result["estimated_savings"]["fuel_cost_inr"] is not None


def test_scenario_sweep():
    employees, vehicles, prices = fixture_data()
    results = run_participation_scenarios(employees, vehicles, prices, (0, 0.5, 1))
    assert len(results) == 3
    assert [r["scenario"]["carpool_participation_rate"] for r in results] == [0, 0.5, 1]


def test_missing_baseline_data_is_not_zero():
    employees, vehicles, prices = fixture_data()
    employees[0].pop("baseline_emissions_kg")
    employees[0].pop("baseline_cost_inr")
    vehicles.clear()
    result = simulate_organization_commute(employees, vehicles, prices, 0)
    assert result["baseline"]["one_way_tailpipe_co2_kg"] is None
    assert result["data_quality"]["baseline_emissions_missing"] is True


if __name__ == "__main__":
    test_zero_participation_baseline()
    test_full_participation_scenario()
    test_scenario_sweep()
    test_missing_baseline_data_is_not_zero()
    print("DIGITAL TWIN TESTS PASSED")
