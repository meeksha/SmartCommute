from pathlib import Path

path = Path("app/services/carbon.py")
content = path.read_text(encoding="utf-8")

old = '''    return {
        "vehicle_type": vehicle_type,
        "distance_km": round(distance_km, 3),'''

new = '''    return {
        "status": "success",
        "vehicle_type": vehicle_type,
        "distance_km": round(distance_km, 3),'''

if old not in content:
    raise SystemExit("Expected return block not found. No changes made.")

content = content.replace(old, new, 1)
path.write_text(content, encoding="utf-8")

print("Carbon status field added.")
