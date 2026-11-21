from __future__ import annotations

import pandas as pd

from app.routing.bmtc_connection_scan import scan_bmtc_connections, earliest_label


def test_target_aware_scan_matches_full_scan():
    # Deliberately include a later express connection that reaches the target
    # earlier than a slower service, ensuring the scanner does not stop on
    # first target discovery.
    rows = [
        ("A", "B", "T1", 100, 200),
        ("B", "D", "T1", 210, 500),
        ("A", "C", "T2", 120, 150),
        ("C", "D", "T2", 160, 250),
        ("A", "E", "T3", 300, 310),
        ("E", "F", "T3", 320, 330),
    ]
    frame = pd.DataFrame([
        {
            "stop_id": a,
            "next_stop_id": b,
            "trip_id": trip,
            "departure_seconds": dep,
            "arrival_seconds": arr,
            "route_id": "R",
            "route_short_name": "R",
            "route_long_name": "Test route",
        }
        for a, b, trip, dep, arr in rows
    ]).sort_values("departure_seconds").reset_index(drop=True)

    labels = scan_bmtc_connections(
        frame,
        [{"stop_id": "A", "ready_seconds": 0}],
        transfer_buffer_seconds=0,
        target_stop_ids=["D"],
        progress_label="TEST",
    )
    best = earliest_label(labels, "D")
    assert best is not None
    assert best["arrival"] == 250
    assert [leg["trip_id"] for leg in best["path"]] == ["T2", "T2"]


def test_multiple_targets_are_all_reached_before_early_stop():
    rows = [
        ("A", "B", "T1", 100, 110),
        ("B", "D", "T1", 120, 130),
        ("A", "C", "T2", 140, 150),
        ("C", "E", "T2", 160, 170),
        ("A", "X", "T3", 200, 210),
    ]
    frame = pd.DataFrame([
        {
            "stop_id": a, "next_stop_id": b, "trip_id": trip,
            "departure_seconds": dep, "arrival_seconds": arr,
            "route_id": "R", "route_short_name": "R",
            "route_long_name": "Test route",
        }
        for a, b, trip, dep, arr in rows
    ]).sort_values("departure_seconds").reset_index(drop=True)
    labels = scan_bmtc_connections(
        frame, [{"stop_id": "A", "ready_seconds": 0}],
        transfer_buffer_seconds=0, target_stop_ids=["D", "E"],
        progress_label="TEST",
    )
    assert earliest_label(labels, "D")["arrival"] == 130
    assert earliest_label(labels, "E")["arrival"] == 170


if __name__ == "__main__":
    test_target_aware_scan_matches_full_scan()
    test_multiple_targets_are_all_reached_before_early_stop()
    print("BMTC PERFORMANCE PATCH TESTS PASSED")
