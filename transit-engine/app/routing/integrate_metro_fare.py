from pathlib import Path

path = Path("app/routing/recommendation_engine.py")
content = path.read_text(encoding="utf-8")

old = '''                "distance_walking_m": metro[
                    "total_estimated_walking_metres"
                ],
                "data_type": "Scheduled Metro + modelled walking",
'''

new = '''                "distance_walking_m": metro[
                    "total_estimated_walking_metres"
                ],
                "fare": metro.get("metro_fare"),
                "data_type": "Scheduled Metro + modelled walking",
'''

if old not in content:
    raise SystemExit("Could not find the Metro recommendation block. No changes made.")

content = content.replace(old, new, 1)

old_print = '''        if "distance_walking_m" in option:
            print("Walking:", option["distance_walking_m"], "m")
'''

new_print = '''        if "distance_walking_m" in option:
            print("Walking:", option["distance_walking_m"], "m")

        if option.get("fare") and option["fare"].get("status") == "success":
            fare = option["fare"]
            print("Metro distance:", fare["distance_km"], "km")
            print("Token fare: Rs.", fare["token_fare_inr"])
            print("Smart Card / QR fare: Rs.", fare["smart_card_qr_fare_inr"])
'''

if old_print not in content:
    raise SystemExit("Could not find the output display block. No changes made.")

content = content.replace(old_print, new_print, 1)
path.write_text(content, encoding="utf-8")

print("Metro fare display integrated.")
