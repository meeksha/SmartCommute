"""Incentive optimiser: where should a company spend a monthly budget to cut the most CO2e?

For every commuter in the office's Census-derived population who currently
drives, rides a two-wheeler or takes an auto/cab, each greener alternative is
priced as a *compensating incentive*: the smallest payment per trip that makes
the alternative at least as good as their current mode in generalised cost

    generalised cost = money + value of time x travel time

using the published value of travel time savings (default Rs 179.2/h, IIT
Bombay study of Mumbai commuters reported by Hindustan Times, 9 Jun 2018).
An incentive can't exceed what the alternative costs the rider (a free pass
is the most a fare subsidy can do); if the time penalty is bigger than that,
money alone won't move that person and the option is marked infeasible.

Alternatives (all evaluated with the Digital Twin's per-trip functions, so the
numbers match the Twin and the journey planner):
* Metro pass  - home and office within the Metro catchment.
* BMTC pass   - any commuter (bus fare subsidy).
* Carpool credit - only within feasible carpool groups (same matching rules
                   as the Twin: homes <= 2.5 km, office <= 2 km, +-30 min).
* Shuttle seat - riders on the shuttle planner's routes; the company pays the
                 bus hire, shared over riders.

Each (person, incentive) pair gets a cost per tonne of CO2e avoided; the
cheapest are funded until the budget runs out (one incentive per person).
This is a marginal abatement cost curve for the company's commuting.
Break-even assumption: everyone offered a compensating incentive switches;
real take-up will be lower (the `take_up_pct` input scales the result).
"""
from __future__ import annotations

from app.services.population import DEFAULT_HEADCOUNT, DEFAULT_START

VOT_DEFAULT = 179.2
VOT_SOURCE = ("Value of travel time savings Rs 179.2/h (IIT Bombay study of Mumbai commuters, "
              "Hindustan Times, 9 Jun 2018)")
WORKING_DAYS = 230
ROAD_MODES = ("car", "two_wheeler", "auto", "cab")
LABELS = {"metro_pass": "Metro pass subsidy", "bus_pass": "BMTC bus pass subsidy",
          "carpool_credit": "Carpool credit", "shuttle_seat": "Company shuttle seat"}


def optimise(office: str | None = None, monthly_budget_inr: float = 200000, value_of_time: float = VOT_DEFAULT,
             headcount: int = DEFAULT_HEADCOUNT, start_time: str = DEFAULT_START,
             enabled: tuple = ("metro_pass", "bus_pass", "carpool_credit", "shuttle_seat"),
             take_up_pct: float = 100.0, shuttle_capacity: int = 40, shuttle_vehicles: int = 10) -> dict:
    from app.services.digital_twin import population, _trip, _metro_trip, _form_carpools, ROAD_CIRCUITY

    pop = population(office, headcount, start_time)
    trips = 2 * WORKING_DAYS
    road = pop[pop["baseline_mode"].isin(ROAD_MODES)]
    gc = lambda t, c: c + value_of_time * t / 60.0  # noqa: E731

    base = {}
    for row in road.itertuples():
        t, c, e, _ = _trip(row.baseline_mode, row.road_km)
        base[row.employee_id] = (t, c, e)

    cands = []          # (person, kind, subsidy/trip, co2 saved/trip, extra)

    def add(eid, kind, t_a, c_a, e_a, cap, extra=None):
        t_b, c_b, e_b = base[eid]
        saved = e_b - e_a
        if saved <= 0:
            return
        need = gc(t_a, c_a) - gc(t_b, c_b)
        if need <= 0:
            # Already as good in generalised cost, yet the Census shows people in this situation still
            # drive: something other than money/time holds them back. Not counted as a funded switch.
            cands.append({"id": eid, "kind": kind, "feasible": False, "nudge": True, "saved_kg": saved})
            return
        if need > cap + 1e-9:
            cands.append({"id": eid, "kind": kind, "feasible": False, "need_inr": round(need, 1),
                          "cap_inr": round(cap, 1)})
            return
        cands.append({"id": eid, "kind": kind, "feasible": True, "subsidy_inr": need, "saved_kg": saved,
                      "minutes_change": t_a - t_b, **(extra or {})})

    for row in road.itertuples():
        eid = row.employee_id
        if "metro_pass" in enabled and row.metro_eligible:
            t, c, e, _ = _metro_trip(row, False, 1.0)
            add(eid, "metro_pass", t, c, e, cap=c)
        if "bus_pass" in enabled:
            t, c, e, _ = _trip("bus", row.road_km)
            add(eid, "bus_pass", t, c, e, cap=c)

    if "carpool_credit" in enabled:
        idx = pop.index[pop["baseline_mode"].isin(ROAD_MODES)].to_numpy()
        for driver, riders, extra in _form_carpools(pop, idx, 4):
            occ = 1 + len(riders)
            for i in [driver] + list(riders):
                row = pop.loc[i]
                t, c, e, _ = _trip("carpool", row["road_km"], extra, occ)
                # Credit capped at what the person spends today (the company won't pay more than that).
                add(row["employee_id"], "carpool_credit", t, c, e, cap=base[row["employee_id"]][1],
                    extra={"group_size": occ})

    shuttle = None
    if "shuttle_seat" in enabled:
        from app.services.shuttles import plan_shuttles
        shuttle = plan_shuttles(office, headcount, start_time, shuttle_capacity, shuttle_vehicles)
        from app.services.costs import SHUTTLE_COST_PER_VKM_INR
        for r in shuttle["routes"]:
            per_rider_vehicle = r["route_km"] * SHUTTLE_COST_PER_VKM_INR / max(1, r["riders"])
            per_rider_co2 = r["fleet_co2e_kg_one_way"] / max(1, r["riders"])
            for s in r["stops"]:
                ride = s["ride_to_office_min"]
                for eid in pop.loc[pop["home_zone"].isin(s["wards"]) &
                                   pop["baseline_mode"].isin(ROAD_MODES), "employee_id"].tolist()[: s["boardings"]]:
                    t_b, c_b, e_b = base[eid]
                    walk = s["walk_from_ward_centre_km"] * 1.3 / 4.8 * 60
                    t_a = ride + walk + 5
                    need = max(0.0, gc(t_a, 0.0) - gc(t_b, c_b))
                    saved = e_b - per_rider_co2
                    if saved <= 0:
                        continue
                    # The rider rides free; the company pays the bus hire share plus any time compensation.
                    cands.append({"id": eid, "kind": "shuttle_seat", "feasible": True,
                                  "subsidy_inr": per_rider_vehicle + need, "saved_kg": saved,
                                  "minutes_change": t_a - t_b, "vehicle": r["vehicle"],
                                  "vehicle_share_inr": per_rider_vehicle})

    feasible = [c for c in cands if c["feasible"]]
    for c in feasible:
        c["annual_cost_inr"] = c["subsidy_inr"] * trips
        c["annual_saved_t"] = c["saved_kg"] * trips / 1000
        c["inr_per_tonne"] = c["annual_cost_inr"] / c["annual_saved_t"]
    # One incentive per person: their cheapest per tonne.
    best = {}
    for c in sorted(feasible, key=lambda c: c["inr_per_tonne"]):
        best.setdefault(c["id"], c)
    ranked = sorted(best.values(), key=lambda c: c["inr_per_tonne"])

    budget = float(monthly_budget_inr) * 12
    take = max(0.0, min(100.0, float(take_up_pct))) / 100
    spent = 0.0
    saved_t = 0.0
    chosen, curve = [], []
    cum = 0.0
    for c in ranked:
        cost, t = c["annual_cost_inr"] * take, c["annual_saved_t"] * take
        funded = spent + cost <= budget
        if funded:
            spent += cost
            saved_t += t
            chosen.append(c)
        cum += t
        curve.append({"cum_tonnes": round(cum, 2), "inr_per_tonne": round(c["inr_per_tonne"], 0),
                      "kind": c["kind"], "funded": funded})

    by_kind = {}
    for c in chosen:
        k = by_kind.setdefault(c["kind"], {"incentive": LABELS[c["kind"]], "people": 0, "annual_cost_inr": 0.0,
                                           "annual_co2e_tonnes": 0.0, "avg_per_trip_inr": 0.0,
                                           "avg_minutes_change": 0.0})
        k["people"] += 1
        k["annual_cost_inr"] += c["annual_cost_inr"] * take
        k["annual_co2e_tonnes"] += c["annual_saved_t"] * take
        k["avg_per_trip_inr"] += c["subsidy_inr"]
        k["avg_minutes_change"] += c["minutes_change"]
    for k in by_kind.values():
        n = max(1, k["people"])
        k["avg_per_trip_inr"] = round(k["avg_per_trip_inr"] / n, 1)
        k["avg_minutes_change"] = round(k["avg_minutes_change"] / n, 1)
        k["inr_per_tonne"] = round(k["annual_cost_inr"] / k["annual_co2e_tonnes"], 0) if k["annual_co2e_tonnes"] else None
        k["annual_cost_inr"] = round(k["annual_cost_inr"], 0)
        k["annual_co2e_tonnes"] = round(k["annual_co2e_tonnes"], 2)

    # Twin check: organisation totals before/after, with the same per-trip functions.
    base_total = 0.0
    for row in pop.itertuples():
        base_total += (_metro_trip(row, False, 1.0) if row.baseline_mode == "metro"
                       else _trip(row.baseline_mode, row.road_km))[2]
    after_total = base_total - sum(c["saved_kg"] for c in chosen) * take
    infeasible = [c for c in cands if not c["feasible"]]
    nudge_ids = {c["id"] for c in cands if c.get("nudge")} - set(best)

    return {
        "office": pop["office_zone"].iloc[0],
        "inputs": {"monthly_budget_inr": monthly_budget_inr, "value_of_time_inr_per_h": value_of_time,
                   "headcount": int(len(pop)), "start_time": start_time, "enabled": list(enabled),
                   "take_up_pct": take_up_pct},
        "result": {
            "people_switched": int(round(len(chosen) * take)),
            "annual_spend_inr": round(spent, 0),
            "monthly_spend_inr": round(spent / 12, 0),
            "annual_co2e_saved_tonnes": round(saved_t, 2),
            "avg_inr_per_tonne": round(spent / saved_t, 0) if saved_t else None,
        },
        "by_incentive": sorted(by_kind.values(), key=lambda k: -k["annual_co2e_tonnes"]),
        "curve": curve[:600],
        "potential": {
            "road_commuters": int(len(road)),
            "people_with_a_feasible_incentive": len(best),
            "max_annual_co2e_tonnes": round(sum(c["annual_saved_t"] for c in ranked) * take, 2),
            "budget_for_all_inr_per_month": round(sum(c["annual_cost_inr"] for c in ranked) * take / 12, 0),
            "money_alone_not_enough": len({c["id"] for c in infeasible if not c.get("nudge")} - set(best)
                                          - nudge_ids),
            "nudge_pool": len(nudge_ids),
            "nudge_pool_note": ("A greener option is already as good for them in money + time, yet people in "
                                "their situation still drive (Census). Payments are not what holds them back; "
                                "information, reliability or comfort might be. Not counted in the totals."),
        },
        "twin_check": {
            "baseline_co2e_one_way_kg": round(base_total, 1),
            "after_co2e_one_way_kg": round(after_total, 1),
            "annual_baseline_tonnes": round(base_total * trips / 1000, 1),
            "annual_after_tonnes": round(after_total * trips / 1000, 1),
            "reduction_pct": round((base_total - after_total) / base_total * 100, 2) if base_total else None,
        },
        "shuttle_routes_used": (shuttle or {}).get("summary"),
        "method": [
            "Commuters: Census 2011-derived statistical population of this office (ward populations + Table B-28).",
            f"Incentive per trip = generalised-cost gap; {VOT_SOURCE}.",
            "Fare subsidies are capped at the alternative's full fare; carpool credits at the person's current "
            "spend; shuttle seats cost the bus hire share (KSRTC Rs 62/km) plus any time compensation.",
            "Trip times, costs and CO2e: the Digital Twin's per-trip functions (same as the journey planner).",
            f"Annual = {WORKING_DAYS} working days x 2 trips. Cheapest Rs/tonne funded first, one incentive "
            "per person.",
            "Break-even assumption: people switch when the incentive closes the gap (an upper bound); scale "
            "with take-up %. Real-world check: when Namma Metro fares rose ~46 % on 9 Feb 2025, weekday "
            "ridership fell ~10 % (Deccan Herald), a short-run fare elasticity of about -0.22, so many "
            "people do not respond to price at all.",
        ],
    }
