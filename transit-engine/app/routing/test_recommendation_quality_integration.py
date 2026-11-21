"""Focused acceptance checks for the shared recommendation quality pipeline."""
from app.routing.recommendation_quality import process_recommendations


def candidate(mode, duration, walking, emissions=None, fare=None, legs=None):
    return {
        "mode": mode,
        "duration_minutes": duration,
        "distance_walking_m": walking,
        "fare": fare,
        "emissions": emissions,
        "journey": {
            "mode": mode,
            "transfers": 2,
            "walking_distance_m": walking,
            "legs": legs if legs is not None else [
                {"type": "walking", "segment": "origin_access", "distance_m": walking}
            ],
        },
    }


def main():
    good_bus = candidate(
        "BMTC Bus", 124.2, 296.8,
        emissions={"scenarios": {"diesel": {"emissions_kg_co2e": 1.4}}},
        fare={"total_fare_inr": 95},
    )
    good_three_mode = candidate("BMTC + Metro + BMTC", 137.3, 361.1)
    bad_metro = candidate("Walking + Metro", 239.6, 14463.4)
    duplicate_bus = candidate(
        "BMTC Bus", 130.0, 296.8,
        emissions={"scenarios": {"diesel": {"emissions_kg_co2e": 1.4}}},
        fare={"total_fare_inr": 95},
    )

    # Same bus signature intentionally creates a duplicate.
    shared_bus_legs = [
        {"type": "bmtc_bus", "route_number": "360B", "from_stop_id": "A", "to_stop_id": "B"}
    ]
    good_bus["journey"]["legs"] = shared_bus_legs
    duplicate_bus["journey"]["legs"] = shared_bus_legs

    result = process_recommendations(
        [good_bus, good_three_mode, bad_metro, duplicate_bus],
        ranking_profile="green_first",
    )

    accepted = result["recommendations"]
    assert len(accepted) == 2, f"Expected two accepted unique journeys, got {len(accepted)}"
    assert len(result["rejected_recommendations"]) == 1
    assert len(result["duplicate_recommendations_removed"]) == 1
    three = next(item for item in accepted if item["mode"] == "BMTC + Metro + BMTC")
    assert three["fare_status"] == "unknown"
    assert three["ranking_metrics"]["fare"] is None
    assert three["ranking_metrics"]["emissions"] is None
    assert three["ranking_score"] is not None
    assert all(item.get("rank") for item in accepted)
    print("RECOMMENDATION QUALITY INTEGRATION TESTS PASSED")
    print("- Excessive walking journey rejected")
    print("- Duplicate BMTC itinerary removed")
    print("- Three-mode journey retained with unknown fare/emissions preserved")
    print("- Remaining journeys ranked together")


if __name__ == "__main__":
    main()
