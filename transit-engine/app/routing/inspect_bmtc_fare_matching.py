from app.routing.bmtc_latest_planner import plan_bmtc_latest_from_gps
import json

result = plan_bmtc_latest_from_gps(
    origin_lat=12.9585,
    origin_lon=77.5635,
    destination_lat=13.0105,
    destination_lon=77.5540,
    travel_date="2026-11-18",
    departure_time="08:00"
)

journey = result.get("best_journey", {})
bmtc = journey.get("bmtc_journey", {})

print("\nBMTC JOURNEY FIELDS:")
print(list(bmtc.keys()) if isinstance(bmtc, dict) else type(bmtc))

print("\nFULL BMTC JOURNEY:")
print(json.dumps(bmtc, indent=2, default=str))
