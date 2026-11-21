from app.routing.bmtc_stop_matcher import find_nearby_bmtc_stops

latitude = 12.9716
longitude = 77.5946

result = find_nearby_bmtc_stops(
    latitude,
    longitude,
    radius_m=2000,
    limit=5
)

print("BENGALURU GPS TEST")
print("==================")
print("Status:", result["status"])

for stop in result["matches"]:
    print(
        stop["stop_name"],
        "|", stop["stop_id"],
        "|", stop["straight_line_distance_m"], "m"
    )

if not result["matches"]:
    print("Nearest candidate:", result["nearest_candidate"])
