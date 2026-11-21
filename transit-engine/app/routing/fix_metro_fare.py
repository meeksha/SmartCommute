from pathlib import Path

path = Path("app/routing/planner.py")
content = path.read_text(encoding="utf-8")

target = '''    return {
        "status": "success",
        "travel_date": travel_date,
'''

replacement = '''    metro_fare = calculate_metro_journey_fare(
        metro_result.get("legs", [])
    )

    return {
        "status": "success",
        "travel_date": travel_date,
'''

if '"metro_fare": metro_fare,' in content:
    print("Fare output field already exists.")

if target not in content:
    raise SystemExit("Could not find the expected success return block. No changes made.")

content = content.replace(target, replacement, 1)
path.write_text(content, encoding="utf-8")

print("Metro fare calculation inserted.")
