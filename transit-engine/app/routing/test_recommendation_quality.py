from app.routing.recommendation_quality import (
    filter_journeys, deduplicate_journeys, rank_journeys, process_recommendations
)


def make_item(mode, duration, walking, emissions, fare, legs, transfers=0):
    return {
        "mode": mode,
        "duration_minutes": duration,
        "distance_walking_m": walking,
        "fare": {"total_fare_inr": fare} if fare is not None else {},
        "emissions": {"emissions_kg_co2e": emissions} if emissions is not None else {},
        "journey": {"legs": legs, "walking_distance_m": walking, "transfers": transfers},
    }


def run_tests():
    walk = lambda segment, distance: {
        "type": "walking", "segment": segment, "distance_m": distance,
        "from": segment, "to": "next"
    }
    bus = {"type": "bmtc_bus", "route_number": "250-P", "from_stop_id": "A", "to_stop_id": "B"}
    good = make_item("BMTC Bus", 42, 700, 0.8, 15,
                     [walk("origin_access", 250), bus, walk("destination_egress", 450)], 0)
    bad = make_item("Walking + Metro", 38, 2873, 0.2, 30,
                    [walk("origin_access", 333), {"type": "metro", "line": "green", "from_stop_id": "S1", "to_stop_id": "S2"}, walk("destination_egress", 2540)], 0)
    accepted, rejected = filter_journeys([good, bad])
    assert len(accepted) == 1 and len(rejected) == 1
    assert any("destination egress walk" in reason for reason in rejected[0]["reasons"])

    duplicate = make_item("BMTC Bus", 45, 700, 0.8, 15,
                          [walk("origin_access", 250), bus, walk("destination_egress", 450)], 0)
    unique, removed = deduplicate_journeys([good, duplicate])
    assert len(unique) == 1 and len(removed) == 1
    ranked = rank_journeys([good, make_item("Private Car", 30, 0, 2.5, 120,
                            [{"type": "car"}], 0)])
    assert ranked[0]["rank"] == 1
    assert all("ranking_score" in item for item in ranked)

    road = make_item("Private Car", 30, None, 2.5, 120, [{"type": "car"}], 0)
    road.pop("distance_walking_m", None)
    road["journey"].pop("walking_distance_m", None)
    road["journey"]["legs"] = [{"type": "car"}]
    road_accepted, road_rejected = filter_journeys([road])
    assert len(road_accepted) == 1 and not road_rejected

    result = process_recommendations([good, bad, duplicate])
    assert len(result["recommendations"]) == 1
    assert len(result["rejected_recommendations"]) == 1
    assert len(result["duplicate_recommendations_removed"]) == 1
    print("RECOMMENDATION QUALITY TESTS PASSED")


if __name__ == "__main__":
    run_tests()
