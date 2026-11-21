import unittest
from unittest.mock import patch
from app.routing.three_mode_adapter import adapt_bmtc_metro_bmtc


class FareAdapterTests(unittest.TestCase):
    def sample(self):
        return {"status": "success", "total_duration_minutes": 100, "walking_m": 300,
            "legs": [
                {"mode": "BMTC feeder", "journey": {"bmtc_journey": {"legs": [{"trip_id": "b1"}]},
                    "origin_access": {"distance_m": 50}, "destination_egress": {"distance_m": 50}}},
                {"mode": "Metro", "journey": {"legs": [{"trip_id": "m1", "from_stop": "A", "to_stop": "B"}]}},
                {"mode": "BMTC feeder", "journey": {"bmtc_journey": {"legs": [{"trip_id": "b2"}]},
                    "origin_access": {"distance_m": 100}, "destination_egress": {"distance_m": 100}}},
            ]}

    @patch("app.routing.three_mode_adapter.calculate_three_mode_emissions", return_value={"status": "unavailable", "message": "test"})
    def test_adapter_attaches_configured_fare(self, _mock):
        data = {"source": "Tariff data", "effective_date": "2026-11-01",
                "bmtc_feeder_fares_inr": {"1": 10, "2": 20},
                "metro_fare_key": "A|B", "metro_journey_fares_inr": {"A|B": 40}}
        adapted = adapt_bmtc_metro_bmtc(self.sample(), fare_data=data)
        self.assertEqual(adapted["fare"]["total_fare_inr"], 70)
        self.assertEqual(adapted["journey"]["fare"]["total_fare_inr"], 70)

    @patch("app.routing.three_mode_adapter.calculate_three_mode_emissions", return_value={"status": "unavailable", "message": "test"})
    def test_adapter_keeps_fare_unknown_without_tariffs(self, _mock):
        adapted = adapt_bmtc_metro_bmtc(self.sample())
        self.assertIsNone(adapted["fare"])
        self.assertIsNone(adapted["journey"]["fare"])


if __name__ == "__main__":
    unittest.main()
