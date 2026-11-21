"""Tests that three-mode adapter attaches emissions without inventing values."""
import unittest
from unittest.mock import patch

from app.routing.three_mode_adapter import adapt_bmtc_metro_bmtc


class ThreeModeEmissionsAdapterTests(unittest.TestCase):
    def _result(self):
        return {
            "status": "success",
            "total_duration_minutes": 137.3,
            "walking_m": 361.1,
            "legs": [
                {"mode": "BMTC feeder", "journey": {
                    "bmtc_journey": {"legs": [{"trip_id": "B1"}]},
                    "origin_access": {"distance_m": 37.5, "walking_minutes": 1},
                    "destination_egress": {"distance_m": 70.3, "walking_minutes": 2},
                }},
                {"mode": "Metro", "journey": {"legs": [
                    {"trip_id": "M1", "from_stop": "A", "to_stop": "B"}
                ]}},
                {"mode": "BMTC feeder", "journey": {
                    "bmtc_journey": {"legs": [{"trip_id": "B2"}]},
                    "origin_access": {"distance_m": 100.2, "walking_minutes": 2},
                    "destination_egress": {"distance_m": 153.1, "walking_minutes": 3},
                }},
            ],
        }

    def test_successful_emissions_attached_to_recommendation(self):
        emissions = {
            "status": "success",
            "distance_km": {"bmtc_total": 10.0, "metro_total": 20.0, "combined_motorized": 30.0},
            "emissions_kg_co2e": {
                "reference_case": 1.2,
                "reference_case_label": "Illustrative case",
                "minimum_scenario": 0.8,
                "maximum_scenario": 1.5,
                "scenarios": {
                    "case_a": {"total_emissions_kg_co2e": 1.2}
                },
            },
            "limitations": ["Fleet mix is not verified."],
        }
        with patch("app.routing.three_mode_adapter.calculate_three_mode_emissions", return_value=emissions):
            adapted = adapt_bmtc_metro_bmtc(self._result())
        self.assertIsNotNone(adapted)
        self.assertEqual(adapted["emissions"]["status"], "success")
        self.assertEqual(adapted["journey"]["emissions"]["emissions_kg_co2e"]["reference_case"], 1.2)
        self.assertEqual(adapted["journey"]["distance_km"], 30.0)
        self.assertEqual(adapted["emissions"]["scenarios"]["case_a"]["total_emissions_kg_co2e"], 1.2)
        self.assertIsNone(adapted["fare"])

    def test_unavailable_emissions_remain_unknown(self):
        unavailable = {"status": "unavailable", "message": "GTFS shape distance missing."}
        with patch("app.routing.three_mode_adapter.calculate_three_mode_emissions", return_value=unavailable):
            adapted = adapt_bmtc_metro_bmtc(self._result())
        self.assertIsNone(adapted["emissions"])
        self.assertIsNone(adapted["journey"]["emissions"])
        self.assertIn("unavailable", adapted["limitations"][0].lower())


if __name__ == "__main__":
    unittest.main()
