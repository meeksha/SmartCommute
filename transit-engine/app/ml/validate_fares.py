"""Validate the distance-based auto fare model against observed Namma Yatri
ward averages (data from scariadon5/Namma-Yatri-Pricing-MLOPS-, MIT).

For each ward: predicted = estimate_auto_fare(average trip distance);
observed = average fare per completed trip. Reports MAPE / bias and logs a
run to MLflow (if installed). Note: ward averages mix trip lengths and some
cab trips, so this checks calibration, not individual trip accuracy.

    python -m app.ml.validate_fares
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from app.routing.namma_yatri_fares import estimate_auto_fare

DATA = Path("data/external/namma_yatri_ward_summary.csv")
OUT = Path("models/ride_hailing/fare_validation.json")


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(r"[₹,%]", "", regex=True), errors="coerce")


def validate(log_to_mlflow: bool = True) -> dict:
    d = pd.read_csv(DATA)
    d["dist"] = _num(d["Average Distance per Trip (km)"])
    d["fare"] = _num(d["Average Fare per Trip"])
    d["trips"] = _num(d["Completed Trips"])
    d = d.dropna(subset=["dist", "fare", "trips"])
    d = d[(d["trips"] >= 100) & (d["Ward"] != "Other Wards")]
    d["pred"] = d["dist"].map(lambda km: estimate_auto_fare(float(km))["estimated_total_inr"])
    err = (d["pred"] - d["fare"]) / d["fare"]
    w = d["trips"]
    res = {
        "wards": int(len(d)),
        "trip_weighted_mape_pct": round(float(np.average(err.abs(), weights=w) * 100), 1),
        "trip_weighted_bias_pct": round(float(np.average(err, weights=w) * 100), 1),
        "median_abs_error_pct": round(float(err.abs().median() * 100), 1),
        "observed_fare_per_km": round(float(np.average(d["fare"] / d["dist"], weights=w)), 2),
        "predicted_fare_per_km": round(float(np.average(d["pred"] / d["dist"], weights=w)), 2),
        "source": "github.com/scariadon5/Namma-Yatri-Pricing-MLOPS- data/raw/namma_yatri.csv (MIT)",
        "note": "Ward averages mix trip lengths and vehicle types; this checks calibration only.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2))
    if log_to_mlflow:
        try:
            import mlflow
            mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
            mlflow.set_experiment("smartcommute_fare_validation")
            with mlflow.start_run(run_name="auto_fare_vs_ward_averages"):
                mlflow.log_metrics({k: v for k, v in res.items() if isinstance(v, (int, float))})
                mlflow.log_param("data", res["source"])
        except Exception as exc:
            print(f"MLflow logging skipped: {exc}")
    print(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    validate()
