from app.routing.three_mode_adapter import adapt_bmtc_metro_bmtc


def sample():
    return {
        "status": "success", "journey_type": "BMTC + Metro + BMTC",
        "total_duration_minutes": 137.3, "walking_m": 361.1,
        "data_warnings": ["Scheduled GTFS only"],
        "legs": [
            {"mode": "BMTC feeder", "journey": {
                "origin_access": {"distance_m": 37.5, "walking_minutes": 0.5},
                "destination_egress": {"distance_m": 70.3, "walking_minutes": 0.9},
                "bmtc_journey": {"legs": [{"route_number": "F1", "from_stop": "A", "to_stop": "B"}]}}},
            {"mode": "Metro", "journey": {"legs": [{"line": "Purple", "from_station": "X", "to_station": "Y"}, {"line": "Green", "from_station": "Y", "to_station": "Z"}]}},
            {"mode": "BMTC feeder", "journey": {
                "origin_access": {"distance_m": 100.2, "walking_minutes": 1.3},
                "destination_egress": {"distance_m": 153.1, "walking_minutes": 1.9},
                "bmtc_journey": {"legs": [{"route_number": "F2", "from_stop": "C", "to_stop": "D"}, {"route_number": "F3", "from_stop": "D", "to_stop": "E"}]}}},
        ]}


def main():
    adapted = adapt_bmtc_metro_bmtc(sample())
    assert adapted is not None
    assert adapted["mode"] == "BMTC + Metro + BMTC"
    assert adapted["duration_minutes"] == 137.3
    assert adapted["distance_walking_m"] == 361.1
    assert adapted["fare"] is None and adapted["emissions"] is None
    kinds = [leg["type"] for leg in adapted["journey"]["legs"]]
    assert kinds.count("bmtc_bus") == 3
    assert kinds.count("metro") == 2
    assert kinds.count("walking") == 4
    assert adapted["journey"]["transfers"] == 4
    assert adapt_bmtc_metro_bmtc({"status": "unavailable"}) is None
    print("THREE-MODE RECOMMENDATION ADAPTER TESTS PASSED")


if __name__ == "__main__":
    main()
