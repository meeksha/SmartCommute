"""Diagnose Metro access/egress distances for a commute pair.

Run from the project root:
  python -m app.routing.diagnose_metro_last_mile

This is diagnostic only: it does not alter routing or relax walking limits.
"""
from app.routing.planner import load_walking_data, nearest_reachable_stations

ORIGIN = (12.84684, 77.67042)       # Electronic City representative point
DESTINATION = (13.10073, 77.59632)  # Yelahanka representative point


def show_candidates(label, coords, graph, stations, entrances):
    print(f"\n{label}")
    print("-" * len(label))
    candidates = nearest_reachable_stations(
        coords[0], coords[1], graph, stations, entrances, limit=10
    )
    for index, item in enumerate(candidates, 1):
        print(
            f"{index:>2}. {item['station_name']} | "
            f"walk={item['walking_distance_m']:.1f} m | "
            f"{item['walking_minutes']:.1f} min | "
            f"entrance={item.get('entrance_name', 'unknown')}"
        )
    nearest = candidates[0]
    if nearest["walking_distance_m"] > 1800:
        print(
            "DIAGNOSIS: nearest station exceeds the configured 1,800 m "
            "egress limit. A walk-only Metro journey is not a viable "
            "last-mile option for this destination. Do not relax the limit; "
            "a scheduled BMTC feeder leg or another last-mile mode is needed."
        )
    else:
        print("DIAGNOSIS: at least one station is within the 1,800 m limit.")
    return candidates


def main():
    print("METRO LAST-MILE DIAGNOSTIC")
    print("Origin: Electronic City", ORIGIN)
    print("Destination: Yelahanka", DESTINATION)
    graph, stations, entrances = load_walking_data()
    show_candidates("ORIGIN STATION CANDIDATES", ORIGIN, graph, stations, entrances)
    show_candidates("DESTINATION STATION CANDIDATES", DESTINATION, graph, stations, entrances)
    print("\nDiagnostic complete. No project files or routing behaviour were changed.")


if __name__ == "__main__":
    main()
