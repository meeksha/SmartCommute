"""End-to-end API tests. Run from the project root:  python -m pytest -q tests

Uses a temporary SQLite DB. The first recommendation loads the walking graph
and the BMTC timetable (~30 s cold).
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.sqlite3"))
os.environ.setdefault("SKIP_WARMUP", "1")
ADMIN_EMAIL = f"admin{os.getpid()}@test.corp"
os.environ["ADMIN_EMAILS"] = ADMIN_EMAIL

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import emissions as E
from app.services.costs import fuel_cost

DATE = "2026-11-18"
TRIP = {"origin": {"lat": 12.9585, "lon": 77.5635}, "destination": {"lat": 13.0105, "lon": 77.5540},
        "date": DATE, "time": "08:00"}
# HSR Layout -> Outer Ring Road (Bellandur): a commute two colleagues can share.
COMMUTE = {"origin": {"lat": 12.9116, "lon": 77.6474}, "destination": {"lat": 12.9352, "lon": 77.6950}, "date": DATE}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin():
    """A company admin (listed in ADMIN_EMAILS): sees the company-wide endpoints."""
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"email": ADMIN_EMAIL, "password": "secret123", "name": "Admin"})
        if r.status_code == 409:
            c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "secret123"})
        yield c


@pytest.fixture(scope="module")
def rec(client):
    r = client.post("/api/recommendations", json=TRIP)
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    m = client.get("/api/meta").json()
    assert len(m["offices"]) == 6 and m["default_profile"] == "green_first"


def test_recommendation_shape(rec):
    assert rec["status"] == "success"
    opts = rec["options"]
    assert 3 <= len(opts) <= 12
    assert rec["recommended_option_id"] == opts[0]["id"]
    ranks = [o["rank"] for o in opts]
    assert ranks == list(range(1, len(opts) + 1))
    scores = [o["score"] for o in opts]
    assert scores == sorted(scores)
    for o in opts:
        em = o["emissions"]
        assert em["lower_kg_co2e"] <= em["estimate_kg_co2e"] <= em["upper_kg_co2e"]
        assert em["methodology"] and em["data_source"] and em["confidence"] in ("low", "medium", "high")
        assert o["duration_min"] > 0 and o["legs"]
        assert o["depart_time"] == "08:00"
        # walking total equals the sum of walking legs
        assert abs(o["walking"]["total_m"] - sum(l.get("distance_m", 0) for l in o["legs"] if l["type"] == "walk")) <= 1
    assert sum(1 for o in opts if "Recommended" in o["badges"]) == 1
    probs = [o["predicted_choice_probability"] for o in opts]
    assert abs(sum(probs) - 1) < 0.01 and probs[0] == max(probs)


def test_walking_limits_respected(rec):
    lim = rec["personalisation"]["constraints"]
    for o in rec["options"]:
        if o["family"] != "walk":
            assert o["walking"]["total_m"] <= lim["max_total_walking_m"] + 1
            assert o["walking"]["origin_access_m"] <= lim["max_origin_access_m"] + 1


def test_transit_legs_have_geometry(rec):
    for o in rec["options"]:
        for leg in o["legs"]:
            if leg["type"] in ("bus", "metro"):
                assert len(leg["path"]) >= 2 and leg["from"]["lat"] and leg["to"]["lat"]
                assert leg["departure_time"] and leg["arrival_time"]


def test_numbers_consistent_with_emission_model(rec):
    """Recompute each road option's CO2e and fuel cost from first principles."""
    for o in rec["options"]:
        if o["family"] == "car":
            ratio = o["traffic"]["congestion_ratio"]
            exp = E.road_vehicle(o["distance_km"], "car_petrol", 1, None, ratio).estimate_kg_co2e
            assert abs(exp - o["emissions"]["estimate_kg_co2e"]) < 1e-3
            assert abs(fuel_cost(o["distance_km"], "car_petrol")["amount_inr"] - o["cost"]["amount_inr"]) < 0.01
        if o["family"] == "metro":
            km = o["transit_km"]["metro"]
            assert abs(E.transit(km, "metro").estimate_kg_co2e - o["emissions"]["estimate_kg_co2e"]) < 1e-3


def test_baseline_savings_text(rec):
    base = rec["baseline_drive_alone"]
    assert base and base["co2e_kg"] > 0
    rec0 = rec["options"][0]
    if rec0["family"] != "car":
        assert any("vs driving alone" in r for r in rec0["reasons"]) or rec0["emissions"]["estimate_kg_co2e"] >= base["co2e_kg"]


def test_profiles_change_ranking(client):
    fast = client.post("/api/recommendations", json={**TRIP, "profile": "fastest"}).json()
    green = client.post("/api/recommendations", json={**TRIP, "profile": "green_first"}).json()
    f0, g0 = fast["options"][0], green["options"][0]
    assert f0["duration_min"] <= g0["duration_min"]
    assert g0["emissions"]["estimate_kg_co2e"] <= f0["emissions"]["estimate_kg_co2e"]


def test_user_learning_loop(client):
    u = client.post("/api/users", json={"name": "Asha", "employee_id": "EMP-1042"}).json()
    assert u["employee_id"] == "EMP-1042"          # company ID is a label; no dataset lookup
    r = client.post("/api/recommendations", json={**TRIP, "user_id": u["id"]}).json()
    # pick the fastest option repeatedly -> duration weight must rise
    fastest = min(r["options"], key=lambda o: o["duration_min"])
    w0 = None
    for _ in range(5):
        c = client.post(f"/api/recommendations/{r['request_id']}/choice",
                        json={"option_id": fastest["id"], "user_id": u["id"]}).json()
        w0 = w0 or c["learning"]["previous_weights"]
        assert c["learning"]["prob_of_chosen_after"] >= c["learning"]["prob_of_chosen_before"]
    w = client.get(f"/api/users/{u['id']}").json()["weights"]
    assert w != w0 and abs(sum(w.values()) - 1) < 1e-3
    # Personalised ranking now uses the learned weights and puts the habitual choice first.
    r2 = client.post("/api/recommendations", json={**TRIP, "user_id": u["id"]}).json()
    assert r2["personalisation"]["source"] == "learned"
    rank_before = next(o["rank"] for o in r["options"] if o["family"] == fastest["family"])
    rank_after = next(o["rank"] for o in r2["options"] if o["family"] == fastest["family"])
    assert rank_after <= rank_before and rank_after <= 2
    h = client.get(f"/api/users/{u['id']}/history").json()
    assert h["impact"]["trips"] == 5


def test_validation_errors(client):
    bad = {**TRIP, "origin": {"lat": 28.6, "lon": 77.2}}          # Delhi
    assert client.post("/api/recommendations", json=bad).status_code == 422
    assert client.post("/api/recommendations", json={**TRIP, "date": "2025-01-01"}).status_code == 422
    assert client.post("/api/recommendations/nope/choice", json={"option_id": "x"}).status_code == 404


def test_office_destination(client):
    r = client.post("/api/recommendations", json={"origin": TRIP["origin"], "destination_office_id": "manyata",
                                                   "date": DATE, "time": "09:00"})
    assert r.status_code == 200 and r.json()["options"]


def test_census_population_clusters_and_no_simulated_colleagues(admin):
    c = admin.get("/api/clusters").json()
    assert sum(x["employee_count"] for x in c["clusters"]) == 2000 and "Census" in c["dataset"]
    pop = admin.get("/api/population", params={"office": "whitefield"}).json()
    assert pop["headcount"] == 2000 and abs(sum(pop["mode_share"].values()) - 1) < 1e-6
    # Same inputs -> same population (deterministic apportionment, no random sampling).
    again = admin.get("/api/population", params={"office": "whitefield"}).json()
    assert again["mode_share"] == pop["mode_share"]
    # Mode shares follow Census B-28 within each distance band.
    from app.services.population import population_for, mode_shares
    df = population_for("whitefield")
    band = df[df["distance_band"] == "distance_6_10_km"]
    expected = mode_shares("distance_6_10_km")
    expected.pop("walk", None)
    tot = sum(expected.values())
    for mode, share in expected.items():
        assert abs((band["baseline_mode"] == mode).mean() - share / tot) < 0.02
    assert admin.get("/api/carpool/matches").status_code == 410


def test_digital_twin(admin):
    base = admin.get("/api/digital-twin/baseline").json()
    sim = admin.post("/api/digital-twin/simulate",
                      json={"metro_shift_pct": 20, "carpool_pct": 30, "shuttle_count": 10}).json()
    assert sim["baseline"]["one_way"]["co2e_kg"] == base["baseline"]["one_way"]["co2e_kg"]
    assert sim["scenario_result"]["one_way"]["co2e_kg"] < sim["baseline"]["one_way"]["co2e_kg"]
    assert sim["scenario_result"]["vehicles_on_road"] < sim["baseline"]["vehicles_on_road"]
    shares = sum(v["share"] for v in sim["scenario_result"]["mode_share"].values())
    assert abs(shares - 1) < 1e-3
    assert 0 < sim["shuttle"]["utilisation"] <= 1
    assert sim["carpool"]["avg_occupancy"] >= 2


def test_twin_uses_same_trip_model_as_recommender():
    from app.services.digital_twin import _trip
    t, cost, co2, veh = _trip("car", 12.0)
    assert abs(co2 - E.road_vehicle(12.0, "car_petrol").estimate_kg_co2e) < 1e-9
    assert abs(cost - fuel_cost(12.0, "car_petrol")["amount_inr"]) < 1e-9
    _, _, co2b, _ = _trip("bus", 12.0)
    assert abs(co2b - E.transit(12.0, "bmtc_bus").estimate_kg_co2e) < 1e-9


def test_demand_and_emissions_endpoints(client):
    d = client.get("/api/demand").json()["hours"]
    assert len(d) == 24 and all(0.9 <= h["price_pressure_multiplier"] <= 1.6 for h in d)
    rainy = client.get("/api/demand", params={"hour": 18, "rain": True}).json()
    dry = client.get("/api/demand", params={"hour": 18}).json()
    assert rainy["quote_probability"] < dry["quote_probability"]
    solo = client.post("/api/emissions/estimate", json={"distance_km": 10, "mode": "car"}).json()
    pool = client.post("/api/emissions/estimate", json={"distance_km": 10, "mode": "carpool", "occupancy": 4}).json()
    assert abs(pool["emissions"]["estimate_kg_co2e"] * 4 - solo["emissions"]["estimate_kg_co2e"]) < 0.01
    ev = client.post("/api/emissions/estimate", json={"distance_km": 10, "mode": "car",
                                                      "vehicle": {"type": "car", "fuel_type": "electric"}}).json()
    assert ev["emissions"]["tailpipe_kg_co2e"] == 0


def test_places_search(client):
    r = client.get("/api/places/search", params={"q": "majestic"}).json()
    assert r["results"]


def test_auth_trip_flow_uses_backend_numbers(client):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        email = f"u{os.getpid()}@example.com"
        assert c.post("/api/auth/register", json={"email": email, "password": "secret123"}).status_code == 201
        assert c.get("/api/auth/me").json()["user"]["email"] == email
        # Session user is applied automatically (no user_id in the body).
        r = c.post("/api/recommendations", json={**TRIP, "profile": "balanced",
                                                  "preferences": {"usual_mode": "driving"}}).json()
        assert r["personalisation"]["preferences"]["usual_mode"] == "driving"
        assert r["usual_option"]["family"] == "car"
        cmp_ = r["comparisons"]["recommended_vs_drive_alone"]
        rec0, base = r["options"][0], r["baseline_drive_alone"]
        if cmp_:
            assert abs(cmp_["co2e_saved_kg"] - (base["co2e_kg"] - rec0["emissions"]["estimate_kg_co2e"])) < 1e-3
        pick = r["options"][1]
        ch = c.post(f"/api/recommendations/{r['request_id']}/choice",
                    json={"option_id": pick["id"], "save_trip": True,
                          "origin_label": "Chamarajapet", "destination_label": "Orion Mall"}).json()
        st = ch["saved_trip"]
        assert st["mode"] == pick["title"] and st["co2_kg"] == pick["emissions"]["estimate_kg_co2e"]
        assert st["cost"] == pick["cost"]["amount_inr"] and st["segments"]
        trips = c.get("/api/trips").json()["trips"]
        assert trips[0]["id"] == st["id"]
        hist = c.get("/api/users/me/history").json()
        assert hist["impact"]["trips"] == 1
        assert abs(hist["impact"]["co2e_saved_kg"] - st["co2_saved_vs_drive_kg"]) < 1e-3
        # Another anonymous client cannot read this account's profile.
        with TestClient(app) as other:
            assert other.get(f"/api/users/{email}").status_code == 403
            assert other.get("/api/trips").status_code == 401
        assert c.post("/api/auth/logout").status_code == 200
        assert c.get("/api/auth/me").status_code == 401


def test_rerank_is_fast_after_first_plan(client):
    import time as _t
    client.post("/api/recommendations", json=TRIP)
    t = _t.time()
    r = client.post("/api/recommendations", json={**TRIP, "profile": "cheapest"}).json()
    assert r["cached"] is True and _t.time() - t < 2.0


def test_google_sign_in(monkeypatch):
    import app.main as M
    from fastapi.testclient import TestClient
    monkeypatch.setattr(M, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    email = f"g{os.getpid()}@gmail.com"
    monkeypatch.setattr(M, "_verify_google_token", lambda cred: {
        "iss": "https://accounts.google.com", "email": email.upper(), "email_verified": True, "name": "Gita G"})
    with TestClient(app) as c:
        assert c.get("/api/auth/config").json()["google_enabled"] is True
        r = c.post("/api/auth/google", json={"credential": "x" * 40})
        assert r.status_code == 200 and r.json()["user"]["email"] == email
        assert c.get("/api/users/me").json()["name"] == "Gita G"
        # Google-only accounts cannot be used with a password
        bad = c.post("/api/auth/login", json={"email": email, "password": "whatever1"})
        assert bad.status_code == 401 and "Google" in bad.json()["detail"]
    monkeypatch.setattr(M, "_verify_google_token", lambda cred: {
        "iss": "https://accounts.google.com", "email": "x@gmail.com", "email_verified": False})
    with TestClient(app) as c:
        assert c.post("/api/auth/google", json={"credential": "y" * 40}).status_code == 401


def test_carpool_request_flow_reveals_contact_only_after_accept():
    from fastapi.testclient import TestClient
    import time as _t
    pid = f"{os.getpid()}{int(_t.time() * 1000)}"
    bname = f"Bala {pid}"
    with TestClient(app) as a, TestClient(app) as b:
        a.post("/api/auth/register", json={"email": f"a{pid}@corp.com", "password": "secret123", "name": "Asha"})
        b.post("/api/auth/register", json={"email": f"b{pid}@corp.com", "password": "secret123", "name": bname})
        for c in (a, b):       # both save the same 08:30 commute
            r = c.post("/api/recommendations", json={**COMMUTE, "time": "08:30"}).json()
            c.post(f"/api/recommendations/{r['request_id']}/choice",
                   json={"option_id": r["options"][0]["id"], "save_trip": True})
        b.put("/api/carpool/profile", json={"available": True, "role": "driver", "seats": 3,
                                            "phone": "98450 12345", "share_phone": True, "note": "Leaves 8:30",
                                            "save_commute_from_last_trip": True})
        a.put("/api/carpool/profile", json={"available": True, "role": "rider", "phone": "+91 99000 11111",
                                            "share_phone": False, "save_commute_from_last_trip": True})
        board = a.get("/api/carpool/board").json()
        assert board["me"]["commute_source"] == "saved commute"
        hit = next(m for m in board["app_matches"] if m["name"] == bname)
        assert "contact" not in hit and hit["role"] == "driver" and hit["compatibility_pct"] > 0
        assert board["dataset_matches"] == []          # no simulated colleagues
        req = a.post("/api/carpool/requests", json={"to_ref": hit["ref"], "message": "Share a ride?"}).json()
        assert req["status"] == "pending" and "contact" not in req
        assert a.post("/api/carpool/requests", json={"to_ref": hit["ref"]}).status_code == 409
        assert b.get("/api/carpool/requests/count").json()["pending_incoming"] == 1
        incoming = next(r for r in b.get("/api/carpool/board").json()["requests"] if r["direction"] == "incoming")
        assert incoming["other"]["name"] == "Asha" and "contact" not in incoming
        assert a.post(f"/api/carpool/requests/{req['id']}/respond", json={"accept": True}).status_code == 404
        acc = b.post(f"/api/carpool/requests/{req['id']}/respond", json={"accept": True}).json()
        assert acc["status"] == "accepted"
        assert acc["contact"]["email"] == f"a{pid}@corp.com" and acc["contact"]["phone"] is None  # A didn't share phone
        hit2 = next(m for m in a.get("/api/carpool/board").json()["app_matches"] if m["name"] == bname)
        assert hit2["contact"]["phone"] == "98450 12345"
        assert hit2["contact"]["whatsapp_url"] == "https://wa.me/919845012345"


def test_city_trip_avoids_airport_buses_and_offers_metro_last_mile(client):
    """JP Nagar 1st Phase -> Whitefield IT Zone: no KIA airport buses, no 3+ bus
    chains when a Metro option exists, and a Metro + feeder/auto option."""
    r = client.post("/api/recommendations", json={
        "origin": {"lat": 12.9113, "lon": 77.5745}, "destination_office_id": "whitefield",
        "date": DATE, "time": "08:30", "profile": "green_first"}).json()
    routes = [l.get("route") or "" for o in r["options"] for l in o["legs"] if l["type"] == "bus"]
    assert not any(str(x).upper().startswith("KIA") for x in routes)
    assert not any(o["family"] == "bus" and o["transfers"] >= 2 for o in r["options"])
    combos = [o for o in r["options"] if o["family"] == "metro_combo"]
    assert combos and any("Metro" in o["chain"][1] or "Line" in " ".join(o["chain"]) for o in combos)
    assert len({o["title"] for o in combos}) == len(combos)
    for o in combos:
        assert o["walking"]["total_m"] <= r["personalisation"]["constraints"]["max_total_walking_m"]
        assert o["cost"]["amount_inr"] > 0 and o["emissions"]["estimate_kg_co2e"] > 0


def test_airport_trip_may_use_airport_buses():
    from app.routing.bmtc_latest_planner import plan_bmtc_latest_from_gps, is_airport_trip
    assert is_airport_trip(12.9767, 77.5713, 13.1989, 77.7068)
    assert not is_airport_trip(12.9113, 77.5745, 12.9698, 77.75)
    res = plan_bmtc_latest_from_gps(12.9767, 77.5713, 13.1989, 77.7068, DATE, "08:00")
    assert res["status"] == "success" and res["airport_routes_included"] is True


def test_registered_colleague_appears_in_recommendations_without_location():
    import time as _t
    from fastapi.testclient import TestClient
    tag = f"{os.getpid()}{int(_t.time() * 1000)}"
    with TestClient(app) as a, TestClient(app) as b:
        a.post("/api/auth/register", json={"email": f"ra{tag}@corp.com", "password": "secret123", "name": "Asha"})
        b.post("/api/auth/register", json={"email": f"rb{tag}@corp.com", "password": "secret123", "name": f"Bala {tag}"})
        rb = b.post("/api/recommendations", json={**COMMUTE, "time": "08:40"}).json()
        b.post(f"/api/recommendations/{rb['request_id']}/choice",
               json={"option_id": rb["options"][0]["id"], "save_trip": True})
        b.put("/api/carpool/profile", json={"available": True, "role": "driver", "seats": 3})
        r = a.post("/api/recommendations", json={**COMMUTE, "time": "08:30", "profile": "balanced"}).json()
        real = [o for o in r["options"] if o["family"] == "carpool" and o["carpool"]["real_colleagues"]]
        assert real, [o["title"] for o in r["options"]]
        assert any(p["name"] == f"Bala {tag}" for p in real[0]["carpool"]["partners"])
        assert real[0]["legs"][0]["pickups"] == []
        assert all("home_lat" not in p for p in real[0]["carpool"]["partners"])


def test_login_rate_limit_and_password_reset_tool():
    import time as _t
    from fastapi.testclient import TestClient
    from app.tools.reset_password import main as reset
    email = f"rl{os.getpid()}{int(_t.time() * 1000)}@corp.com"
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": email, "password": "secret123"})
        c.post("/api/auth/logout")
        codes = [c.post("/api/auth/login", json={"email": email, "password": "wrongpass"}).status_code for _ in range(6)]
        assert codes[:5] == [401] * 5 and codes[5] == 429
        import app.main as M
        M._FAILED_LOGINS.pop(email, None)
        assert reset(["x", email, "brandnew123"]) == 0
        assert c.post("/api/auth/login", json={"email": email, "password": "brandnew123"}).status_code == 200


def test_ride_hailing_ml_models_served_and_beat_baseline(client):
    r = client.get("/api/ml/models").json()
    card = r["ride_hailing"]
    assert card["data"]["test_date"] not in card["data"]["train_dates"]          # honest hold-out
    for name in ("demand", "quote_rate", "completion", "fare"):
        t = card["targets"][name]
        assert t["champion"] in ("model", "baseline")
        if t["champion"] == "model":
            assert t["model"]["rmse"] < t["baseline_hour_of_day"]["rmse"]
    m = client.get("/api/demand", params={"hour": 18}).json()
    assert m["model"]["type"] == "ml" and 0 < m["trip_success_probability"] <= m["quote_probability"]
    assert r["fare_validation"]["wards"] > 100


def test_ml_artifact_retrains_when_missing(tmp_path, monkeypatch):
    import app.ml.ride_hailing_model as RM
    import app.ml.train_ride_hailing as TR
    monkeypatch.setattr(TR, "OUT_DIR", tmp_path)
    monkeypatch.setattr(RM, "ARTIFACT", tmp_path / "model.joblib")
    monkeypatch.setattr(RM, "CARD", tmp_path / "model_card.json")
    RM.load.cache_clear(); RM.hourly_curve.cache_clear()
    try:
        assert RM.load() is not None and (tmp_path / "model.joblib").exists()
        assert len(RM.hourly_curve()) == 24
    finally:
        RM.load.cache_clear(); RM.hourly_curve.cache_clear()


def test_carpool_board_matches_the_planned_trip_not_just_regular_commutes():
    """Regression: two users with the same 09:00 regular commute must NOT match
    a 19:42 Jayanagar -> Peenya trip; they must match when both plan that trip."""
    import time as _t
    from fastapi.testclient import TestClient
    tag = f"{os.getpid()}{int(_t.time() * 1000)}"
    jayanagar, orr, peenya = (12.9250, 77.5938), (12.9352, 77.6950), (13.0285, 77.5197)
    with TestClient(app) as a, TestClient(app) as b:
        for c, n in ((a, "pa"), (b, "pb")):
            c.post("/api/auth/register", json={"email": f"{n}{tag}@corp.com", "password": "secret123", "name": f"{n}{tag}"})
            # regular commute: Jayanagar -> ORR at 09:00, via a saved trip
            r = c.post("/api/recommendations", json={"origin": {"lat": jayanagar[0], "lon": jayanagar[1]},
                       "destination": {"lat": orr[0], "lon": orr[1]}, "date": DATE, "time": "09:00"}).json()
            c.post(f"/api/recommendations/{r['request_id']}/choice", json={"option_id": r["options"][0]["id"], "save_trip": True})
            c.put("/api/carpool/profile", json={"available": True, "role": "either", "seats": 3,
                                                "save_commute_from_last_trip": True})
        trip = {"olat": jayanagar[0], "olon": jayanagar[1], "dlat": peenya[0], "dlon": peenya[1],
                "time": "19:42", "date": DATE}
        names = lambda board: [m["name"] for m in board["app_matches"]]
        # Regular commute view: they match (same 09:00 commute)
        assert f"pb{tag}" in names(a.get("/api/carpool/board").json())
        # Planned 19:42 Peenya trip: B is not travelling then -> no match
        board = a.get("/api/carpool/board", params=trip).json()
        assert board["me"]["commute_source"] == "planned trip"
        assert f"pb{tag}" not in names(board)
        # B plans and saves the same evening trip -> now they match, based on B's planned trip
        r = b.post("/api/recommendations", json={"origin": {"lat": jayanagar[0], "lon": jayanagar[1]},
                   "destination": {"lat": peenya[0], "lon": peenya[1]}, "date": DATE, "time": "19:50"}).json()
        b.post(f"/api/recommendations/{r['request_id']}/choice", json={"option_id": r["options"][0]["id"], "save_trip": True})
        hit = [m for m in a.get("/api/carpool/board", params=trip).json()["app_matches"] if m["name"] == f"pb{tag}"]
        assert hit and "planned trip" in hit[0]["basis"] and hit[0]["departure_difference_min"] == 8
        req = a.post("/api/carpool/requests", json={"to_ref": hit[0]["ref"], "trip": trip}).json()
        assert req["message"].startswith(f"Trip on {DATE} at 19:42")


def test_tumakuru_trips_use_real_trains_and_intercity_buses(client):
    """Tumakuru -> Peenya: real daily trains (published timetable) and the BMTC Vajra Vistara route."""
    r = client.post("/api/recommendations", json={
        "origin": {"lat": 13.3405, "lon": 77.1025}, "destination_office_id": "peenya",
        "date": DATE, "time": "07:00", "profile": "green_first"}).json()
    fams = {o["family"] for o in r["options"]}
    assert "train" in fams, [o["title"] for o in r["options"]]
    train = next(o for o in r["options"] if o["family"] == "train")
    tleg = next(l for l in train["legs"] if l["type"] == "train")
    from app.services.rail import trains
    published = {t["no"]: t for t in trains()}
    t = published[tleg["route"]]
    times = {s["code"]: s for s in t["stops"]}
    dep = times[tleg["from"]["stop_id"]]["dep"]
    assert tleg["departure_time"] == f"{dep // 60:02d}:{dep % 60:02d}"     # exactly the published time
    assert t["days"] == "daily" and tleg["departure_time"] >= "07:00"
    assert "auto" not in fams                                               # no 50 km auto rides
    buses = [l.get("route") for o in r["options"] for l in o["legs"] if l["type"] == "bus"]
    assert any(str(b).startswith("VV-EXP TMK") for b in buses)


def test_tumakuru_is_inside_coverage_and_delhi_is_not(client):
    ok = client.post("/api/recommendations", json={"origin": {"lat": 13.3405, "lon": 77.1025},
                                                   "destination": {"lat": 13.3162, "lon": 77.1481},
                                                   "date": DATE, "time": "09:00"})
    assert ok.status_code == 200 and ok.json()["options"]
    assert client.get("/api/places/search", params={"q": "tumakuru"}).json()["results"]


def test_shuttle_planner_targets_underserved_wards(admin):
    r = admin.get("/api/shuttles/plan", params={"office": "whitefield", "max_vehicles": 6}).json()
    s = r["summary"]
    assert 0 < s["vehicles"] <= 6 and s["riders"] <= 6 * s["capacity"]
    for route in r["routes"]:
        assert route["riders"] <= s["capacity"] and route["max_ride_min"] <= 75 + 1e-6
        assert sum(x["boardings"] for x in route["stops"]) == route["riders"]
    under = {w["ward"] for w in r["service_gaps"]["wards"] if w["underserved"]}
    served_wards = {w for route in r["routes"] for st in route["stops"] for w in st["wards"]}
    assert served_wards <= under                                  # only underserved wards get shuttles
    assert s["annual_co2e_saved_tonnes"] > 0 and s["cost_per_tonne_inr"] > 0


def test_incentive_optimiser_respects_budget_and_matches_twin(admin):
    r = admin.get("/api/incentives/optimise", params={"office": "whitefield", "monthly_budget_inr": 100000,
                                                       "shuttle_vehicles": 4}).json()
    res = r["result"]
    assert res["annual_spend_inr"] <= 100000 * 12 + 1
    curve = [p["inr_per_tonne"] for p in r["curve"]]
    assert curve == sorted(curve)                                  # cheapest abatement first
    tc = r["twin_check"]
    assert abs((tc["annual_baseline_tonnes"] - tc["annual_after_tonnes"]) - res["annual_co2e_saved_tonnes"]) < 0.2
    bigger = admin.get("/api/incentives/optimise", params={"office": "whitefield", "monthly_budget_inr": 300000,
                                                            "shuttle_vehicles": 4}).json()
    assert bigger["result"]["annual_co2e_saved_tonnes"] >= res["annual_co2e_saved_tonnes"]


def test_company_pages_are_admin_only(client, admin):
    """Employees can't see company-wide data; admins can, and can change roles."""
    import time as _t
    tag = f"{os.getpid()}{int(_t.time() * 1000)}"
    with TestClient(app) as emp:
        r = emp.post("/api/auth/register", json={"email": f"emp{tag}@corp.com", "password": "secret123", "name": "Emp"})
        assert r.json()["user"]["role"] == "employee"
        for path in ("/api/clusters", "/api/population", "/api/shuttles/plan", "/api/incentives/optimise",
                     "/api/digital-twin/presets", "/api/admin/users"):
            assert emp.get(path).status_code == 403, path
        assert emp.post("/api/digital-twin/simulate", json={}).status_code == 403
        assert client.get("/api/clusters").status_code == 401            # not signed in
        assert emp.get("/api/auth/me").json()["user"]["role"] == "employee"
        assert admin.get("/api/auth/me").json()["user"]["role"] == "admin"
        assert admin.patch(f"/api/admin/users/emp{tag}@corp.com/role", json={"role": "admin"}).json()["role"] == "admin"
        assert emp.get("/api/clusters").status_code == 200                # promoted: no re-login needed
        assert admin.patch(f"/api/admin/users/emp{tag}@corp.com/role", json={"role": "employee"}).status_code == 200
        assert emp.get("/api/clusters").status_code == 403


def test_return_trip_plans_the_reverse_direction(client):
    """Coming back = destination -> origin at the return time; carpools look at colleagues' return trips."""
    out = client.post("/api/recommendations", json={**COMMUTE, "time": "08:30"}).json()
    back = client.post("/api/recommendations", json={"origin": COMMUTE["destination"], "destination": COMMUTE["origin"],
                                                    "date": DATE, "time": "18:00"}).json()
    assert out["options"] and back["options"]
    assert back["request"]["origin"]["lat"] == COMMUTE["destination"]["lat"]
    assert all(o["depart_time"] >= "18:00" for o in back["options"] if o.get("depart_time"))


def test_options_carry_official_booking_links(rec):
    """Every option says where to book or pay; Metro legs point to BMRCL, autos to ride-hailing apps."""
    for o in rec["options"]:
        assert o["booking"], o["title"]
        kinds = {b["provider"] for b in o["booking"]}
        assert "Google Maps" in kinds
        types = {l["type"] for l in o["legs"]}
        if "metro" in types:
            assert "Namma Metro (BMRCL)" in kinds and "Metro QR ticket on WhatsApp" in kinds
        if o["family"] in ("auto", "cab"):
            assert "Namma Yatri" in kinds
        for b in o["booking"]:
            for url in (b.get("android"), b.get("ios"), b.get("web")):
                assert url is None or url.startswith("https://")


def test_cheaper_alternative_saves_money_without_much_extra_time(rec):
    """The pop-up suggestion: never an own vehicle, saves >= Rs 10 and 10 %, at most +10 min or +25 %."""
    by_id = {o["id"]: o for o in rec["options"]}
    for o in rec["options"]:
        c = o.get("cheaper_alternative")
        if not c:
            continue
        alt = by_id[c["option_id"]]
        assert alt["family"] not in ("bicycle", "two_wheeler", "car")
        saving = o["cost"]["amount_inr"] - alt["cost"]["amount_inr"]
        assert saving >= max(10, 0.10 * o["cost"]["amount_inr"]) - 0.5 and abs(saving - c["saves_inr"]) <= 0.5
        assert alt["duration_min"] - o["duration_min"] <= max(10, 0.25 * o["duration_min"]) + 0.5
    cab = next((o for o in rec["options"] if o["family"] == "cab"), None)
    if cab and any(o["family"] in ("bus", "metro", "bus_metro", "auto") for o in rec["options"]):
        assert cab["cheaper_alternative"] is not None
