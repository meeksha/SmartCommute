from app.routing.journey_schema import (
    build_journey,
    validate_journey
)

sample = build_journey(
    mode="BMTC + Metro",
    duration_minutes=40.4,
    legs=[
        {
            "type": "bus",
            "from_stop": "Example Stop A",
            "to_stop": "Example Stop B"
        },
        {
            "type": "metro",
            "from_station": "Example Station A",
            "to_station": "Example Station B"
        }
    ],
    walking_distance_m=630.7,
    transfers=1,
    data_sources=["BMTC GTFS", "Metro GTFS"],
    limitations=["Scheduled transit data only"]
)

print("TEST JOURNEY")
print(sample)

print("\nVALIDATION")
print(validate_journey(sample))
