"""Unified, vehicle/fuel/occupancy-aware emissions model.

One module is used by the recommender AND the Digital Twin so that a journey
shown to a commuter and the same journey aggregated for the organisation always
carry the same number.

Two methodologies, never silently mixed:

* ``well_to_wheel`` (road vehicles): distance -> fuel/electricity consumed ->
  (combustion + upstream fuel production) factor -> vehicle-trip CO2e, then
  divided by occupancy for the per-passenger figure. Vehicle manufacture is
  excluded.
* ``lifecycle_per_pkm`` (BMTC bus, Metro): ITF / World Bank India passenger
  transport LCA factors per passenger-km. These include vehicle/infrastructure
  life-cycle stages, so they are *higher-or-equal* in scope to well-to-wheel.
  Comparing transit on a life-cycle basis against road on a well-to-wheel basis
  is therefore conservative: it never overstates the benefit of transit.

Every result carries an estimate, a lower/upper bound, a confidence label, the
methodology, the data source and the assumptions used, so the UI can avoid
false precision.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

ITF_SOURCE = (
    "International Transport Forum / World Bank, Life-Cycle Assessment of "
    "Passenger Transport: An Indian Case Study (2023)"
)
FUEL_SOURCE = (
    "Combustion factors: IPCC 2006 default carbon content (petrol 2.31, diesel "
    "2.68 kg CO2/L; CNG 2.75 kg CO2/kg; LPG 1.56 kg CO2/L). Upstream "
    "(well-to-tank) uplifts follow UK DESNZ conversion-factor magnitudes. "
    "Grid electricity: CEA CO2 Baseline Database (India), adjusted for T&D losses."
)

# --- Fuel factors: kg CO2e per unit of energy carrier -----------------------
# tailpipe = direct combustion; wtt = upstream production/transport.
FUEL_FACTORS = {
    #  unit,  tailpipe, well-to-tank
    "petrol": ("litre", 2.31, 0.58),
    "diesel": ("litre", 2.68, 0.62),
    "cng": ("kg", 2.75, 0.50),
    "lpg": ("litre", 1.56, 0.20),
    # E20: 20 % ethanol by volume. Biogenic CO2 from ethanol is excluded by
    # convention; ethanol's upstream emissions are kept. Assumption, stated.
    "e20": ("litre", 2.31 * 0.80, 0.58 * 0.80 + 0.20 * 0.90),
    # Electricity at the plug (kg CO2e/kWh). CEA ~0.72 at generation, ~0.82
    # after ~12 % T&D losses. Range 0.72-0.95 used for the bounds.
    "electric": ("kWh", 0.0, 0.82),
}
GRID_RANGE_KG_PER_KWH = (0.72, 0.95)

# Default vehicle profiles when the user has not supplied their own vehicle.
# efficiency = km per unit (km/L, km/kg) or kWh per km for EVs.
DEFAULT_VEHICLES = {
    "car_petrol": {"fuel": "petrol", "efficiency": 14.0, "seats": 4,
                   "label": "Petrol car (default, ~14 km/L city)"},
    "car_diesel": {"fuel": "diesel", "efficiency": 16.0, "seats": 4,
                   "label": "Diesel car (default, ~16 km/L city)"},
    "car_cng": {"fuel": "cng", "efficiency": 22.0, "seats": 4,
                "label": "CNG car (default, ~22 km/kg)"},
    "car_hybrid": {"fuel": "petrol", "efficiency": 22.0, "seats": 4,
                   "label": "Petrol hybrid car (default, ~22 km/L)"},
    "car_ev": {"fuel": "electric", "efficiency": 0.15, "seats": 4,
               "label": "Electric car (default, 0.15 kWh/km)"},
    "two_wheeler_petrol": {"fuel": "petrol", "efficiency": 45.0, "seats": 1,
                           "label": "Petrol two-wheeler (default, ~45 km/L)"},
    "two_wheeler_ev": {"fuel": "electric", "efficiency": 0.035, "seats": 1,
                       "label": "Electric scooter (default, 0.035 kWh/km)"},
    "auto_cng": {"fuel": "cng", "efficiency": 30.0, "seats": 3,
                 "label": "CNG auto-rickshaw (default, ~30 km/kg)"},
    "auto_ev": {"fuel": "electric", "efficiency": 0.06, "seats": 3,
                "label": "Electric auto-rickshaw (default, 0.06 kWh/km)"},
    "cab_diesel": {"fuel": "diesel", "efficiency": 15.0, "seats": 4,
                   "label": "Diesel ride-hailing cab (default, ~15 km/L)"},
    "cab_cng": {"fuel": "cng", "efficiency": 22.0, "seats": 4,
                "label": "CNG ride-hailing cab (default, ~22 km/kg)"},
    "shuttle_diesel": {"fuel": "diesel", "efficiency": 5.5, "seats": 40,
                       "label": "Company shuttle mini-bus (default, ~5.5 km/L)"},
}

# Lifecycle factors per passenger-km (g CO2e), ITF/World Bank India case study.
TRANSIT_FACTORS_G_PER_PKM = {
    "bmtc_bus": {"low": 26.0, "central": 28.0, "high": 31.0,
                 "note": "Range spans electric (26), diesel (28) and CNG (31) bus scenarios; "
                         "BMTC fleet fuel mix per route is not verified."},
    "metro": {"low": 20.0, "central": 24.0, "high": 24.0,
              "note": "Indian-grid Metro (24); 20 = net-zero-grid scenario."},
}

# Extra one-off uncertainty when we fall back to a category default vehicle
# instead of the user's own vehicle.
DEFAULT_PROFILE_UNCERTAINTY = 0.25
USER_PROFILE_UNCERTAINTY = 0.10
# Real-world urban fuel use is typically worse than rated; congestion adds more.
CONGESTION_FUEL_PENALTY_MAX = 0.20


@dataclass
class EmissionEstimate:
    estimate_kg_co2e: float          # per passenger, central
    lower_kg_co2e: float
    upper_kg_co2e: float
    vehicle_trip_kg_co2e: float | None  # whole vehicle, if applicable
    occupancy: float | None
    tailpipe_kg_co2e: float | None   # per passenger, direct combustion only
    methodology: str
    scope: str
    confidence: str
    data_source: str
    vehicle_label: str | None = None
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        for k in ("estimate_kg_co2e", "lower_kg_co2e", "upper_kg_co2e",
                  "vehicle_trip_kg_co2e", "tailpipe_kg_co2e"):
            if d[k] is not None:
                d[k] = round(float(d[k]), 3)
        return d


def _zero(method: str, note: str) -> EmissionEstimate:
    return EmissionEstimate(0.0, 0.0, 0.0, 0.0, 1, 0.0, method, "operational",
                            "high", "Human-powered", None, [note])


def walking(distance_km: float) -> EmissionEstimate:
    return _zero("human_powered", "Walking/cycling treated as zero operational CO2e.")


def resolve_vehicle(category: str, user_vehicle: dict | None = None) -> tuple[dict, bool]:
    """Return (vehicle profile, is_user_supplied).

    user_vehicle may contain: fuel_type, efficiency (km/L, km/kg or kWh/km),
    mileage_km_per_litre (alias), kwh_per_km (alias), seats, label.
    """
    base = dict(DEFAULT_VEHICLES[category])
    if not user_vehicle:
        return base, False
    v = dict(user_vehicle)
    fuel = str(v.get("fuel_type") or base["fuel"]).lower()
    if fuel in ("ev", "bev"):
        fuel = "electric"
    if fuel == "hybrid":
        fuel = "petrol"
    if fuel not in FUEL_FACTORS:
        raise ValueError(f"Unsupported fuel_type {fuel!r}; choose {sorted(FUEL_FACTORS)}")
    eff = v.get("efficiency") or v.get("mileage_km_per_litre") or v.get("kwh_per_km")
    if eff is None:
        # User told us the fuel but not the efficiency: use a same-fuel default.
        key = category.split("_")[0] + "_" + ("ev" if fuel == "electric" else fuel)
        eff = DEFAULT_VEHICLES.get(key, base)["efficiency"] if key in DEFAULT_VEHICLES else base["efficiency"]
    eff = float(eff)
    if eff <= 0:
        raise ValueError("Vehicle efficiency must be positive.")
    label = v.get("label") or (
        f"Your {fuel} vehicle ({eff} {'kWh/km' if fuel == 'electric' else 'km/L' if FUEL_FACTORS[fuel][0] == 'litre' else 'km/kg'})"
    )
    return {"fuel": fuel, "efficiency": eff, "seats": int(v.get("seats") or base["seats"]),
            "label": label}, True


def energy_used(distance_km: float, vehicle: dict) -> float:
    """Units of fuel (L / kg) or kWh for a trip."""
    if vehicle["fuel"] == "electric":
        return distance_km * vehicle["efficiency"]
    return distance_km / vehicle["efficiency"]


def road_vehicle(distance_km: float, category: str, occupancy: float = 1.0,
                 user_vehicle: dict | None = None,
                 congestion_ratio: float | None = None) -> EmissionEstimate:
    """Well-to-wheel CO2e for a road vehicle trip, split by occupancy.

    congestion_ratio = traffic duration / free-flow duration (>=1). Stop-and-go
    traffic raises fuel use; we apply a bounded penalty to ICE vehicles only.
    """
    distance_km = max(0.0, float(distance_km))
    occupancy = max(1.0, float(occupancy))
    vehicle, user_supplied = resolve_vehicle(category, user_vehicle)
    unit, tailpipe_f, wtt_f = FUEL_FACTORS[vehicle["fuel"]]
    used = energy_used(distance_km, vehicle)
    assumptions = [vehicle["label"]]

    penalty = 0.0
    if congestion_ratio and vehicle["fuel"] != "electric":
        penalty = min(CONGESTION_FUEL_PENALTY_MAX, max(0.0, (float(congestion_ratio) - 1.0) * 0.25))
        if penalty > 0:
            used *= (1 + penalty)
            assumptions.append(f"+{penalty:.0%} fuel for congestion (traffic/free-flow ratio {congestion_ratio:.2f})")

    vehicle_tailpipe = used * tailpipe_f
    vehicle_wtw = used * (tailpipe_f + wtt_f)

    spread = USER_PROFILE_UNCERTAINTY if user_supplied else DEFAULT_PROFILE_UNCERTAINTY
    if vehicle["fuel"] == "electric":
        lo_f, hi_f = GRID_RANGE_KG_PER_KWH
        lower = used * lo_f * (1 - spread / 2)
        upper = used * hi_f * (1 + spread / 2)
        assumptions.append(f"Grid electricity {wtt_f} kg CO2e/kWh at plug (range {lo_f}-{hi_f}); zero tailpipe")
    else:
        lower = vehicle_wtw * (1 - spread)
        upper = vehicle_wtw * (1 + spread)
        assumptions.append(f"{tailpipe_f} kg CO2/{unit} combustion + {wtt_f} kg CO2e/{unit} upstream")
    if occupancy > 1:
        assumptions.append(f"Shared equally across {occupancy:g} occupants")

    return EmissionEstimate(
        estimate_kg_co2e=vehicle_wtw / occupancy,
        lower_kg_co2e=lower / occupancy,
        upper_kg_co2e=upper / occupancy,
        vehicle_trip_kg_co2e=vehicle_wtw,
        occupancy=occupancy,
        tailpipe_kg_co2e=vehicle_tailpipe / occupancy,
        methodology="well_to_wheel",
        scope="fuel/electricity production + combustion; excludes vehicle manufacture",
        confidence="medium" if user_supplied else "low",
        data_source=FUEL_SOURCE,
        vehicle_label=vehicle["label"],
        assumptions=assumptions,
    )


def transit(distance_km: float, mode: str) -> EmissionEstimate:
    f = TRANSIT_FACTORS_G_PER_PKM[mode]
    d = max(0.0, float(distance_km))
    return EmissionEstimate(
        estimate_kg_co2e=d * f["central"] / 1000,
        lower_kg_co2e=d * f["low"] / 1000,
        upper_kg_co2e=d * f["high"] / 1000,
        vehicle_trip_kg_co2e=None,
        occupancy=None,
        tailpipe_kg_co2e=None,
        methodology="lifecycle_per_pkm",
        scope="life-cycle per passenger-km at average Indian load factors",
        confidence="medium",
        data_source=ITF_SOURCE,
        vehicle_label=None,
        assumptions=[f"{f['central']:g} g CO2e/passenger-km ({f['low']:g}-{f['high']:g})", f["note"]],
    )


def combine(parts: list[EmissionEstimate]) -> EmissionEstimate:
    """Sum per-passenger estimates across journey legs."""
    parts = [p for p in parts if p is not None]
    if not parts:
        raise ValueError("No emission parts to combine")
    methods = sorted({p.methodology for p in parts if p.methodology != "human_powered"}) or ["human_powered"]
    conf_order = {"low": 0, "medium": 1, "high": 2}
    confidence = min((p.confidence for p in parts if p.methodology != "human_powered"),
                     key=lambda c: conf_order[c], default="high")
    assumptions = []
    for p in parts:
        for a in p.assumptions:
            if a not in assumptions:
                assumptions.append(a)
    sources = []
    for p in parts:
        if p.data_source not in sources and p.methodology != "human_powered":
            sources.append(p.data_source)
    return EmissionEstimate(
        estimate_kg_co2e=sum(p.estimate_kg_co2e for p in parts),
        lower_kg_co2e=sum(p.lower_kg_co2e for p in parts),
        upper_kg_co2e=sum(p.upper_kg_co2e for p in parts),
        vehicle_trip_kg_co2e=None,
        occupancy=None,
        tailpipe_kg_co2e=None,
        methodology="+".join(methods),
        scope="; ".join(sorted({p.scope for p in parts if p.methodology != "human_powered"})) or "operational",
        confidence=confidence,
        data_source=" | ".join(sources) or "Human-powered",
        assumptions=assumptions,
    )


def methodology_notes() -> dict:
    return {
        "metric": "kg CO2e per passenger for one one-way trip",
        "road_vehicles": "well-to-wheel: fuel or electricity consumed x (combustion + upstream) factor, "
                         "divided by occupancy. Vehicle manufacture excluded.",
        "public_transport": "life-cycle per passenger-km (ITF/World Bank India). Broader scope than "
                            "well-to-wheel, so the comparison is conservative against transit.",
        "uncertainty": "Ranges reflect fuel-mix, grid-intensity and vehicle-efficiency uncertainty. "
                       "Default vehicle profiles carry +/-25 %, user-supplied vehicles +/-10 %.",
        "sources": [ITF_SOURCE, FUEL_SOURCE],
        "fuel_factors": {k: {"unit": v[0], "tailpipe": v[1], "upstream": v[2]} for k, v in FUEL_FACTORS.items()},
        "default_vehicles": DEFAULT_VEHICLES,
        "transit_factors_g_per_pkm": TRANSIT_FACTORS_G_PER_PKM,
    }
