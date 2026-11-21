from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

old_loop = '''    for mode, label in [
        ("car", "Private Car"),
        ("taxi", "Taxi / Cab (vehicle class unverified)")
    ]:
'''

new_loop = '''    for mode, label in [
        ("car", "Private Car"),
        ("taxi", "Taxi / Cab (vehicle class unverified)"),
        ("motorcycle", "Private Two-Wheeler")
    ]:
'''

if source.count(old_loop) != 1:
    raise SystemExit("Road mode loop not found exactly once. No changes made.")

source = source.replace(old_loop, new_loop, 1)

old_vehicle = '''            vehicle_type = (
                "private_car_petrol"
                if mode == "car"
                else "ride_hailing_diesel"
            )
'''

new_vehicle = '''            vehicle_type = {
                "car": "private_car_petrol",
                "taxi": "ride_hailing_diesel",
                "motorcycle": "private_motorcycle_petrol"
            }[mode]
'''

if source.count(old_vehicle) != 1:
    raise SystemExit("Vehicle emissions mapping not found. No changes made.")

source = source.replace(old_vehicle, new_vehicle, 1)

old_fare = '''            if mode == "taxi":
                route_distance = road["distance_km"]
'''

new_fare = '''            if mode == "taxi":
                route_distance = road["distance_km"]
'''

if source.count(old_fare) != 1:
    raise SystemExit("Taxi fare block not found. No changes made.")

# Add motorcycle-specific metadata to the recommendation.
old_append = '''                "fare_estimates": fare_estimates,
                "data_type": "TomTom live-traffic routing estimate",
                "details": road
'''

new_append = '''                "fare_estimates": fare_estimates,
                "data_type": (
                    "TomTom Routing API v1 motorcycle route"
                    if mode == "motorcycle"
                    else "TomTom live-traffic routing estimate"
                ),
                "details": road
'''

if source.count(old_append) != 1:
    raise SystemExit("Recommendation output block not found. No changes made.")

source = source.replace(old_append, new_append, 1)

# Update project limitations.
source = source.replace(
    '"Taxi road routing does not verify the vehicle class; fare estimates are modelled separately.",',
    '"Taxi road routing does not verify the vehicle class; fare estimates are modelled separately.",\n            "Motorcycle routing uses TomTom Routing API v1 beta; motorcycle restriction data may be incomplete in some areas.",'
)

source = source.replace(
    '"Auto fare estimates use reported Namma Yatri distance-based pricing; Cab estimates use Karnataka notified rates. Two-wheeler routing, carpool and company shuttle matching are not integrated yet."',
    '"Auto fare estimates use reported Namma Yatri distance-based pricing; Cab estimates use Karnataka notified rates. Two-wheeler routing is integrated, but two-wheeler operating-cost estimates, carpool and company shuttle matching are not yet integrated."'
)

backup = path.with_name(
    "recommendation_engine.py.before_motorcycle_integration.bak"
)
shutil.copy2(path, backup)

path.write_text(source, encoding="utf-8")

print("Motorcycle recommendation integration applied.")
print("Backup:", backup)
