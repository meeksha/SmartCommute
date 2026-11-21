from pathlib import Path

path = Path("app/routing/recommendation_engine.py")
content = path.read_text(encoding="utf-8")

old_import = (
    "from app.routing.bmtc_latest_planner import "
    "plan_bmtc_latest_from_gps"
)

new_import = (
    old_import
    + "\nfrom app.routing.bmtc_fares import calculate_bmtc_journey_fare"
)

if "from app.routing.bmtc_fares import" not in content:
    if old_import not in content:
        raise SystemExit("BMTC planner import not found. No changes made.")
    content = content.replace(old_import, new_import, 1)

old_block = '''            recommendations.append({
                "mode": "BMTC Bus",
                "duration_minutes": best[
                    "total_estimated_duration_minutes"
                ],
                "distance_walking_m": (
                    best["origin_access"]["distance_m"]
                    + best["destination_egress"]["distance_m"]
                ),
                "data_type": "2026-2027 BMTC scheduled timetable",
                "details": bmtc
            })
'''

new_block = '''            bmtc_fare = calculate_bmtc_journey_fare(
                best["bmtc_journey"].get("legs", [])
            )

            recommendations.append({
                "mode": "BMTC Bus",
                "duration_minutes": best[
                    "total_estimated_duration_minutes"
                ],
                "distance_walking_m": (
                    best["origin_access"]["distance_m"]
                    + best["destination_egress"]["distance_m"]
                ),
                "fare": bmtc_fare,
                "data_type": "2026-2027 BMTC scheduled timetable",
                "details": bmtc
            })
'''

if old_block not in content:
    raise SystemExit("BMTC recommendation block not found. No changes made.")

content = content.replace(old_block, new_block, 1)

old_print = '''        if option.get("fare") and option["fare"].get("status") == "success":
            fare = option["fare"]
            print("Metro distance:", fare["distance_km"], "km")
            print("Token fare: Rs.", fare["token_fare_inr"])
            print("Smart Card / QR fare: Rs.", fare["smart_card_qr_fare_inr"])
'''

new_print = '''        if option.get("fare") and option["fare"].get("status") == "success":
            fare = option["fare"]

            if option["mode"] == "Walking + Metro":
                print("Metro distance:", fare["distance_km"], "km")
                print("Token fare: Rs.", fare["token_fare_inr"])
                print("Smart Card / QR fare: Rs.", fare["smart_card_qr_fare_inr"])

            elif option["mode"] == "BMTC Bus":
                for leg in fare["legs"]:
                    print(
                        "Route", leg.get("route"),
                        "fare: Rs.", leg.get("fare_inr")
                    )
                print("Total BMTC fare: Rs.", fare["total_fare_inr"])
'''

if old_print not in content:
    raise SystemExit("Fare display block not found. No changes made.")

content = content.replace(old_print, new_print, 1)

path.write_text(content, encoding="utf-8")
print("BMTC fare integration completed.")
