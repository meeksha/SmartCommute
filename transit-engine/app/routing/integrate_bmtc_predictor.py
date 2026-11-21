from pathlib import Path
import shutil

path = Path("app/routing/bmtc_planner.py")
source = path.read_text(encoding="utf-8")

import_line = "from app.routing.bmtc_duration_predictor import predict_segment_duration\n"

if import_line not in source:
    anchor = "import pandas as pd\n"
    if anchor not in source:
        raise RuntimeError("Could not find pandas import.")
    source = source.replace(anchor, anchor + import_line, 1)

anchor = '    stop_names = stops.set_index("stop_id")["stop_name"].to_dict()\n'

if anchor not in source:
    raise RuntimeError("Could not find the stop_names integration point.")

integration = '''    # Add historical duration estimates without changing timetable routing.
    estimates_by_trip = {}

    for segment in path:
        trip_id = segment["trip_id"]
        scheduled_duration = (
            segment["arrival"] - segment["departure"]
        ) / 60

        try:
            prediction = predict_segment_duration(
                route_id=segment["route_id"],
                stop_id=segment["from_stop"],
                next_stop_id=segment["to_stop"],
                departure_time=format_time(segment["departure"])
            )
        except Exception:
            prediction = {"status": "unavailable"}

        entry = estimates_by_trip.setdefault(
            trip_id,
            {
                "predicted_total": 0.0,
                "scheduled_total": 0.0,
                "successful_segments": 0,
                "total_segments": 0,
                "methods": set()
            }
        )

        entry["scheduled_total"] += scheduled_duration
        entry["total_segments"] += 1

        if prediction.get("status") == "success":
            entry["predicted_total"] += prediction[
                "predicted_duration_min"
            ]
            entry["successful_segments"] += 1
            entry["methods"].add(prediction["method"])

    stop_names = stops.set_index("stop_id")["stop_name"].to_dict()
'''

source = source.replace(anchor, integration, 1)

anchor = '''        leg["arrival_time"] = format_time(leg["arrival"])

    for index in range(1, len(legs)):
'''

replacement = '''        leg["arrival_time"] = format_time(leg["arrival"])

        estimate = estimates_by_trip.get(leg["trip_id"])

        if estimate and estimate["successful_segments"] == estimate["total_segments"]:
            leg["duration_estimate_min"] = round(
                estimate["predicted_total"], 2
            )
            leg["scheduled_segment_duration_min"] = round(
                estimate["scheduled_total"], 2
            )

            methods = sorted(estimate["methods"])
            leg["duration_estimate_method"] = (
                methods[0] if len(methods) == 1 else "mixed"
            )
            leg["duration_estimate_status"] = "success"
        else:
            leg["duration_estimate_min"] = None
            leg["scheduled_segment_duration_min"] = (
                round(estimate["scheduled_total"], 2)
                if estimate else None
            )
            leg["duration_estimate_method"] = "unavailable"
            leg["duration_estimate_status"] = "incomplete"

        leg["duration_estimate_note"] = (
            "Historical schedule estimate; does not account for "
            "live traffic or delays. Does not change scheduled journey times."
        )

    for index in range(1, len(legs)):
'''

if anchor not in source:
    raise RuntimeError("Could not find the leg annotation integration point.")

source = source.replace(anchor, replacement, 1)

backup = path.with_suffix(".py.backup")
shutil.copy2(path, backup)
path.write_text(source, encoding="utf-8")

print("BMTC planner updated successfully.")
print("Backup:", backup)
print("Existing timetable route selection preserved.")
print("Historical duration estimates added to bus legs.")
