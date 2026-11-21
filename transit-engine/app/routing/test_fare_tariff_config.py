import json, tempfile, unittest
from pathlib import Path
from app.routing.fare_tariff_config import load_fare_data
class Tests(unittest.TestCase):
 def test_blank_template_stays_unknown(self): self.assertIsNone(load_fare_data(Path(__file__).with_name('fare_tariffs.json')))
 def test_verified_fares_load(self):
  x={'source':'official tariff','effective_date':'2026-11-05','bmtc_feeder_fares_inr':{'1':15,'2':20},'metro_fare_key':'A|B','metro_journey_fares_inr':{'A|B':70}}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.json'; p.write_text(json.dumps(x),encoding='utf-8'); y=load_fare_data(p)
  self.assertEqual(y['bmtc_feeder_fares_inr'],{'1':15.0,'2':20.0}); self.assertEqual(y['metro_journey_fares_inr']['A|B'],70.0)
 def test_negative_fare_rejected(self):
  x={'source':'official','effective_date':'2026-11-05','bmtc_feeder_fares_inr':{'1':-1}}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.json'; p.write_text(json.dumps(x),encoding='utf-8')
   with self.assertRaises(ValueError): load_fare_data(p)
if __name__=='__main__': unittest.main()
