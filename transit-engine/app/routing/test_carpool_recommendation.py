from app.routing.carpool_recommendation import (
    build_carpool_recommendations,
    summarize_carpool_recommendations,
)


def fixtures():
    employees = [
        {
            "employee_id": "D1", "role": "driver", "available_seats": 2,
            "origin_lat": 12.9716, "origin_lon": 77.5946,
            "destination_lat": 13.0358, "destination_lon": 77.5970,
            "departure_time": "08:30"
        },
        {
            "employee_id": "R1", "role": "rider",
            "origin_lat": 12.9760, "origin_lon": 77.5960,
            "destination_lat": 13.0370, "destination_lon": 77.5990,
            "departure_time": "08:40"
        }
    ]
    vehicles = {
        "D1": {
            "distance_km": 18.4,
            "mileage_km_per_litre": 15,
            "fuel_type": "petrol"
        }
    }
    prices = {
        "D1": {
            "price_inr_per_litre": 105,
            "source": "test fixture (not live)",
            "timestamp": "2026-11-18T09:00:00+05:30"
        }
    }
    return employees, vehicles, prices


def test_end_to_end_carpool_recommendation():
    employees, vehicles, prices = fixtures()
    results = build_carpool_recommendations(employees, vehicles, prices)
    assert len(results) == 1
    item = results[0]
    assert item["recommendation_type"] == "potential_carpool"
    assert item["fuel_metrics"]["estimated_fuel_cost_inr"] is not None
    assert item["per_occupant_metrics"]["cost_per_occupant_inr"] is not None
    assert item["per_occupant_metrics"]["tailpipe_co2_kg_per_occupant"] > 0
    summary = summarize_carpool_recommendations(results)
    assert summary["potential_matches"] == 1
    assert summary["matches_with_fuel_price"] == 1


def test_missing_price_does_not_become_zero():
    employees, vehicles, _ = fixtures()
    results = build_carpool_recommendations(employees, vehicles, fuel_prices={})
    item = results[0]
    assert item["fuel_metrics"]["estimated_fuel_cost_inr"] is None
    assert item["fuel_metrics"]["estimated_tailpipe_co2_kg"] > 0
    assert item["cost_status"] == "fuel_price_unavailable_cost_not_estimated"


if __name__ == "__main__":
    test_end_to_end_carpool_recommendation()
    test_missing_price_does_not_become_zero()
    print("CARPOOL RECOMMENDATION INTEGRATION TESTS PASSED")
