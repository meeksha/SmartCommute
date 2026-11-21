"""Load explicitly verified BMTC/BMRCL fares; missing fares stay unknown."""
import json
from pathlib import Path
DEFAULT_PATH = Path(__file__).with_name("fare_tariffs.json")
def load_fare_data(path=None):
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists(): return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict): raise ValueError("Fare tariff file must be a JSON object")
    source, date = str(raw.get("source") or "").strip(), str(raw.get("effective_date") or "").strip()
    if not source or source.startswith("REPLACE") or not date or date == "YYYY-MM-DD": return None
    def clean(table):
        result = {}
        for key, value in (table or {}).items():
            if value is None: continue
            if isinstance(value, bool) or not isinstance(value, (int, float)): continue
            if value < 0: raise ValueError("Fare cannot be negative")
            result[str(key)] = float(value)
        return result
    bmtc = clean(raw.get("bmtc_feeder_fares_inr")); metro = clean(raw.get("metro_journey_fares_inr"))
    if not bmtc and not metro: return None
    return {"source": source, "effective_date": date, "bmtc_feeder_fares_inr": bmtc,
            "metro_fare_key": raw.get("metro_fare_key"), "metro_journey_fares_inr": metro}
