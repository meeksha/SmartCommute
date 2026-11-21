import unittest
from app.routing.fare_estimator import calculate_three_mode_fare
from app.routing.recommendation_quality import rank_journeys, _estimated_fare


def fixture_result():
    return {"status": "success", "legs": [
        {"mode": "BMTC feeder", "journey": {"bmtc_journey": {"legs": [{"trip_id": "b1"}]}}},
        {"mode": "Metro", "journey": {"legs": [
            {"trip_id": "m1", "from_stop": "EC", "to_stop": "RV"},
            {"trip_id": "m2", "from_stop": "RV", "to_stop": "YG"},
        ]}},
        {"mode": "BMTC feeder", "journey": {"bmtc_journey": {"legs": [{"trip_id": "b2"}, {"trip_id": "b3"}]}}},
    ]}


def item(mode, duration, emissions, fare=None, walking=0, transfers=0):
    return {"mode": mode, "duration_minutes": duration,
            "distance_walking_m": walking,
            "fare": {"total_fare_inr": fare} if fare is not None else None,
            "emissions": {"emissions_kg_co2e": emissions} if emissions is not None else None,
            "journey": {"legs": [{"type": "motorcycle"}],
                        "walking_distance_m": walking, "transfers": transfers}}


class FareAndRankingTests(unittest.TestCase):
    def test_fare_unknown_without_tariff_source(self):
        result = calculate_three_mode_fare(fixture_result())
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["total_fare_inr"])

    def test_fare_aggregates_two_feeders_and_one_metro_trip(self):
        result = calculate_three_mode_fare(fixture_result(), {
            "source": "Illustrative official tariff extract",
            "effective_date": "2026-11-01",
            "bmtc_feeder_fares_inr": {"1": 15, "2": 20},
            "metro_fare_key": "Electronic City|Yelahanka",
            "metro_journey_fares_inr": {"Electronic City|Yelahanka": 45},
        })
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_fare_inr"], 80)
        self.assertEqual(len(result["components"]), 3)

    def test_partial_fare_never_presented_as_total(self):
        result = calculate_three_mode_fare(fixture_result(), {
            "source": "Tariff file", "bmtc_feeder_fares_inr": {"1": 15}
        })
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["total_fare_inr"])
        self.assertEqual(result["known_components_subtotal_inr"], 15)

    def test_green_first_bus_beats_higher_emission_motorcycle(self):
        bus = item("BMTC Bus", 124, 1.40, 95, 297, 1)
        bike = item("Private Two-Wheeler", 60, 2.17, None)
        ranked = rank_journeys([bus, bike], profile="green_first")
        self.assertEqual(ranked[0]["mode"], "BMTC Bus")

    def test_balanced_can_choose_faster_private_vehicle_when_cost_known(self):
        bus = item("BMTC Bus", 124, 1.40, 95, 297, 1)
        bike = item("Private Two-Wheeler", 60, 2.17, 35)
        ranked = rank_journeys([bus, bike], profile="balanced")
        self.assertEqual(ranked[0]["mode"], "Private Two-Wheeler")

    def test_missing_fare_not_zero_and_fuel_cost_not_mislabeled_as_fare(self):
        vehicle = item("Private Car", 65, 5.0)
        vehicle["operating_cost"] = {"fuel_cost_inr": 120}
        self.assertEqual(_estimated_fare(vehicle), (None, None))
        ranked = rank_journeys([vehicle], profile="green_first")
        self.assertEqual(ranked[0]["fare_status"], "unknown")
        self.assertIn("fare", ranked[0]["ranking_missing_metrics"])
        self.assertEqual(ranked[0]["ranking_breakdown"]["fare"], 0.5)

    def test_fixed_scores_do_not_shift_when_outlier_added(self):
        bike = item("Private Two-Wheeler", 60, 2.17)
        base = rank_journeys([bike], profile="green_first")[0]["ranking_score"]
        taxi = item("Taxi", 65, 10.5, 900)
        with_outlier = rank_journeys([bike, taxi], profile="green_first")
        bike_score = next(x["ranking_score"] for x in with_outlier if x["mode"] == "Private Two-Wheeler")
        self.assertEqual(base, bike_score)


if __name__ == "__main__":
    unittest.main()
