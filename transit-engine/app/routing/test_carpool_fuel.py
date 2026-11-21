from app.routing.carpool_matching import match_employees
from app.routing.fuel_emissions import (
    calculate_vehicle_fuel_metrics,
    allocate_shared_trip_metrics,
)


def test_fuel_metrics():
    result = calculate_vehicle_fuel_metrics(
        distance_km=20,
        mileage_km_per_litre=15,
        fuel_type="petrol",
        fuel_price_inr_per_litre=105,
        price_source="test fixture",
        price_timestamp="2026-11-18T00:00:00+05:30",
    )
    assert result["estimated_fuel_consumed_litres"] == 1.3333
    assert result["estimated_fuel_cost_inr"] == 140.0
    assert result["estimated_tailpipe_co2_kg"] > 3.0
    shared = allocate_shared_trip_metrics(result, 2)
    assert shared["cost_per_occupant_inr"] == 70.0
    assert shared["tailpipe_co2_kg_per_occupant"] < result["estimated_tailpipe_co2_kg"]


def test_price_does_not_change_emissions():
    a = calculate_vehicle_fuel_metrics(20, 15, "petrol", 100)
    b = calculate_vehicle_fuel_metrics(20, 15, "petrol", 120)
    assert a["estimated_tailpipe_co2_kg"] == b["estimated_tailpipe_co2_kg"]
    assert a["estimated_fuel_cost_inr"] != b["estimated_fuel_cost_inr"]


def test_carpool_matching():
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
        },
        {
            "employee_id": "R2", "role": "rider",
            "origin_lat": 12.9000, "origin_lon": 77.5000,
            "destination_lat": 13.2000, "destination_lon": 77.7000,
            "departure_time": "10:00"
        }
    ]
    results = match_employees(employees)
    assert len(results) == 1
    assert results[0]["driver_employee_id"] == "D1"
    assert results[0]["rider_employee_id"] == "R1"


if __name__ == "__main__":
    test_fuel_metrics()
    test_price_does_not_change_emissions()
    test_carpool_matching()
    print("CARPOOL + FUEL METRICS TESTS PASSED")
