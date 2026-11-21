"""Operating-cost assumptions shared by the recommender and the Digital Twin."""
from __future__ import annotations

from app.services.emissions import energy_used, resolve_vehicle

# Bengaluru retail energy prices (configurable; update from a live feed when
# available). Petrol keeps the value already used by two_wheeler_cost.py.
ENERGY_PRICES_INR = {
    "petrol": 110.93,   # per litre, Bengaluru 3 Nov 2026 (Goodreturns via HDFC Sky)
    "e20": 110.93,      # per litre (retailed as petrol)
    "diesel": 98.80,    # per litre, Bengaluru 3 Nov 2026
    "cng": 89.00,       # per kg
    "lpg": 70.00,       # per litre (auto LPG)
    "electric": 8.00,   # per kWh, home charging
}
PRICE_SOURCE = "Configured Bengaluru retail energy prices (app/services/costs.py) - not a live price feed"

# Company shuttle: hired-bus cost per vehicle-km, INR. KSRTC ordinary bus hire rate (intra-state),
# revised Nov 2026 (The Hans India, 13 Nov 2026: "KSRTC revises bus hire charges").
SHUTTLE_COST_PER_VKM_INR = 62.0
SHUTTLE_COST_SOURCE = "KSRTC ordinary bus hire rate, Rs 62/km (revised Nov 2026, The Hans India)"


def fuel_cost(distance_km: float, category: str, user_vehicle: dict | None = None) -> dict:
    vehicle, user_supplied = resolve_vehicle(category, user_vehicle)
    used = energy_used(distance_km, vehicle)
    price = ENERGY_PRICES_INR[vehicle["fuel"]]
    unit = "kWh" if vehicle["fuel"] == "electric" else ("kg" if vehicle["fuel"] == "cng" else "litre")
    return {
        "amount_inr": round(used * price, 2),
        "energy_used": round(used, 3),
        "energy_unit": unit,
        "price_inr_per_unit": price,
        "fuel": vehicle["fuel"],
        "vehicle_label": vehicle["label"],
        "user_vehicle": user_supplied,
        "source": PRICE_SOURCE,
        "excludes": "parking, tolls, maintenance, insurance and depreciation",
    }
