"""Quality filtering, deduplication and explainable commute ranking.

Unknown costs are never treated as free. They receive a neutral normalized
cost contribution and are explicitly marked as unavailable. Two ranking
profiles are calculated for every accepted option: balanced and green-first.
"""
from __future__ import annotations
from typing import Any

DEFAULT_LIMITS = {
    "max_total_walking_m": 2500.0,
    "max_origin_access_m": 1200.0,
    "max_destination_egress_m": 1800.0,
    "max_transfer_walk_m": 600.0,
}

RANKING_PROFILES = {
    # Green-first gives emissions enough influence to outweigh moderate
    # journey-time differences, without making duration irrelevant.
    "balanced": {
        "emissions": 0.35, "duration": 0.35, "fare": 0.15,
        "walking": 0.10, "transfers": 0.05,
    },
    "green_first": {
        "emissions": 0.70, "duration": 0.12, "fare": 0.08,
        "walking": 0.07, "transfers": 0.03,
    },
}

# Fixed, interpretable normalization anchors prevent an unusually polluting
# taxi candidate from compressing the emissions differences between bus and
# private two-wheeler. Values are capped at 1.0 for each metric.
METRIC_SCALE = {
    "emissions": 3.0,   # kg CO2e per one-way commute
    "duration": 180.0, # minutes
    "fare": 1000.0,    # INR per one-way commute
    "walking": 2500.0, # metres
    "transfers": 4.0,
}
DEFAULT_RANKING_PROFILE = "green_first"


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        return result if result >= 0 and result < float("inf") else None
    except (TypeError, ValueError):
        return None


def walking_segments(item: dict) -> list[dict]:
    return [leg for leg in (item.get("journey") or {}).get("legs", [])
            if leg.get("type") == "walking"]


def walking_metrics(item: dict) -> dict:
    segments = walking_segments(item)
    total = _number(item.get("distance_walking_m"))
    if total is None:
        total = _number((item.get("journey") or {}).get("walking_distance_m"))
    if total is None:
        vals = [_number(leg.get("distance_m")) for leg in segments]
        total = sum(v for v in vals if v is not None) if segments else 0.0
    origin = destination = transfer = 0.0
    for leg in segments:
        distance = _number(leg.get("distance_m")) or 0.0
        segment = leg.get("segment")
        if segment == "origin_access": origin += distance
        elif segment == "destination_egress": destination += distance
        else: transfer += distance
    return {"total_m": total, "origin_access_m": origin,
            "destination_egress_m": destination, "transfer_walk_m": transfer}


def filter_journeys(recommendations: list[dict], limits: dict | None = None):
    active = {**DEFAULT_LIMITS, **(limits or {})}
    accepted, rejected = [], []
    checks = (("total_m", "max_total_walking_m", "total walking distance"),
              ("origin_access_m", "max_origin_access_m", "origin access walk"),
              ("destination_egress_m", "max_destination_egress_m", "destination egress walk"),
              ("transfer_walk_m", "max_transfer_walk_m", "transfer walking distance"))
    for item in recommendations:
        metrics, reasons = walking_metrics(item), []
        for metric_key, limit_key, label in checks:
            value, limit = metrics[metric_key], _number(active.get(limit_key))
            if value is None and metric_key == "total_m":
                reasons.append("walking distance is unavailable")
            elif value is not None and limit is not None and value > limit:
                reasons.append(f"{label} {value:.0f} m exceeds {limit:.0f} m limit")
        if reasons:
            rejected.append({"journey_id": (item.get("journey") or {}).get("journey_id"),
                             "mode": item.get("mode"), "duration_minutes": item.get("duration_minutes"),
                             "reasons": reasons, "walking": metrics})
        else:
            item["walking_metrics"] = metrics
            accepted.append(item)
    return accepted, rejected


def _conservative_emissions(item: dict) -> float | None:
    emissions = item.get("emissions") or {}
    groups = [emissions.get("scenarios", {}), emissions.get("combined_scenarios", {})]
    values = []
    for group in groups:
        for scenario in (group or {}).values():
            value = (scenario.get("emissions_kg_co2e", scenario.get("total_emissions_kg_co2e"))
                     if isinstance(scenario, dict) else scenario)
            number = _number(value)
            if number is not None: values.append(number)
    return max(values) if values else _number(emissions.get("emissions_kg_co2e"))


def _estimated_fare(item: dict) -> tuple[float | None, str | None]:
    """Return a grounded trip cost and its provenance; None means unknown."""
    fare = item.get("fare") or {}
    for key in ("total_smart_card_qr_fare_inr", "total_token_fare_inr",
                "total_fare_inr", "fare_inr"):
        value = _number(fare.get(key))
        if value is not None: return value, f"fare.{key}"

    # Integrated Namma Yatri / notified-rate estimates use estimated_total_inr.
    estimates = item.get("fare_estimates") or {}
    cab = estimates.get("cab") or {}
    for category in ("10_to_15_lakh", "up_to_10_lakh", "above_15_lakh"):
        value = _number((cab.get(category) or {}).get("estimated_total_inr"))
        if value is not None: return value, f"fare_estimates.cab.{category} (modelled estimate)"
    auto = estimates.get("auto") or {}
    value = _number(auto.get("estimated_total_inr"))
    if value is not None: return value, "fare_estimates.auto (modelled estimate)"

    # Private-vehicle fuel expense is an operating cost, not a fare. Do not
    # silently mix it into public-transport fares or label it as a fare.
    return None, None


def _dedupe_key(item: dict) -> tuple:
    journey = item.get("journey") or {}
    signature = []
    for leg in journey.get("legs", []):
        kind = leg.get("type")
        if kind == "bmtc_bus":
            signature.append((kind, str(leg.get("route_number") or leg.get("route_short_name")),
                              str(leg.get("from_stop_id") or leg.get("from_stop")),
                              str(leg.get("to_stop_id") or leg.get("to_stop"))))
        elif kind == "metro":
            signature.append((kind, str(leg.get("line") or leg.get("route_id")),
                              str(leg.get("from_stop_id") or leg.get("from_station")),
                              str(leg.get("to_stop_id") or leg.get("to_station"))))
        elif kind == "walking":
            signature.append((kind, leg.get("segment"),
                              str(leg.get("details", {}).get("stop_id", "")),
                              str(leg.get("from", "")), str(leg.get("to", ""))))
        else: signature.append((kind,))
    return item.get("mode"), tuple(signature)


def deduplicate_journeys(recommendations: list[dict]):
    kept, removed, positions = [], [], {}
    for item in recommendations:
        key = _dedupe_key(item)
        if key not in positions:
            positions[key] = len(kept); kept.append(item); continue
        index = positions[key]
        old = _number(kept[index].get("duration_minutes"))
        new = _number(item.get("duration_minutes"))
        old = old if old is not None else float("inf")
        new = new if new is not None else float("inf")
        if new < old:
            removed.append({"mode": kept[index].get("mode"),
                            "duration_minutes": kept[index].get("duration_minutes"),
                            "reason": "duplicate itinerary; slower instance removed"})
            kept[index] = item
        else:
            removed.append({"mode": item.get("mode"), "duration_minutes": item.get("duration_minutes"),
                            "reason": "duplicate itinerary"})
    return kept, removed


def _score_profile(metrics_by_id: dict, weights: dict) -> dict:
    """Score candidates against fixed scales, not candidate-set min/max.

    Lower is better. Missing metrics receive a neutral midpoint (0.5), never
    zero/free. Fixed scales make scores stable when a very high-emission taxi
    is added or removed from the candidate list.
    """
    scores, details = {}, {}
    for item_id, metrics in metrics_by_id.items():
        total = 0.0
        breakdown, missing = {}, []
        for key, weight in weights.items():
            value = _number(metrics.get(key))
            scale = METRIC_SCALE.get(key)
            if value is None or scale is None:
                normalized = 0.5
                missing.append(key)
            else:
                normalized = min(1.0, max(0.0, value / scale))
            total += float(weight) * normalized
            breakdown[key] = round(normalized, 4)
        scores[item_id] = round(total, 6)
        details[item_id] = {"breakdown": breakdown, "missing_metrics": missing}
    return {"scores": scores, "details": details}


def rank_journeys(recommendations: list[dict], weights: dict | None = None,
                  profile: str = DEFAULT_RANKING_PROFILE):
    if profile not in RANKING_PROFILES:
        raise ValueError(f"Unknown ranking profile {profile!r}; choose {tuple(RANKING_PROFILES)}")
    active_profiles = {name: dict(values) for name, values in RANKING_PROFILES.items()}
    if weights is not None:
        active_profiles[profile] = {**active_profiles[profile], **weights}
    metrics_by_id = {}
    fare_sources = {}
    for item in recommendations:
        walk = item.get("walking_metrics") or walking_metrics(item)
        fare, fare_source = _estimated_fare(item)
        fare_sources[id(item)] = fare_source
        metrics_by_id[id(item)] = {
            "emissions": _conservative_emissions(item),
            "duration": _number(item.get("duration_minutes")),
            "fare": fare,
            "walking": _number(walk.get("total_m")),
            "transfers": _number((item.get("journey") or {}).get("transfers")),
        }
    profile_results = {name: _score_profile(metrics_by_id, pweights)
                       for name, pweights in active_profiles.items()}
    for item in recommendations:
        item_id = id(item)
        item["ranking_scores"] = {name: result["scores"][item_id]
                                  for name, result in profile_results.items()}
        item["ranking_profile"] = profile
        item["ranking_score"] = item["ranking_scores"][profile]
        item["ranking_metrics"] = metrics_by_id[item_id]
        item["ranking_breakdown"] = profile_results[profile]["details"][item_id]["breakdown"]
        item["ranking_missing_metrics"] = profile_results[profile]["details"][item_id]["missing_metrics"]
        item["fare_estimate_source"] = fare_sources[item_id]
        item["fare_status"] = "estimated" if fare_sources[item_id] else "unknown"
        item["ranking_metric_scales"] = dict(METRIC_SCALE)
        item["ranking_emissions_kg_co2e"] = metrics_by_id[item_id]["emissions"]
    recommendations.sort(key=lambda item: (item["ranking_score"],
        _number(item.get("duration_minutes")) if _number(item.get("duration_minutes")) is not None else float("inf")))
    for rank, item in enumerate(recommendations, 1): item["rank"] = rank
    return recommendations


def process_recommendations(recommendations: list[dict], limits: dict | None = None,
                            weights: dict | None = None,
                            ranking_profile: str = DEFAULT_RANKING_PROFILE) -> dict:
    filtered, rejected = filter_journeys(recommendations, limits)
    unique, duplicates = deduplicate_journeys(filtered)
    ranked = rank_journeys(unique, weights, ranking_profile)
    active_weights = {name: dict(values) for name, values in RANKING_PROFILES.items()}
    if weights is not None:
        active_weights[ranking_profile] = {**active_weights[ranking_profile], **weights}
    return {
        "recommendations": ranked,
        "rejected_recommendations": rejected,
        "duplicate_recommendations_removed": duplicates,
        "quality_limits": {**DEFAULT_LIMITS, **(limits or {})},
        "ranking_profile": ranking_profile,
        "ranking_weights": active_weights,
        "quality_summary": {
            "input_candidates": len(recommendations),
            "accepted_after_filter_and_deduplication": len(ranked),
            "rejected_by_walking_limits": len(rejected),
            "duplicates_removed": len(duplicates),
        },
    }
