"""Personalised ranking: preset profiles + online preference learning.

Model: a conditional-logit (multinomial discrete-choice) model over the
candidate journeys shown in one request,

    P(choose j) = exp(-w . x_j / T) / sum_k exp(-w . x_k / T)

where x_j are normalised journey costs (CO2e, time, money, walking, transfers,
wait/uncertainty) and w >= 0 are the user's weights. After each observed choice
we take one gradient-ascent step on the log-likelihood:

    w <- w + eta * (E_p[x] - x_chosen)

so a metric the user keeps accepting more of gets a lower weight, and one
they keep avoiding gets a higher weight. Weights are clipped to stay positive
and renormalised to sum to 1. Cold start = the user's stated profile.
"""
from __future__ import annotations

import math

FEATURES = ["emissions", "duration", "cost", "walking", "transfers", "uncertainty"]

# Fixed, interpretable normalisation anchors (value / scale, capped at FEATURE_CAP).
# The cap is high enough that long intercity trips (e.g. 4.5 kg vs 1.5 kg CO2e) still differ.
FEATURE_CAP = 4.0
SCALES = {"emissions": 1.0, "duration": 120.0, "cost": 400.0, "walking": 2500.0,
          "transfers": 3.0, "uncertainty": 1.0}

PROFILES = {
    "balanced":    {"emissions": 0.25, "duration": 0.30, "cost": 0.20, "walking": 0.10, "transfers": 0.07, "uncertainty": 0.08},
    "green_first": {"emissions": 0.55, "duration": 0.18, "cost": 0.10, "walking": 0.07, "transfers": 0.04, "uncertainty": 0.06},
    "fastest":     {"emissions": 0.08, "duration": 0.60, "cost": 0.08, "walking": 0.08, "transfers": 0.06, "uncertainty": 0.10},
    "cheapest":    {"emissions": 0.10, "duration": 0.15, "cost": 0.55, "walking": 0.08, "transfers": 0.04, "uncertainty": 0.08},
    "comfort":     {"emissions": 0.10, "duration": 0.25, "cost": 0.10, "walking": 0.25, "transfers": 0.20, "uncertainty": 0.10},
}
# Employee-dataset preference labels -> profiles.
DATASET_PREFERENCE_MAP = {"Balanced": "balanced", "Time": "fastest", "Cost": "cheapest",
                          "CO2": "green_first", "Environment": "green_first", "Comfort": "comfort"}

# Same default as the original engine (recommendation_quality.DEFAULT_RANKING_PROFILE).
DEFAULT_PROFILE = "green_first"

LEARNING_RATE = 0.15
TEMPERATURE = 0.15
MIN_WEIGHT = 0.02


def normalise_weights(w: dict) -> dict:
    w = {k: max(MIN_WEIGHT, float(w.get(k, 0.0))) for k in FEATURES}
    s = sum(w.values())
    return {k: round(v / s, 4) for k, v in w.items()}


def feature_vector(metrics: dict) -> dict:
    """Raw metrics -> normalised [0, FEATURE_CAP] features. Unknown -> 0.5 (never free)."""
    out = {}
    for k in FEATURES:
        v = metrics.get(k)
        out[k] = 0.5 if v is None else min(FEATURE_CAP, max(0.0, float(v) / SCALES[k]))
    return out


def score(features: dict, weights: dict) -> float:
    return sum(weights[k] * features[k] for k in FEATURES)


def choice_probabilities(feature_list: list[dict], weights: dict) -> list[float]:
    utils = [-score(f, weights) / TEMPERATURE for f in feature_list]
    m = max(utils)
    ex = [math.exp(u - m) for u in utils]
    s = sum(ex)
    return [e / s for e in ex]


def update_weights(weights: dict, feature_list: list[dict], chosen_index: int,
                   lr: float = LEARNING_RATE) -> tuple[dict, dict]:
    probs = choice_probabilities(feature_list, weights)
    expected = {k: sum(p * f[k] for p, f in zip(probs, feature_list)) for k in FEATURES}
    chosen = feature_list[chosen_index]
    grad = {k: expected[k] - chosen[k] for k in FEATURES}
    new = normalise_weights({k: weights[k] + lr * grad[k] for k in FEATURES})
    diag = {
        "prob_of_chosen_before": round(probs[chosen_index], 4),
        "prob_of_chosen_after": round(choice_probabilities(feature_list, new)[chosen_index], 4),
        "gradient": {k: round(v, 4) for k, v in grad.items()},
    }
    return new, diag


def explain_weights(weights: dict) -> list[str]:
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    names = {"emissions": "low emissions", "duration": "short travel time", "cost": "low cost",
             "walking": "less walking", "transfers": "fewer transfers", "uncertainty": "reliability"}
    return [f"{names[k]} ({v:.0%})" for k, v in ranked[:3]]
