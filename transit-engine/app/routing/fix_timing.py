from pathlib import Path

path = Path("app/routing/planner.py")
code = path.read_text(encoding="utf-8")

old = '''    metro_start = start + timedelta(minutes=access_minutes)

    metro_result = plan_metro(
'''

new = '''    raw_metro_start = start + timedelta(minutes=access_minutes)

    # Round UP to the next minute to avoid impossible early departures.
    metro_start = raw_metro_start.replace(second=0, microsecond=0)

    if metro_start < raw_metro_start:
        metro_start += timedelta(minutes=1)

    metro_result = plan_metro(
'''

if old not in code:
    raise SystemExit("Expected code block not found. No changes made.")

path.write_text(code.replace(old, new, 1), encoding="utf-8")
print("Walking-to-Metro timing correction applied.")
