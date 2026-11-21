import pandas as pd

from app.routing.bmtc_connection_scan import (
    scan_bmtc_connections,
    earliest_label,
)


def test_paths_remain_tied_to_their_origin_stop():
    connections = pd.DataFrame([
        {
            "trip_id": "T1", "route_id": "R1", "route_short_name": "10",
            "route_long_name": "A-B", "stop_id": "A", "next_stop_id": "X",
            "departure_seconds": 9 * 3600, "arrival_seconds": 9 * 3600 + 300,
        },
        {
            "trip_id": "T1", "route_id": "R1", "route_short_name": "10",
            "route_long_name": "A-B", "stop_id": "X", "next_stop_id": "B",
            "departure_seconds": 9 * 3600 + 360, "arrival_seconds": 9 * 3600 + 600,
        },
        {
            "trip_id": "T1", "route_id": "R1", "route_short_name": "10",
            "route_long_name": "A-B", "stop_id": "B", "next_stop_id": "Y",
            "departure_seconds": 9 * 3600 + 660, "arrival_seconds": 9 * 3600 + 900,
        },
        {
            "trip_id": "T2", "route_id": "R2", "route_short_name": "20",
            "route_long_name": "B-Y", "stop_id": "B", "next_stop_id": "Y",
            "departure_seconds": 9 * 3600 + 1200, "arrival_seconds": 9 * 3600 + 1500,
        },
    ])

    labels = scan_bmtc_connections(
        connections,
        [
            {"stop_id": "A", "ready_seconds": 9 * 3600 - 60},
            {"stop_id": "B", "ready_seconds": 9 * 3600 - 60},
        ],
        transfer_buffer_seconds=300,
        target_stop_ids={"Y"},
        progress_label="Synthetic test",
    )

    result = earliest_label(labels, "Y")
    assert result is not None
    assert result["path"][0]["from_stop"] == result["origin_id"]
    assert result["path"][-1]["to_stop"] == "Y"
    assert all(
        left["to_stop"] == right["from_stop"]
        for left, right in zip(result["path"], result["path"][1:])
    )


if __name__ == "__main__":
    test_paths_remain_tied_to_their_origin_stop()
    print("BMTC CONNECTION SCAN TEST PASSED")
