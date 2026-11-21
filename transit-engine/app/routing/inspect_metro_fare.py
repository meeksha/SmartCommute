from app.routing.planner import plan_journey
import json

result = plan_journey(
    origin_lat=12.9585,
    origin_lon=77.5635,
    destination_lat=13.0105,
    destination_lon=77.5540,
    travel_date="2026-11-18",
    departure_time="08:00"
)

print("\nMETRO JOURNEY DETAILS:")
print(json.dumps(result.get("metro_journey", {}), indent=2, default=str))
