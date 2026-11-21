from app.routing.recommendation_quality import (
    rank_journeys, process_recommendations, _estimated_fare
)


def item(mode, duration, emissions, fare, walking=0, transfers=0):
    return {
        "mode": mode,
        "duration_minutes": duration,
        "distance_walking_m": walking,
        "fare": {"total_fare_inr": fare} if fare is not None else {},
        "emissions": {"emissions_kg_co2e": emissions} if emissions is not None else {},
        "journey": {"legs": ([{"type": "walking", "segment": "origin_access", "distance_m": walking}]
                            if walking else [{"type": mode.lower()}]),
                    "walking_distance_m": walking, "transfers": transfers},
    }


def run_tests():
    bus = item("BMTC Bus", 124, 1.40, 95, 297, 1)
    bike = item("Private Two-Wheeler", 60, 2.17, None, 0, 0)

    green = rank_journeys([bus.copy(), bike.copy()], profile="green_first")
    assert green[0]["mode"] == "BMTC Bus", "Green-first should prioritize much lower emissions in this fixture"
    assert all("balanced" in x["ranking_scores"] and "green_first" in x["ranking_scores"] for x in green)

    bike_with_known_cost = item("Private Two-Wheeler", 60, 2.17, 35, 0, 0)
    balanced = rank_journeys([bus.copy(), bike_with_known_cost], profile="balanced")
    assert balanced[0]["mode"] == "Private Two-Wheeler", "Balanced profile should expose the duration trade-off"

    unknown = item("Private Car", 65, 5.0, None)
    assert _estimated_fare(unknown) == (None, None)
    ranked = rank_journeys([bus.copy(), unknown], profile="green_first")
    car = next(x for x in ranked if x["mode"] == "Private Car")
    assert car["fare_status"] == "unknown"
    assert "fare" in car["ranking_missing_metrics"]
    assert car["ranking_breakdown"]["fare"] == 0.5, "Unknown fare must use neutral midpoint, not zero"

    taxi = {
        "mode": "Taxi", "duration_minutes": 60, "distance_walking_m": 0,
        "fare": {}, "fare_estimates": {"cab": {"10_to_15_lakh": {"estimated_total_inr": 950}}},
        "emissions": {"emissions_kg_co2e": 8},
        "journey": {"legs": [{"type": "taxi"}], "walking_distance_m": 0, "transfers": 0},
    }
    assert _estimated_fare(taxi)[0] == 950
    assert _estimated_fare(taxi)[1].startswith("fare_estimates.cab")

    bike_cost = {
        "mode": "Private Two-Wheeler", "duration_minutes": 60,
        "distance_walking_m": 0, "fare": {},
        "operating_cost": {"fuel_cost_inr": 82.15},
        "emissions": {"emissions_kg_co2e": 2},
        "journey": {"legs": [{"type": "motorcycle"}], "walking_distance_m": 0, "transfers": 0},
    }
    assert _estimated_fare(bike_cost) == (None, None), "Fuel operating cost must not be mislabeled as a fare"

    result = process_recommendations([bus.copy(), bike.copy()], ranking_profile="green_first")
    assert result["ranking_profile"] == "green_first"
    assert set(result["ranking_weights"]) == {"balanced", "green_first"}
    print("SUSTAINABILITY RANKING TESTS PASSED")


if __name__ == "__main__":
    run_tests()
