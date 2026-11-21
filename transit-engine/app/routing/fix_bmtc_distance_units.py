from pathlib import Path

path = Path("app/routing/inspect_bmtc_emission_distance.py")
content = path.read_text(encoding="utf-8")

content = content.replace(
    'distance = (\n            float(end.iloc[0]["shape_dist_traveled"])\n            - float(start.iloc[0]["shape_dist_traveled"])\n        )\n\n        print(f"\\nRoute {route}: {distance:.3f} km")',
    'distance_m = (\n            float(end.iloc[0]["shape_dist_traveled"])\n            - float(start.iloc[0]["shape_dist_traveled"])\n        )\n        distance_km = distance_m / 1000.0\n\n        print(f"\\nRoute {route}: {distance_km:.3f} km")'
)

path.write_text(content, encoding="utf-8")
print("Distance conversion updated.")
