"""Offline unit tests for three-mode emissions distance and aggregation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.routing.three_mode_emissions import (
    calculate_metro_journey_distance,
    calculate_three_mode_emissions,
)


class ThreeModeEmissionsTests(unittest.TestCase):
    def test_metro_shape_distance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stop_times.csv"
            pd.DataFrame([
                {"trip_id": "M1", "stop_id": "A", "stop_sequence": 1, "shape_dist_traveled": 0.0},
                {"trip_id": "M1", "stop_id": "B", "stop_sequence": 2, "shape_dist_traveled": 3.4},
            ]).to_csv(path, index=False)
            result = calculate_metro_journey_distance([
                {"trip_id": "M1", "from_stop": "A", "to_stop": "B"}
            ], path)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["distance_km"], 3.4)

    def test_missing_metro_distance_stays_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stop_times.csv"
            pd.DataFrame([
                {"trip_id": "M1", "stop_id": "A", "stop_sequence": 1, "shape_dist_traveled": 0.0},
            ]).to_csv(path, index=False)
            result = calculate_metro_journey_distance([
                {"trip_id": "M1", "from_stop": "A", "to_stop": "B"}
            ], path)
            self.assertEqual(result["status"], "unavailable")

    def test_combined_scenario_calculation(self):
        itinerary = {
            "status": "success",
            "legs": [
                {"mode": "BMTC feeder", "journey": {"bmtc_journey": {"legs": [{"trip_id": "B1"}]}}},
                {"mode": "Metro", "journey": {"legs": [{"trip_id": "M1", "from_stop": "A", "to_stop": "B"}]}},
                {"mode": "BMTC feeder", "journey": {"bmtc_journey": {"legs": [{"trip_id": "B2"}]}}},
            ],
        }
        def fake_bmtc(legs):
            return {"status": "success", "distance_km": 4.0 if legs[0]["trip_id"] == "B1" else 6.0, "legs": []}
        def fake_metro(legs, stop_times_path=None):
            return {"status": "success", "distance_km": 20.0, "legs": []}
        with patch("app.routing.three_mode_emissions.calculate_bmtc_journey_distance", side_effect=fake_bmtc), \
             patch("app.routing.three_mode_emissions.calculate_metro_journey_distance", side_effect=fake_metro):
            result = calculate_three_mode_emissions(itinerary)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["distance_km"]["bmtc_total"], 10.0)
        self.assertEqual(result["distance_km"]["metro_total"], 20.0)
        self.assertEqual(len(result["emissions_kg_co2e"]["scenarios"]), 6)
        self.assertIsNotNone(result["emissions_kg_co2e"]["reference_case"])


if __name__ == "__main__":
    unittest.main()
