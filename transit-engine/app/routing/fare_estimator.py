"""Evidence-based fare aggregation for a BMTC + Metro + BMTC itinerary.

No fare is guessed from distance. The caller must supply fare records from an
official/current tariff source, or the planner result must contain explicit
fare_inr values. If any component is missing, the combined fare remains None.
"""
from __future__ import annotations
from typing import Any


def _valid_amount(value: Any) -> float | None:
    try:
        amount = float(value)
        if amount >= 0 and amount < float("inf"):
            return amount
    except (TypeError, ValueError):
        pass
    return None


def calculate_three_mode_fare(result: dict, fare_data: dict | None = None) -> dict:
    if not isinstance(result, dict) or result.get("status") != "success":
        return {"status": "unavailable", "total_fare_inr": None,
                "message": "Input is not a successful three-mode itinerary."}

    fare_data = fare_data or {}
    sections = result.get("legs") or []
    bmtc_sections = [x for x in sections if x.get("mode") == "BMTC feeder"]
    metro_sections = [x for x in sections if x.get("mode") == "Metro"]
    if len(bmtc_sections) != 2 or len(metro_sections) != 1:
        return {"status": "unavailable", "total_fare_inr": None,
                "message": "Expected two BMTC feeder sections and one Metro section."}

    source = fare_data.get("source")
    effective_date = fare_data.get("effective_date")
    bmtc_table = fare_data.get("bmtc_feeder_fares_inr") or {}
    metro_table = fare_data.get("metro_journey_fares_inr") or {}
    components = []
    missing = []

    for idx, section in enumerate(bmtc_sections, start=1):
        journey = section.get("journey") or {}
        # Explicit fare from planner data takes precedence over a supplied table.
        amount = _valid_amount(journey.get("fare_inr"))
        component_source = journey.get("fare_source") if amount is not None else None
        if amount is None:
            amount = _valid_amount(bmtc_table.get(str(idx)))
            component_source = source if amount is not None else None
        if amount is None:
            missing.append(f"BMTC feeder {idx}")
        else:
            components.append({"component": f"BMTC feeder {idx}",
                               "fare_inr": round(amount, 2),
                               "source": component_source or "provided fare data"})

    metro_journey = metro_sections[0].get("journey") or {}
    metro_amount = _valid_amount(metro_journey.get("fare_inr"))
    metro_source = metro_journey.get("fare_source") if metro_amount is not None else None
    if metro_amount is None:
        # One Metro fare is charged for the complete Metro journey, not once
        # per train leg or interchange.
        fare_key = fare_data.get("metro_fare_key")
        if fare_key:
            metro_amount = _valid_amount(metro_table.get(str(fare_key)))
            metro_source = source if metro_amount is not None else None
    if metro_amount is None:
        missing.append("Metro journey")
    else:
        components.append({"component": "Metro journey", "fare_inr": round(metro_amount, 2),
                           "source": metro_source or "provided fare data"})

    if missing:
        partial = round(sum(x["fare_inr"] for x in components), 2) if components else None
        return {
            "status": "partial" if components else "unavailable",
            "total_fare_inr": None,
            "known_components_subtotal_inr": partial,
            "components": components,
            "missing_components": missing,
            "source": source,
            "effective_date": effective_date,
            "message": "Combined fare withheld because one or more component fares are unavailable.",
        }

    return {
        "status": "success",
        "total_fare_inr": round(sum(x["fare_inr"] for x in components), 2),
        "components": components,
        "missing_components": [],
        "source": source or "explicit fare fields in itinerary",
        "effective_date": effective_date,
        "fare_basis": "Sum of two BMTC feeder journey fares plus one complete Metro journey fare",
        "currency": "INR",
    }
