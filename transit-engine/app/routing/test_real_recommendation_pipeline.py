"""Run the full commute recommendation orchestration on a real Bengaluru trip.

This is an integration/diagnostic runner, not a mocked unit test. It invokes the
actual walking+Metro, BMTC, BMTC+Metro and TomTom branches configured in the app.
Unavailable providers are reported rather than hidden.
"""
from __future__ import annotations

from app.routing.recommendation_engine import get_recommendations


ORIGIN = (13.0107901, 77.5548862)       # Orion Mall
DESTINATION = (13.0218597, 77.5671423)  # IISc Main Building
TRAVEL_DATE = "2026-11-18"
DEPARTURE_TIME = "09:00"


def run_real_pipeline():
    result = get_recommendations(
        origin_lat=ORIGIN[0],
        origin_lon=ORIGIN[1],
        destination_lat=DESTINATION[0],
        destination_lon=DESTINATION[1],
        travel_date=TRAVEL_DATE,
        departure_time=DEPARTURE_TIME,
    )

    print("\nREAL MULTIMODAL RECOMMENDATION PIPELINE")
    print("========================================")
    print(f"Trip: Orion Mall -> IISc Main Building")
    print(f"Date/time: {TRAVEL_DATE} {DEPARTURE_TIME}")
    print(f"Status: {result.get('status')}")
    print(f"Raw candidates: {result.get('raw_candidate_count', 0)}")
    print(f"Accepted recommendations: {result.get('comparison_count', 0)}")
    print(f"Rejected by quality filters: {len(result.get('rejected_recommendations', []))}")
    print(f"Duplicates removed: {len(result.get('duplicate_recommendations_removed', []))}")

    print("\nRANKED RECOMMENDATIONS")
    for item in result.get("recommendations", []):
        metrics = item.get("ranking_metrics", {})
        print(
            f"#{item.get('rank')} {item.get('mode')} | "
            f"{item.get('duration_minutes')} min | "
            f"walk={metrics.get('walking')} m | "
            f"fare={metrics.get('fare')} INR | "
            f"emissions={metrics.get('emissions')} kg CO2e | "
            f"score={item.get('ranking_score')}"
        )
        print(f"   breakdown={item.get('ranking_breakdown')}")

    print("\nREJECTED CANDIDATES AND REASONS")
    for item in result.get("rejected_recommendations", []):
        print(
            f"{item.get('mode')} | {item.get('duration_minutes')} min | "
            f"walking={item.get('walking')}"
        )
        for reason in item.get("reasons", []):
            print(f"   - {reason}")

    print("\nDUPLICATES REMOVED")
    for item in result.get("duplicate_recommendations_removed", []):
        print(f"{item.get('mode')} | {item.get('duration_minutes')} min | {item.get('reason')}")

    print("\nPROVIDER / PLANNER ERRORS")
    for error in result.get("errors", []):
        print(f"{error.get('mode')}: {error.get('message')}")

    # Structural assertions: any returned recommendation must have completed
    # filtering and ranking, rather than being a raw planner result.
    for item in result.get("recommendations", []):
        assert isinstance(item.get("rank"), int)
        assert isinstance(item.get("ranking_score"), (int, float))
        assert isinstance(item.get("ranking_metrics"), dict)
        assert isinstance(item.get("ranking_breakdown"), dict)

    if result.get("status") == "success":
        assert result.get("recommendations"), "success status requires ranked recommendations"
    else:
        print("\nNOTE: No final recommendations were produced. Check provider errors above;")
        print("      this is not evidence that the quality layer failed.")

    return result


if __name__ == "__main__":
    run_real_pipeline()
