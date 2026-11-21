"""End-to-end test of filter -> de-duplicate -> rank using adapted-schema candidates."""
from app.routing.recommendation_quality import process_recommendations


def candidate(mode, duration, walk, emissions, fare, route):
    return {
        "mode": mode,
        "duration_minutes": duration,
        "distance_walking_m": walk,
        "fare": {"total_fare_inr": fare},
        "emissions": {"emissions_kg_co2e": emissions},
        "journey": {
            "journey_id": f"{mode}-{duration}",
            "walking_distance_m": walk,
            "transfers": 1,
            "legs": [
                {"type": "walking", "segment": "origin_access", "distance_m": 300},
                {"type": "bmtc_bus", "route_number": route,
                 "from_stop_id": "STOP-A", "to_stop_id": "STOP-B"},
                {"type": "walking", "segment": "destination_egress", "distance_m": walk - 300},
            ],
        },
    }


def run_tests():
    candidates = [
        candidate("BMTC Bus", 43, 700, 0.8, 15, "250-P"),
        candidate("BMTC Bus", 48, 700, 0.8, 15, "250-P"),  # duplicate, slower
        candidate("Walking + Metro", 39, 2873, 0.2, 30, "METRO"),  # egress too long
        candidate("BMTC + Metro", 46, 1100, 0.5, 35, "176"),
    ]
    result = process_recommendations(candidates)
    assert result["quality_summary"] == {
        "input_candidates": 4,
        "accepted_after_filter_and_deduplication": 2,
        "rejected_by_walking_limits": 1,
        "duplicates_removed": 1,
    }
    assert [item["rank"] for item in result["recommendations"]] == [1, 2]
    assert all("ranking_score" in item for item in result["recommendations"])
    assert any("destination egress walk" in reason for reason in result["rejected_recommendations"][0]["reasons"])
    print("INTEGRATED RECOMMENDATION PIPELINE TESTS PASSED")


if __name__ == "__main__":
    run_tests()
