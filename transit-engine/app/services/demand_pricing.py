"""Two-sided ride-hailing model built on Namma Yatri open aggregate data.

Commuter side: by hour of day, how likely a search is to get a driver quote
(availability), the expected pickup wait, and a *price-pressure* multiplier.
Driver side: average earning per completed ride, completed rides per hour and
an estimated hourly earning for an active driver.

Namma Yatri is a zero-commission platform without a published surge formula.
The price-pressure multiplier is therefore an *analytical model* of how
demand/supply imbalance and weather push effective prices (driver add-ons,
tips, cancellations), bounded to [0.9, 1.6]. It is not a Namma Yatri quote.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

NY_DIR = Path("data/processed/namma_yatri")
SOURCE = "Namma Yatri open data (city_agg_live_trends, driver EDA), Bengaluru, May 2026 aggregates"

PRICE_PRESSURE_BOUNDS = (0.90, 1.60)
DEMAND_COEF = 0.35   # +35 % per unit of excess demand index
SUPPLY_COEF = 0.50   # +50 % per unit of quote shortfall vs the daily mean


@lru_cache(maxsize=1)
def hourly_profile() -> pd.DataFrame:
    d = pd.read_csv(NY_DIR / "city_hourly_demand.csv")
    d = d[d["trip_category"] == "OneWay"]
    num = ["srch_rqst", "srch_fr_q", "srch_which_got_q", "booking", "done_ride", "earning"]
    g = d.groupby(["vehicle_type", "hour"])[num].sum()
    days = max(1, d["date"].nunique())

    allv = g.loc["All"].reindex(range(24), fill_value=0)
    out = pd.DataFrame(index=range(24))
    out["searches_per_day"] = allv["srch_rqst"] / days
    out["quote_rate"] = (allv["srch_which_got_q"] / allv["srch_fr_q"].replace(0, pd.NA)).astype(float).fillna(0)
    mean_search = out["searches_per_day"].mean()
    mean_quote = (allv["srch_which_got_q"].sum() / allv["srch_fr_q"].sum())
    out["demand_index"] = out["searches_per_day"] / mean_search
    out["supply_adequacy"] = out["quote_rate"] / mean_quote

    for vt in ("Auto", "Cab"):
        if vt in g.index.get_level_values(0):
            v = g.loc[vt].reindex(range(24), fill_value=0)
            out[f"{vt.lower()}_avg_fare_inr"] = (v["earning"] / v["done_ride"].replace(0, pd.NA)).astype(float)
            out[f"{vt.lower()}_completion_rate"] = (v["done_ride"] / v["booking"].replace(0, pd.NA)).astype(float)
            out[f"{vt.lower()}_rides_per_day"] = v["done_ride"] / days
    return out


@lru_cache(maxsize=1)
def driver_snapshot() -> dict:
    d = pd.read_csv(NY_DIR / "city_driver_availability.csv")
    out = {}
    for row in d.to_dict("records"):
        active = float(row["active_drvr"] or 0)
        out[str(row["vehicle_type"]).lower()] = {
            "active_drivers": int(active),
            "on_ride": int(row["drvr_onride"] or 0),
            "idle": int(row["drvr_notonride"] or 0),
            "utilisation": round(float(row["drvr_onride"] or 0) / active, 3) if active else None,
        }
    return out


def market_state(hour: int, weather_fx: dict | None = None) -> dict:
    weather_fx = weather_fx or {}
    p = hourly_profile().loc[int(hour) % 24]
    # Prefer the trained ward-level ML models (app/ml); fall back to the
    # analytical hourly profile if they are unavailable.
    ml = None
    try:
        from app.ml.ride_hailing_model import predict_hour
        ml = predict_hour(hour)
    except Exception:
        ml = None
    base_demand = ml["demand_index"] if ml else float(p["demand_index"])
    base_supply = ml["supply_adequacy"] if ml else float(p["supply_adequacy"])
    base_quote = ml["quote_probability"] if ml else float(p["quote_rate"])
    completion = ml["completion_rate"] if ml else None
    demand = base_demand * weather_fx.get("ride_hailing_demand_factor", 1.0)
    supply = base_supply * weather_fx.get("ride_hailing_supply_factor", 1.0)
    quote = max(0.05, min(0.99, base_quote * weather_fx.get("ride_hailing_supply_factor", 1.0)
                          / weather_fx.get("ride_hailing_demand_factor", 1.0) ** 0.5))
    raw = 1 + DEMAND_COEF * max(0.0, demand - 1) + SUPPLY_COEF * max(0.0, 1 - supply)
    lo, hi = PRICE_PRESSURE_BOUNDS
    pressure = min(hi, max(lo, raw))
    wait = round(4.0 / quote, 1)   # base 4 min pickup when a quote is certain

    drivers = driver_snapshot()
    driver_side = {}
    for vt in ("auto", "cab"):
        fare = p.get(f"{vt}_avg_fare_inr")
        rides_day = p.get(f"{vt}_rides_per_day")
        snap = drivers.get(vt, {})
        active = snap.get("active_drivers")
        rides_per_driver_hour = (float(rides_day) / active) if (active and pd.notna(rides_day)) else None
        driver_side[vt] = {
            "avg_earning_per_ride_inr": round(float(fare), 1) if pd.notna(fare) else None,
            "completion_rate": round(float(p.get(f"{vt}_completion_rate")), 3)
            if pd.notna(p.get(f"{vt}_completion_rate")) else None,
            "rides_per_active_driver_hour": round(rides_per_driver_hour, 3) if rides_per_driver_hour else None,
            "est_hourly_earning_inr": round(rides_per_driver_hour * float(fare), 1)
            if rides_per_driver_hour and pd.notna(fare) else None,
            "fleet_utilisation_snapshot": snap.get("utilisation"),
        }
    if ml:
        driver_side["all_vehicles_ml"] = {"predicted_avg_earning_per_ride_inr": round(ml["fare_per_ride"], 1),
                                          "predicted_completion_rate": round(ml["completion_rate"], 3)}

    return {
        "hour": int(hour) % 24,
        "demand_index": round(demand, 3),
        "supply_adequacy": round(supply, 3),
        "quote_probability": round(quote, 3),
        "expected_pickup_wait_min": wait,
        "price_pressure_multiplier": round(pressure, 3),
        "market_condition": ("tight" if pressure >= 1.2 else "balanced" if pressure > 1.02 else "slack"),
        "completion_probability": round(completion, 3) if completion is not None else None,
        "trip_success_probability": round(quote * completion, 3) if completion is not None else round(quote, 3),
        "driver_side": driver_side,
        "model": {
            "type": "ml" if ml else "analytical",
            "ml_version": ml["version"] if ml else None,
            "predictor": ("Gradient-boosted ward x hour models (demand, driver-quote rate, completion, fare), "
                          "MLflow-tracked; aggregated city-wide" if ml else "Hourly averages"),
            "formula": "clip(1 + 0.35*max(0, demand_index-1) + 0.5*max(0, 1-supply_adequacy), 0.9, 1.6)",
            "is_official_pricing": False,
            "note": ("Predicted demand/supply feed a bounded, transparent price-pressure rule "
                     "(prediction + constrained pricing). Not a booking quote."),
        },
        "source": SOURCE + (" + ward-level hourly trends (June 2025) for the ML models" if ml else ""),
    }


def daily_curve(weather_fx: dict | None = None) -> list[dict]:
    return [market_state(h, weather_fx) for h in range(24)]
