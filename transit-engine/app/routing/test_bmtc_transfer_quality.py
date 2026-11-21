from app.routing.recommendation_quality import filter_journeys, process_recommendations


def item(legs, walking=300):
    return {
        "mode": "BMTC Bus", "duration_minutes": 120,
        "distance_walking_m": walking,
        "fare": {"total_fare_inr": 95},
        "emissions": {"emissions_kg_co2e": 1.4},
        "journey": {"legs": legs, "walking_distance_m": walking, "transfers": max(0, sum(x.get("type") == "bmtc_bus" for x in legs)-1)},
    }


def run_tests():
    walk_origin = {"type": "walking", "segment": "origin_access", "distance_m": 144}
    walk_end = {"type": "walking", "segment": "destination_egress", "distance_m": 150}
    long_bus = {"type": "bmtc_bus", "route_number": "G-10", "scheduled_duration_minutes": 62.9, "from_stop_id": "A", "to_stop_id": "B"}
    tiny_bus = {"type": "bmtc_bus", "route_number": "CHAKRA-10A", "scheduled_duration_minutes": 0.8, "from_stop_id": "B", "to_stop_id": "C"}
    suspicious = item([walk_origin, long_bus, tiny_bus, walk_end])
    good_single = item([walk_origin, long_bus, walk_end])
    legitimate_transfer = item([walk_origin, long_bus, {**tiny_bus, "scheduled_duration_minutes": 12.0}, walk_end])
    too_far_to_walk = item([walk_origin, long_bus, tiny_bus,
                            {"type": "walking", "segment": "destination_egress", "distance_m": 900}], walking=1050)

    accepted, rejected = filter_journeys([suspicious, good_single, legitimate_transfer, too_far_to_walk])
    assert len(accepted) == 3, (len(accepted), rejected)
    assert len(rejected) == 1
    assert "short terminal BMTC hop" in rejected[0]["reasons"][0]

    result = process_recommendations([suspicious, good_single])
    assert len(result["recommendations"]) == 1
    assert len(result["rejected_recommendations"]) == 1
    print("BMTC TRANSFER QUALITY TESTS PASSED")


if __name__ == "__main__":
    run_tests()
