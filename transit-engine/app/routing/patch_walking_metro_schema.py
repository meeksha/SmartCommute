from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

start = source.index("    # 1. Walking + Metro")
end = source.index("    # 2. BMTC", start)

replacement = '''    # 1. Walking + Metro
    try:
        metro = plan_journey(
            origin_lat,
            origin_lon,
            destination_lat,
            destination_lon,
            travel_date,
            departure_time
        )

        if metro.get("status") == "success":
            metro_distance = metro.get("metro_fare", {}).get("distance_km")

            metro_emissions = (
                calculate_emissions(metro_distance, "metro_ips")
                if metro_distance is not None else None
            )

            journeys = adapt_walking_metro(metro)

            for journey in journeys:
                journey["emissions"] = metro_emissions
                journey["fare"] = metro.get("metro_fare")

                recommendations.append({
                    "mode": journey["mode"],
                    "duration_minutes": journey["duration_minutes"],
                    "distance_walking_m": journey["walking_distance_m"],
                    "fare": journey["fare"],
                    "emissions": journey["emissions"],
                    "data_type": "Scheduled Metro + modelled walking",
                    "journey": journey,
                    "details": metro
                })

            if not journeys:
                errors.append({
                    "mode": "Walking + Metro",
                    "message": "Planner succeeded but produced no adapted journeys."
                })

        else:
            errors.append({
                "mode": "Walking + Metro",
                "message": metro.get("message", "Route unavailable")
            })

    except Exception as exc:
        errors.append({
            "mode": "Walking + Metro",
            "message": str(exc)
        })

'''

backup = path.with_name(
    "recommendation_engine.py.before_walking_metro_schema.bak"
)

shutil.copy2(path, backup)
source = source[:start] + replacement + source[end:]
path.write_text(source, encoding="utf-8")

print("Walking + Metro schema integration completed.")
print("Backup:", backup)
