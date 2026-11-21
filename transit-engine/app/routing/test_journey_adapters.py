from app.routing.journey_schema import validate_journey, validate_itinerary
from app.routing.journey_adapters import (
    adapt_walking_metro,
    adapt_bmtc_journeys,
    adapt_bmtc_metro_journeys,
)

walking_metro = {
    "status": "success",
    "total_estimated_duration_minutes": 40.4,
    "total_estimated_walking_metres": 630.7,
    "origin_metro": {
        "station_id": "A", "station_name": "Station A",
        "walking_distance_m": 300, "walking_minutes": 3.8,
    },
    "destination_metro": {
        "station_id": "B", "station_name": "Station B",
        "walking_distance_m": 330.7, "walking_minutes": 4.1,
    },
    "metro_journey": {
        "status": "success",
        "legs": [{
            "route_id": "GREEN", "route_name": "Green Line",
            "headsign": "Peenya", "from_station": "Station A",
            "to_station": "Station B", "departure_time": "09:10",
            "arrival_time": "09:20",
        }],
    },
    "metro_fare": {"token_fare_inr": 30},
    "limitations": [],
}

bmtc = {
    "status": "success",
    "best_journey": {
        "total_estimated_duration_minutes": 45,
        "origin_access": {"stop_id": "S1", "stop_name": "Origin Stop", "distance_m": 200},
        "destination_egress": {"stop_id": "S3", "stop_name": "Destination Stop", "distance_m": 150},
        "bmtc_journey": {"legs": [
            {"route_short_name": "49", "from_stop": "S1", "to_stop": "S2",
             "from_stop_name": "Origin Stop", "to_stop_name": "Transfer Stop"},
            {"route_short_name": "82", "from_stop": "S2", "to_stop": "S3",
             "from_stop_name": "Transfer Stop", "to_stop_name": "Destination Stop"},
        ]},
    },
    "alternative_journeys": [],
}

combined = {
    "status": "success",
    "limitations": [],
    "best_journey": {
        "total_estimated_duration_minutes": 48,
        "total_estimated_walking_metres": 700,
        "origin_access": {"stop_id": "S1", "stop_name": "Origin Stop", "distance_m": 100},
        "interchange": {
            "bmtc_stop_id": "S2", "bmtc_stop_name": "Metro Bus Stop",
            "metro_station_name": "Station B", "walking_distance_m": 100,
            "walking_minutes": 1.3,
        },
        "destination_metro": {
            "station_id": "C", "station_name": "Station C",
            "walking_distance_m": 500, "walking_minutes": 6.3,
        },
        "bmtc_journey": {"legs": [{
            "route_short_name": "49", "from_stop": "S1", "to_stop": "S2",
            "from_stop_name": "Origin Stop", "to_stop_name": "Metro Bus Stop",
        }]},
        "metro_journey": {"legs": [{
            "route_id": "GREEN", "route_name": "Green Line",
            "headsign": "Peenya", "from_station": "Station B",
            "to_station": "Station C",
        }]},
        "fare": {"bmtc": {}, "metro": {}},
        "emissions": {},
    },
}

results = {
    "Walking + Metro": adapt_walking_metro(walking_metro),
    "BMTC Bus": adapt_bmtc_journeys(bmtc),
    "BMTC + Metro": adapt_bmtc_metro_journeys(combined),
}

for mode, journeys in results.items():
    print(f"\n{mode}: {len(journeys)} journey(s)")
    for journey in journeys:
        schema = validate_journey(journey)
        route = validate_itinerary(journey)
        print(
            "Duration:", journey["duration_minutes"],
            "| Legs:", len(journey["legs"]),
            "| Transfers:", journey["transfers"],
            "| Schema:", schema["status"],
            "| Route:", route["status"],
        )
        assert schema["status"] == "success"
        assert route["status"] == "success"

assert len(results["Walking + Metro"]) == 1
assert len(results["BMTC Bus"]) == 1
assert len(results["BMTC + Metro"]) == 1
print("\nALL ADAPTER TESTS PASSED")
