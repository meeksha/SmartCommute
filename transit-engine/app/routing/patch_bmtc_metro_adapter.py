from pathlib import Path
import shutil

path = Path("app/routing/journey_adapters.py")
source = path.read_text(encoding="utf-8")

start = source.index("def adapt_bmtc_metro_journeys(")

replacement = '''def adapt_bmtc_metro_journeys(result):
    """Convert actual BMTC + Metro planner results."""

    if result.get("status") != "success":
        return []

    candidates = []

    if result.get("best_journey"):
        candidates.append(result["best_journey"])

    candidates.extend(
        result.get("alternative_journeys", [])
    )

    journeys = []

    for candidate in candidates:
        bmtc = candidate.get("bmtc_journey", {})
        metro = candidate.get("metro_journey", {})

        bus_legs = bmtc.get("legs", [])
        metro_legs = metro.get("legs", [])

        interchange = candidate.get("interchange", {})
        destination_metro = candidate.get(
            "destination_metro", {}
        )

        total_walking = candidate.get(
            "total_estimated_walking_metres"
        )

        interchange_walking = interchange.get(
            "walking_distance_m"
        )

        destination_walking = destination_metro.get(
            "walking_distance_m"
        )

        origin_walking = None

        if (
            total_walking is not None
            and interchange_walking is not None
            and destination_walking is not None
        ):
            origin_walking = round(
                total_walking
                - interchange_walking
                - destination_walking,
                1
            )

            if origin_walking < 0:
                raise ValueError(
                    "Walking-distance components exceed total walking."
                )

        legs = [
            {
                "type": "walking",
                "segment": "origin_access",
                "distance_m": origin_walking,
                "details": {
                    "source": "Derived from planner walking-distance total"
                }
            }
        ]

        legs.extend(
            _tag_legs(bus_legs, "bmtc_bus")
        )

        legs.append({
            "type": "walking",
            "segment": "bmtc_metro_interchange",
            "distance_m": interchange_walking,
            "details": interchange
        })

        legs.extend(
            _tag_legs(metro_legs, "metro")
        )

        legs.append({
            "type": "walking",
            "segment": "destination_egress",
            "distance_m": destination_walking,
            "details": destination_metro
        })

        transfers = (
            max(0, len(bus_legs) - 1)
            + 1
            + max(0, len(metro_legs) - 1)
        )

        journey = build_journey(
            mode="BMTC + Metro",
            duration_minutes=candidate.get(
                "total_estimated_duration_minutes"
            ),
            legs=legs,
            walking_distance_m=total_walking,
            fare=candidate.get("fare"),
            emissions=candidate.get("emissions"),
            transfers=transfers,
            data_sources=["BMTC GTFS", "Metro GTFS", "OSM walking network"],
            limitations=[
                candidate.get("data_warning", ""),
                *result.get("limitations", [])
            ],
            raw_details=candidate
        )

        journeys.append(journey)

    return journeys
'''

# Replace only this function, preserving the rest of the file.
source = source[:start] + replacement

backup = path.with_name(
    "journey_adapters.py.before_bmtc_metro_fix.bak"
)

shutil.copy2(path, backup)
path.write_text(source, encoding="utf-8")

print("BMTC + Metro adapter corrected.")
print("Backup:", backup)
