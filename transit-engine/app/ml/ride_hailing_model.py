"""Serving side of the ride-hailing ML models (see train_ride_hailing.py).

Predicts, for any hour of the day, city-wide ride-hailing conditions by
running the ward-level models for every ward and aggregating (demand-weighted):
  demand_index       searches this hour / average hourly searches
  quote_probability  chance a search gets a driver quote (supply)
  completion_rate    chance a booking is completed (not cancelled)
  fare_per_ride      average earning per completed ride (driver side)

If the trained artifact is missing or was produced by a different
scikit-learn version, it is retrained locally (a few seconds, no MLflow).
"""
from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ARTIFACT = Path("models/ride_hailing/model.joblib")
CARD = Path("models/ride_hailing/model_card.json")
_LOCK = threading.Lock()


def _sklearn_version():
    import sklearn
    return sklearn.__version__


@lru_cache(maxsize=1)
def load():
    """Return the artifact dict, retraining if needed. None if data is missing."""
    import joblib
    with _LOCK:
        art = None
        if ARTIFACT.exists():
            try:
                art = joblib.load(ARTIFACT)
                if art.get("sklearn_version") not in (None, _sklearn_version()):
                    art = None
            except Exception:
                art = None
        if art is None:
            try:
                from app.ml.train_ride_hailing import train
                train(log_to_mlflow=False)
                art = joblib.load(ARTIFACT)
            except Exception as exc:
                print(f"Ride-hailing ML model unavailable: {exc}")
                return None
        return art


def model_card() -> dict | None:
    try:
        return json.loads(CARD.read_text())
    except Exception:
        return None


@lru_cache(maxsize=1)
def hourly_curve() -> pd.DataFrame | None:
    """24-row frame of city-level predictions (cached; models are static)."""
    art = load()
    if art is None:
        return None
    wt = art["ward_table"].copy()
    rows = []
    for h in range(24):
        X = wt.assign(hour_f=float(h), hour_sin=np.sin(2 * np.pi * h / 24), hour_cos=np.cos(2 * np.pi * h / 24))
        X = X[art["features"]].astype(float)
        preds = {}
        for name, spec in art["models"].items():
            if spec["champion"] == "model":
                preds[name] = spec["model"].predict(X)
            else:
                preds[name] = np.full(len(X), spec["baseline"].get(h, np.nan))
        searches = np.clip(np.expm1(preds["demand"]), 0, None)
        w = searches if searches.sum() > 0 else np.ones(len(searches))
        quote = float(np.average(np.clip(preds["quote_rate"], 0, 1), weights=w))
        completion = float(np.average(np.clip(preds["completion"], 0, 1), weights=w))
        fare = float(np.average(preds["fare"], weights=w * np.clip(preds["completion"], 0.05, 1)))
        rows.append({"hour": h, "searches": float(searches.sum()), "quote_probability": quote,
                     "completion_rate": completion, "fare_per_ride": fare})
    df = pd.DataFrame(rows).set_index("hour")
    df["demand_index"] = df["searches"] / df["searches"].mean()
    df["supply_adequacy"] = df["quote_probability"] / np.average(df["quote_probability"], weights=df["searches"])
    return df


def predict_hour(hour: int) -> dict | None:
    df = hourly_curve()
    if df is None:
        return None
    r = df.loc[int(hour) % 24]
    card = model_card() or {}
    return {"demand_index": float(r["demand_index"]), "quote_probability": float(r["quote_probability"]),
            "completion_rate": float(r["completion_rate"]), "fare_per_ride": float(r["fare_per_ride"]),
            "supply_adequacy": float(r["supply_adequacy"]), "version": card.get("version")}
