from app.routing.recommendation_engine import get_recommendations

ORIGIN = (12.84684, 77.67042)       # Electronic City
DESTINATION = (13.10073, 77.59632)  # Yelahanka
TRAVEL_DATE = "2026-11-18"
DEPARTURE_TIME = "09:00"

def run():
    print("\nELECTRONIC CITY -> YELAHANKA")
    print("=" * 60)
    print("Test module:", __file__)
    print("Origin:", ORIGIN)
    print("Destination:", DESTINATION)
    print("Date:", TRAVEL_DATE)
    print("Departure:", DEPARTURE_TIME)

    result = get_recommendations(
        origin_lat=ORIGIN[0],
        origin_lon=ORIGIN[1],
        destination_lat=DESTINATION[0],
        destination_lon=DESTINATION[1],
        travel_date=TRAVEL_DATE,
        departure_time=DEPARTURE_TIME,
    )

    print("\nPIPELINE SUMMARY")
    print("Status:", result.get("status"))
    print("Raw candidates:", result.get("raw_candidate_count", 0))
    print("Accepted:", result.get("comparison_count", 0))
    print("Rejected:", len(result.get("rejected_recommendations", [])))
    print("Duplicates removed:",
          len(result.get("duplicate_recommendations_removed", [])))

    print("\nFINAL RANKING")
    for item in result.get("recommendations", []):
        metrics = item.get("ranking_metrics", {})
        print(
            f"\n#{item.get('rank')} {item.get('mode')}"
            f" | Duration: {item.get('duration_minutes')} min"
            f" | Walking: {metrics.get('walking')} m"
            f" | Fare: {metrics.get('fare')} INR"
            f" | Emissions: {metrics.get('emissions')} kg CO2e"
            f" | Score: {item.get('ranking_score')}"
        )
        print("Ranking breakdown:", item.get("ranking_breakdown"))

        journey = item.get("journey", {})
        for leg in journey.get("legs", []):
            print("  LEG:", leg)

    print("\nREJECTION SUMMARY")
    for item in result.get("rejected_recommendations", []):
        print(
            item.get("mode"),
            "|",
            item.get("duration_minutes"),
            "min |",
            item.get("reasons")
        )

    print("\nPROVIDER / PLANNER ERRORS")
    for error in result.get("errors", []):
        print(error)

    if result.get("status") != "success":
        raise RuntimeError("Recommendation pipeline did not succeed.")

    if not result.get("recommendations"):
        raise RuntimeError("No recommendations were produced.")

    print("\nELECTRONIC CITY -> YELAHANKA TEST COMPLETED")
    return result

if __name__ == "__main__":
    run()
