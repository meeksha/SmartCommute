"""Estimate life-cycle emissions for BMTC + Metro + BMTC journeys.

Distances are taken from GTFS shape_dist_traveled values. Missing or invalid
shape distances are reported as unavailable; this module does not substitute
straight-line distance or zero emissions.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.carbon import (
    EMISSION_FACTORS,
    SOURCE,
    calculate_emissions,
    calculate_bmtc_journey_distance,
)

METRO_DIR = Path("data/processed/metro/standard")


@lru_cache(maxsize=32)
def _load_metro_trip_distances(stop_times_path: str, trip_ids: tuple[str, ...]):
    """Load stop sequence shape distances for only the requested Metro trips."""
    wanted = set(trip_ids)
    found: dict[tuple[str, str], tuple[float, int]] = {}
    path = Path(stop_times_path)
    if not path.exists():
        raise FileNotFoundError(f"Metro GTFS stop_times file not found: {path}")

    for chunk in pd.read_csv(
        path,
        dtype={"trip_id": str, "stop_id": str},
        chunksize=250_000,
        usecols=["trip_id", "stop_id", "stop_sequence", "shape_dist_traveled"],
    ):
        chunk = chunk[chunk["trip_id"].isin(wanted)]
        for row in chunk.itertuples(index=False):
            value = pd.to_numeric(row.shape_dist_traveled, errors="coerce")
            sequence = pd.to_numeric(row.stop_sequence, errors="coerce")
            if pd.notna(value) and pd.notna(sequence):
                found[(str(row.trip_id), str(row.stop_id))] = (float(value), int(sequence))
    return found


def calculate_metro_journey_distance(
    metro_legs: list[dict[str, Any]],
    stop_times_path: str | Path | None = None,
) -> dict:
    """Calculate Metro distance from GTFS shape_dist_traveled (kilometres)."""
    if not metro_legs:
        return {"status": "unavailable", "message": "No Metro legs supplied."}

    path = Path(stop_times_path) if stop_times_path else METRO_DIR / "stop_times.csv"
    trip_ids = tuple(sorted({str(leg.get("trip_id", "")) for leg in metro_legs}))
    if not all(trip_ids):
        return {"status": "unavailable", "message": "A Metro leg is missing trip_id."}

    try:
        values = _load_metro_trip_distances(str(path), trip_ids)
    except (OSError, ValueError, KeyError) as exc:
        return {"status": "unavailable", "message": str(exc)}

    details = []
    total_km = 0.0
    for leg in metro_legs:
        trip_id = str(leg["trip_id"])
        from_stop = str(leg.get("from_stop", ""))
        to_stop = str(leg.get("to_stop", ""))
        start = values.get((trip_id, from_stop))
        end = values.get((trip_id, to_stop))
        if start is None or end is None:
            return {
                "status": "unavailable",
                "message": f"Metro GTFS shape distance missing for trip {trip_id} ({from_stop} -> {to_stop}).",
            }
        if end[1] <= start[1] or end[0] < start[0]:
            return {
                "status": "unavailable",
                "message": f"Invalid Metro stop order or shape distance for trip {trip_id}.",
            }
        distance_km = end[0] - start[0]
        details.append({
            "trip_id": trip_id,
            "from_stop": from_stop,
            "to_stop": to_stop,
            "distance_km": round(distance_km, 3),
            "distance_basis": "GTFS stop_times.shape_dist_traveled; feed values interpreted as kilometres",
        })
        total_km += distance_km

    return {
        "status": "success",
        "distance_km": round(total_km, 3),
        "legs": details,
        "distance_basis": "GTFS stop_times.shape_dist_traveled in kilometres",
    }


def _bmtc_legs_from_section(section: dict) -> list[dict]:
    journey = section.get("journey") or {}
    bmtc = journey.get("bmtc_journey") or {}
    return list(bmtc.get("legs") or [])


def calculate_three_mode_emissions(
    combined_result: dict,
    *,
    metro_stop_times_path: str | Path | None = None,
) -> dict:
    """Calculate separate and combined BMTC/Metro life-cycle emissions.

    BMTC fleet fuel is not verified, so diesel/CNG/electric scenarios are
    returned rather than asserting one fleet-wide factor. Metro IPS and
    net-zero scenarios are also retained separately.
    """
    if not isinstance(combined_result, dict) or combined_result.get("status") != "success":
        return {"status": "unavailable", "message": "Input is not a successful three-mode itinerary."}

    sections = combined_result.get("legs") or []
    bmtc_sections = [section for section in sections if section.get("mode") == "BMTC feeder"]
    metro_sections = [section for section in sections if section.get("mode") == "Metro"]
    if len(bmtc_sections) != 2 or len(metro_sections) != 1:
        return {
            "status": "unavailable",
            "message": "Expected exactly two BMTC feeder sections and one Metro section.",
        }

    feeder_results = []
    total_bmtc_km = 0.0
    for index, section in enumerate(bmtc_sections, start=1):
        bus_legs = _bmtc_legs_from_section(section)
        if not bus_legs:
            return {"status": "unavailable", "message": f"BMTC feeder {index} contains no bus legs."}
        result = calculate_bmtc_journey_distance(bus_legs)
        if result.get("status") != "success":
            return {
                "status": "unavailable",
                "message": f"BMTC feeder {index}: {result.get('message', 'distance unavailable')}",
                "partial_bmtc_results": feeder_results,
            }
        feeder_results.append({"feeder": index, **result})
        total_bmtc_km += float(result["distance_km"])

    metro_result = calculate_metro_journey_distance(
        list((metro_sections[0].get("journey") or {}).get("legs") or []),
        stop_times_path=metro_stop_times_path,
    )
    if metro_result.get("status") != "success":
        return {
            "status": "unavailable",
            "message": f"Metro distance: {metro_result.get('message', 'unavailable')}",
            "bmtc": {"distance_km": round(total_bmtc_km, 3), "feeders": feeder_results},
        }

    metro_km = float(metro_result["distance_km"])
    bmtc_factors = {
        "diesel": "bmtc_diesel",
        "cng": "bmtc_cng",
        "electric_grid": "bmtc_electric_ips",
    }
    metro_factors = {
        "grid": "metro_ips",
        "net_zero": "metro_net_zero",
    }

    bmtc_scenarios = {
        label: calculate_emissions(total_bmtc_km, factor)
        for label, factor in bmtc_factors.items()
    }
    metro_scenarios = {
        label: calculate_emissions(metro_km, factor)
        for label, factor in metro_factors.items()
    }

    combined_scenarios = {}
    for bmtc_label, bmtc_data in bmtc_scenarios.items():
        for metro_label, metro_data in metro_scenarios.items():
            key = f"bmtc_{bmtc_label}+metro_{metro_label}"
            combined_scenarios[key] = {
                "bmtc_emissions_kg_co2e": bmtc_data["emissions_kg_co2e"],
                "metro_emissions_kg_co2e": metro_data["emissions_kg_co2e"],
                "total_emissions_kg_co2e": round(
                    bmtc_data["emissions_kg_co2e"] + metro_data["emissions_kg_co2e"], 4
                ),
            }

    # This is an explicitly labelled illustrative reference case, not a
    # claim about the actual BMTC fleet or Metro electricity mix.
    reference_case = combined_scenarios["bmtc_diesel+metro_grid"]
    totals = [x["total_emissions_kg_co2e"] for x in combined_scenarios.values()]
    return {
        "status": "success",
        "mode": "BMTC + Metro + BMTC",
        "distance_km": {
            "bmtc_total": round(total_bmtc_km, 3),
            "metro_total": round(metro_km, 3),
            "combined_motorized": round(total_bmtc_km + metro_km, 3),
        },
        "distance_breakdown": {
            "bmtc_feeders": feeder_results,
            "metro": metro_result,
        },
        "emissions_kg_co2e": {
            "reference_case": reference_case["total_emissions_kg_co2e"],
            "reference_case_label": "Illustrative BMTC diesel + Metro grid scenario; not verified fleet energy mix",
            "minimum_scenario": round(min(totals), 4),
            "maximum_scenario": round(max(totals), 4),
            "scenarios": combined_scenarios,
        },
        "emission_factors_g_per_passenger_km": {
            "bmtc": {label: EMISSION_FACTORS[factor] for label, factor in bmtc_factors.items()},
            "metro": {label: EMISSION_FACTORS[factor] for label, factor in metro_factors.items()},
        },
        "source": SOURCE,
        "calculation_basis": "Life-cycle emissions per passenger-kilometre; segment distances from GTFS shape_dist_traveled",
        "is_estimate": True,
        "limitations": [
            "BMTC vehicle fuel type is not verified; alternative fleet scenarios are reported.",
            "Metro electricity scenario is not verified against actual traction-energy procurement.",
            "Emission factors are estimates from the existing project carbon module.",
            "Fare is not calculated by this module.",
            "Walking access and egress emissions are excluded.",
        ],
    }
