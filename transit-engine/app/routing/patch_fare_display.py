from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

anchor = '''        if "distance_km" in option:
            print("Distance:", option["distance_km"], "km")
'''

replacement = anchor + '''
        fare_estimates = option.get("fare_estimates")

        if fare_estimates:
            print("\\nEstimated fare references:")
            print("Route distance:", fare_estimates["distance_basis_km"], "km")

            auto = fare_estimates["auto"]
            print(
                "Auto:",
                "Rs.", auto["estimated_total_inr"]
            )

            for category, cab in fare_estimates["cab"].items():
                print(
                    "Cab", category + ":",
                    "Rs.", cab["estimated_total_inr"]
                )

            print("Fare limitations:")
            for limitation in fare_estimates["limitations"]:
                print("-", limitation)
'''

if source.count(anchor) != 1:
    raise SystemExit("Display insertion point not found. No changes made.")

backup = path.with_name(
    "recommendation_engine.py.before_fare_display.bak"
)
shutil.copy2(path, backup)

source = source.replace(anchor, replacement, 1)

source = source.replace(
    '"Taxi road routing does not verify the vehicle class or provide a live fare.",',
    '"Taxi road routing does not verify the vehicle class; fare estimates are modelled separately.",'
)

source = source.replace(
    '"Auto-specific fares, two-wheeler routing, carpool and company shuttle matching are not integrated yet."',
    '"Auto fare estimates use reported Namma Yatri distance-based pricing; Cab estimates use Karnataka notified rates. Two-wheeler routing, carpool and company shuttle matching are not integrated yet."'
)

path.write_text(source, encoding="utf-8")

print("Fare display patch applied.")
print("Backup:", backup)
