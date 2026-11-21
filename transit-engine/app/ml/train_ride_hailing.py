"""Ride-hailing demand/supply models with MLflow tracking (MLOps pipeline).

Pattern adapted from scariadon5/Namma-Yatri-Pricing-MLOPS- (MIT): train ->
track in MLflow -> save a versioned artifact -> serve it from FastAPI. Unlike
that repo (one row per ward, predicting a ward's average fare from its average
distance), this trains on ward x hour data, so the models learn *time-varying*
demand and driver supply, which is what dynamic pricing needs.

Data: Namma Yatri open data, ward-level hourly trends (244 wards x 24 h x
3 days, June 2025) + ward driver availability snapshot.

Targets (one model each, sample-weighted by the relevant volume):
  demand       log1p(searches) per ward-hour
  quote_rate   searches that got a driver quote / searches for quotes
  completion   completed rides / bookings
  fare         earnings per completed ride (INR)

Evaluation: train on the first two dates, test on the last (unseen) date.
Each model must beat an hour-of-day baseline (the method the app used before)
on the test day to become "champion"; otherwise the baseline is served.

Run from the transit-engine folder:
    python -m app.ml.train_ride_hailing
    mlflow ui --backend-store-uri sqlite:///mlflow.db     # browse runs
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

NY = Path("data/processed/namma_yatri")
OUT_DIR = Path("models/ride_hailing")
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")
EXPERIMENT = "smartcommute_ride_hailing"

TARGETS = {
    "demand": {"weight": None, "desc": "log1p(searches) per ward-hour"},
    "quote_rate": {"weight": "srch_fr_q", "desc": "share of quote searches that got a driver quote"},
    "completion": {"weight": "booking", "desc": "completed rides / bookings"},
    "fare": {"weight": "done_ride", "desc": "earnings per completed ride (INR)"},
}
FEATURES = ["hour_sin", "hour_cos", "hour_f", "ward_log_volume", "ward_log_drivers", "ward_onride_share",
            "ward_quote_rate", "ward_fare"]
PARAMS = {"max_iter": 300, "learning_rate": 0.06, "max_leaf_nodes": 31, "min_samples_leaf": 40,
          "l2_regularization": 1.0, "random_state": 42}


def load_frame():
    d = pd.read_csv(NY / "ward_hourly_demand.csv")
    d["hour"] = d["hour"].astype(int)
    d["date"] = d["date"].astype(str)
    drivers = pd.read_csv(NY / "ward_driver_availability.csv")
    dv = drivers.groupby("ward_num")[["active_drvr", "drvr_onride"]].sum()
    dv["ward_log_drivers"] = np.log1p(dv["active_drvr"])
    dv["ward_onride_share"] = (dv["drvr_onride"] / dv["active_drvr"].replace(0, np.nan)).fillna(0)
    d = d.merge(dv[["ward_log_drivers", "ward_onride_share"]], left_on="ward_num", right_index=True, how="left")
    d[["ward_log_drivers", "ward_onride_share"]] = d[["ward_log_drivers", "ward_onride_share"]].fillna(0)
    d["hour_f"] = d["hour"].astype(float)
    d["hour_sin"] = np.sin(2 * np.pi * d["hour"] / 24)
    d["hour_cos"] = np.cos(2 * np.pi * d["hour"] / 24)
    d["demand"] = np.log1p(d["srch_rqst"])
    d["quote_rate"] = d["srch_which_got_q"] / d["srch_fr_q"].replace(0, np.nan)
    d["completion"] = d["done_ride"] / d["booking"].replace(0, np.nan)
    d["fare"] = d["earning"] / d["done_ride"].replace(0, np.nan)
    d.loc[(d["fare"] < 20) | (d["fare"] > 2000), "fare"] = np.nan    # obvious data errors
    return d


def ward_features(train: pd.DataFrame) -> pd.DataFrame:
    """Per-ward profile computed from TRAINING dates only (no test leakage)."""
    days = train["date"].nunique()
    g = train.groupby("ward_num")
    wf = pd.DataFrame({
        "ward_log_volume": np.log1p(g["srch_rqst"].sum() / days),
        "ward_quote_rate": (g["srch_which_got_q"].sum() / g["srch_fr_q"].sum().replace(0, np.nan)),
        "ward_fare": (g["earning"].sum() / g["done_ride"].sum().replace(0, np.nan)),
    })
    wf["ward_quote_rate"] = wf["ward_quote_rate"].fillna(wf["ward_quote_rate"].median())
    wf["ward_fare"] = wf["ward_fare"].clip(50, 600).fillna(wf["ward_fare"].median())
    return wf


def _metrics(y, p, w):
    return {"rmse": float(math.sqrt(mean_squared_error(y, p, sample_weight=w))),
            "mae": float(mean_absolute_error(y, p, sample_weight=w)),
            "r2": float(r2_score(y, p, sample_weight=w))}


def train(log_to_mlflow: bool = True) -> dict:
    t0 = time.time()
    d = load_frame()
    dates = sorted(d["date"].unique())
    train_dates, test_date = dates[:-1], dates[-1]
    tr, te = d[d["date"].isin(train_dates)].copy(), d[d["date"] == test_date].copy()
    wf = ward_features(tr)
    tr = tr.drop(columns=[c for c in wf.columns if c in tr], errors="ignore").merge(wf, left_on="ward_num", right_index=True)
    te = te.merge(wf, left_on="ward_num", right_index=True, how="inner")

    mlflow = None
    if log_to_mlflow:
        try:
            import mlflow as _mlflow
            mlflow = _mlflow
            mlflow.set_tracking_uri(MLFLOW_URI)
            mlflow.set_experiment(EXPERIMENT)
        except Exception as exc:  # MLflow optional: training still works
            print(f"MLflow unavailable ({exc}); training without tracking.")
            mlflow = None

    card = {"trained_at": datetime.now(timezone.utc).isoformat(), "data": {
        "source": "Namma Yatri open data: ward-level hourly trends + ward driver availability",
        "train_dates": train_dates, "test_date": test_date, "wards": int(d["ward_num"].nunique()),
        "rows": int(len(d))}, "features": FEATURES, "params": PARAMS, "targets": {}, "mlflow": None}
    models = {}

    parent = mlflow.start_run(run_name=f"ride_hailing_{datetime.now():%Y%m%d_%H%M}") if mlflow else None
    try:
        if mlflow:
            mlflow.log_params({**PARAMS, "train_dates": ",".join(train_dates), "test_date": test_date,
                               "features": ",".join(FEATURES)})
        for name, spec in TARGETS.items():
            wcol = spec["weight"]
            a = tr.dropna(subset=[name])
            b = te.dropna(subset=[name])
            if wcol:
                a, b = a[a[wcol] > 0], b[b[wcol] > 0]
            wa = a[wcol].to_numpy() if wcol else None
            wb = b[wcol].to_numpy() if wcol else None
            # Baseline = hour-of-day (weighted) mean from training days: what the app used before.
            if wcol:
                base_tab = (a[name] * a[wcol]).groupby(a["hour"]).sum() / a[wcol].groupby(a["hour"]).sum()
            else:
                base_tab = a.groupby("hour")[name].mean()
            base_pred = b["hour"].map(base_tab).fillna(float(base_tab.mean())).to_numpy()
            model = HistGradientBoostingRegressor(**PARAMS)
            model.fit(a[FEATURES], a[name], sample_weight=wa)
            pred = model.predict(b[FEATURES])
            if name in ("quote_rate", "completion"):
                pred = np.clip(pred, 0, 1)
            m_model = _metrics(b[name], pred, wb)
            m_base = _metrics(b[name], base_pred, wb)
            champion = "model" if m_model["rmse"] < m_base["rmse"] else "baseline"
            improvement = (m_base["rmse"] - m_model["rmse"]) / m_base["rmse"] * 100 if m_base["rmse"] else 0.0
            card["targets"][name] = {"description": spec["desc"], "train_rows": int(len(a)), "test_rows": int(len(b)),
                                     "model": {k: round(v, 4) for k, v in m_model.items()},
                                     "baseline_hour_of_day": {k: round(v, 4) for k, v in m_base.items()},
                                     "rmse_improvement_pct": round(improvement, 1), "champion": champion}
            models[name] = {"model": model, "baseline": base_tab.to_dict(), "champion": champion}
            print(f"{name:<11} model RMSE {m_model['rmse']:.4f} R2 {m_model['r2']:.3f} | "
                  f"baseline RMSE {m_base['rmse']:.4f} R2 {m_base['r2']:.3f} -> champion: {champion} "
                  f"({improvement:+.1f}%)")
            if mlflow:
                with mlflow.start_run(run_name=name, nested=True):
                    mlflow.log_params({"target": name, "weight": wcol or "none"})
                    mlflow.log_metrics({f"model_{k}": v for k, v in m_model.items()})
                    mlflow.log_metrics({f"baseline_{k}": v for k, v in m_base.items()})
                    mlflow.log_metric("rmse_improvement_pct", improvement)
                    mlflow.set_tag("champion", champion)
                    try:
                        import mlflow.sklearn
                        # We created this model in this run, so its tree type is trusted.
                        mlflow.sklearn.log_model(
                            model, name="model", input_example=a[FEATURES].astype(float).head(3),
                            skops_trusted_types=[
                                "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor"])
                    except Exception as exc:
                        print(f"  (model artifact not logged to MLflow: {exc})")

        # Refit on ALL dates for serving (ward profile from all dates too).
        wf_all = ward_features(d)
        full = d.drop(columns=[c for c in wf_all.columns if c in d], errors="ignore").merge(
            wf_all, left_on="ward_num", right_index=True)
        for name, spec in TARGETS.items():
            wcol = spec["weight"]
            a = full.dropna(subset=[name])
            if wcol:
                a = a[a[wcol] > 0]
            if models[name]["champion"] == "model":
                m = HistGradientBoostingRegressor(**PARAMS)
                m.fit(a[FEATURES], a[name], sample_weight=a[wcol].to_numpy() if wcol else None)
                models[name]["model"] = m
            if wcol:
                tab = (a[name] * a[wcol]).groupby(a["hour"]).sum() / a[wcol].groupby(a["hour"]).sum()
            else:
                tab = a.groupby("hour")[name].mean()
            models[name]["baseline"] = tab.to_dict()

        drivers = pd.read_csv(NY / "ward_driver_availability.csv").groupby("ward_num")[["active_drvr", "drvr_onride"]].sum()
        ward_table = wf_all.join(pd.DataFrame({
            "ward_log_drivers": np.log1p(drivers["active_drvr"]),
            "ward_onride_share": (drivers["drvr_onride"] / drivers["active_drvr"].replace(0, np.nan)).fillna(0)}),
            how="left").fillna(0)
        if mlflow:
            card["mlflow"] = {"tracking_uri": MLFLOW_URI, "experiment": EXPERIMENT,
                              "run_id": parent.info.run_id}
            mlflow.set_tag("champions", json.dumps({k: v["champion"] for k, v in models.items()}))
    finally:
        if mlflow:
            mlflow.end_run()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    card["version"] = version
    card["train_seconds"] = round(time.time() - t0, 1)
    import sklearn
    card["sklearn_version"] = sklearn.__version__
    joblib.dump({"models": models, "ward_table": ward_table, "features": FEATURES, "version": version,
                 "sklearn_version": sklearn.__version__}, OUT_DIR / "model.joblib")
    (OUT_DIR / "model_card.json").write_text(json.dumps(card, indent=2))
    print(f"Saved models/ride_hailing/model.joblib (version {version}) in {card['train_seconds']} s")
    return card


if __name__ == "__main__":
    train()
