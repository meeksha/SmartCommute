"""Unit tests with mocked existing planners; no GTFS/network files required."""
import sys
import types

bmtc_stub = types.ModuleType("app.routing.bmtc_latest_planner")
bmtc_stub.plan_bmtc_latest_from_gps = lambda *args, **kwargs: None
metro_stub = types.ModuleType("app.routing.metro_planner")
metro_stub.plan_metro = lambda *args, **kwargs: None
sys.modules.setdefault("app.routing.bmtc_latest_planner", bmtc_stub)
sys.modules.setdefault("app.routing.metro_planner", metro_stub)

from app.routing.bmtc_metro_bmtc_planner import plan_bmtc_metro_bmtc


def fake_bmtc(*args):
    call = getattr(fake_bmtc, "count", 0)
    fake_bmtc.count = call + 1
    if call == 0:
        dep, arr, access, egress = "09:05:00", "09:35:00", 300, 450
    else:
        dep, arr, access, egress = "10:30:00", "11:00:00", 400, 500
    return {"status": "success", "best_journey": {
        "origin_access": {"distance_m": access},
        "destination_egress": {"distance_m": egress, "walking_minutes": egress / 80},
        "bmtc_journey": {"departure": dep, "arrival": arr, "legs": []},
    }}


def fake_metro(origin, destination, date, time):
    assert origin == "Electronic City"
    assert destination == "Goraguntepalya"
    assert time == "09:46"
    return {"status": "success", "arrival": "10:25:00", "duration_minutes": 45, "legs": []}


def test_successful_three_mode_composition():
    fake_bmtc.count = 0
    result = plan_bmtc_metro_bmtc(
        12.84, 77.67, 13.10, 77.59, "2026-11-18", "09:00",
        "Electronic City", 12.84, 77.67,
        "Goraguntepalya", 13.01, 77.51,
        bmtc_planner=fake_bmtc, metro_planner=fake_metro,
    )
    assert result["status"] == "success", result
    assert result["journey_type"] == "BMTC + Metro + BMTC"
    assert len(result["legs"]) == 3
    assert result["arrival"] == "11:06:15"
    assert result["total_duration_minutes"] == 126.2


def test_rejects_excessive_walking():
    def bad_bmtc(*args):
        return {"status": "success", "best_journey": {
            "origin_access": {"distance_m": 300},
            "destination_egress": {"distance_m": 2500},
            "bmtc_journey": {"arrival": "09:35:00"},
        }}
    result = plan_bmtc_metro_bmtc(
        12.84, 77.67, 13.10, 77.59, "2026-11-18", "09:00",
        "Electronic City", 12.84, 77.67,
        "Goraguntepalya", 13.01, 77.51,
        bmtc_planner=bad_bmtc, metro_planner=fake_metro,
    )
    assert result["status"] == "rejected"
    assert result["stage"] == "origin_feeder"


if __name__ == "__main__":
    test_successful_three_mode_composition()
    test_rejects_excessive_walking()
    print("THREE-MODE BMTC + METRO + BMTC TESTS PASSED")
