from pathlib import Path

path = Path("app/routing/test_real_journey_adapters.py")
source = path.read_text(encoding="utf-8")

replacements = {
    "ORIGIN_LAT = 12.9585": "ORIGIN_LAT = 13.0107901",
    "ORIGIN_LON = 77.5635": "ORIGIN_LON = 77.5548862",
    "DESTINATION_LAT = 13.0105": "DESTINATION_LAT = 13.0218597",
    "DESTINATION_LON = 77.5540": "DESTINATION_LON = 77.5671423",
    'TRAVEL_DATE = "2026-11-18"': 'TRAVEL_DATE = "2026-11-18"',
    'DEPARTURE_TIME = "08:00"': 'DEPARTURE_TIME = "09:00"',
}

for old, new in replacements.items():
    if old not in source:
        raise RuntimeError(f"Could not find expected setting: {old}")
    source = source.replace(old, new, 1)

path.write_text(source, encoding="utf-8")
print("Test configured for Orion Mall -> IISc at 09:00.")
