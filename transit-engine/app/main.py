"""FastAPI backend for the Intelligent Sustainable Commute Recommendation System.

Run from the project root (the folder that contains app/ and data/):

    uvicorn app.main:app --host 0.0.0.0 --port 8000

Interactive API docs: http://localhost:8000/docs
"""
from __future__ import annotations

from app.certs import install_extra_ca
install_extra_ca()   # before any HTTPS client is created
import os
import threading
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import (ROLES, SessionLocal, User, TripChoice, RecommendationLog, UserAccount, LoginSession,
                          SavedTrip, CarpoolRequest, init_db, DATABASE_URL)
from app.security import create_session_token, hash_password, hash_session_token, verify_password
from app.schemas import (RecommendationRequest, ChoiceRequest, UserCreate, UserUpdate, TwinScenario,
                         RegisterRequest, LoginRequest, TripIn, GoogleLogin, CarpoolProfileIn,
                         CarpoolRequestIn, CarpoolRespond, TripSpec,
                         EmissionRequest)
from app.services import emissions as E
from app.services import preferences as P
from app.services.places import OFFICE_PRESETS, search_places
from app.services.context import get_weather, weather_effects, traffic_profile
from app.services.demand_pricing import market_state, daily_curve
from app.services import employees as EMP
from app.services import digital_twin as TWIN
from app.services.costs import fuel_cost, ENERGY_PRICES_INR

IST = timezone(timedelta(hours=5, minutes=30))
BMTC_FEED_VALIDITY = ("2026-11-09", "2027-11-09")
API_VERSION = "2.0.0"

@asynccontextmanager
async def lifespan(_app):
    init_db()
    if os.getenv("SKIP_WARMUP") != "1":
        threading.Thread(target=_warm_up, daemon=True).start()
    else:
        WARM["state"] = "lazy"
    yield


app = FastAPI(title="Sustainable Commute API", version=API_VERSION, lifespan=lifespan,
              description="Multimodal, personalised, emissions-aware commute recommendations for "
                          "Bengaluru employees, with an organisation-level Digital Twin.")

origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=origins != ["*"],
                   allow_methods=["*"], allow_headers=["*"])

WARM = {"state": "starting", "started_at": None, "finished_at": None, "steps": {}, "error": None}


def _warm_up():
    """Load the heavy datasets once so the first user request is fast."""
    WARM["state"], WARM["started_at"] = "warming", time.time()
    steps = [
        ("walking_graph", lambda: __import__("app.routing.planner", fromlist=["x"]).load_walking_data()),
        ("metro_entrances", lambda: __import__("app.routing.planner", fromlist=["x"])._entrance_nodes()),
        ("bmtc_timetable", lambda: __import__("app.routing.bmtc_latest_planner", fromlist=["x"]).load_bmtc_latest_data()),
        ("bmtc_today", lambda: __import__("app.routing.bmtc_latest_planner", fromlist=["x"])
            .load_bmtc_connections_for_date(datetime.now(IST).strftime("%Y-%m-%d"))),
        ("bmtc_shape_index", lambda: __import__("app.services.carbon", fromlist=["x"])._shape_distance_index()),
        ("employees", EMP.load_employees),
        ("twin_population", TWIN.population),
        ("bmtc_fare_curve", TWIN.bmtc_fare_curve),
        ("namma_yatri", lambda: __import__("app.services.demand_pricing", fromlist=["x"]).hourly_profile()),
        ("ride_hailing_ml", lambda: __import__("app.ml.ride_hailing_model", fromlist=["x"]).hourly_curve()),
    ]
    try:
        for name, fn in steps:
            t = time.time()
            fn()
            WARM["steps"][name] = round(time.time() - t, 1)
        WARM["state"] = "ready"
    except Exception as exc:  # keep serving; planners will load lazily
        WARM["state"], WARM["error"] = "degraded", f"{type(exc).__name__}: {exc}"
    WARM["finished_at"] = time.time()


def _now_ist():
    return datetime.now(IST)


def _resolve_datetime(date, time_):
    now = _now_ist()
    d = date or now.strftime("%Y-%m-%d")
    t = time_ or now.strftime("%H:%M")
    try:
        datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(422, "Invalid date/time.")
    if not (BMTC_FEED_VALIDITY[0] <= d <= BMTC_FEED_VALIDITY[1]):
        raise HTTPException(422, f"Date {d} is outside the BMTC timetable validity "
                                 f"({BMTC_FEED_VALIDITY[0]} to {BMTC_FEED_VALIDITY[1]}).")
    return d, t


def _user_dict(u: User | None):
    if not u:
        return None
    return {"id": u.id, "name": u.name, "employee_id": u.employee_id,
            "preferences": u.preferences or {}, "vehicle": u.vehicle, "weights": u.weights,
            "choice_count": u.choice_count or 0,
            "top_priorities": P.explain_weights(P.normalise_weights(u.weights)) if u.weights else None,
            "created_at": u.created_at.isoformat() if u.created_at else None}


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "version": API_VERSION, "warmup": WARM, "server_time_ist": _now_ist().isoformat(),
            "database": DATABASE_URL.split("://")[0]}


@app.get("/api/meta")
def meta():
    return {
        "offices": OFFICE_PRESETS,
        "profiles": {k: P.normalise_weights(v) for k, v in P.PROFILES.items()},
        "default_profile": P.DEFAULT_PROFILE,
        "families": {"metro": "Walk + Metro", "bus": "BMTC Bus", "bus_metro": "Bus + Metro", "carpool": "Carpool",
                     "walk": "Walk", "auto": "Auto-rickshaw", "cab": "Cab", "two_wheeler": "Two-wheeler",
                     "car": "Drive alone", "bicycle": "Cycle",
                     "metro_combo": "Metro + auto / feeder bus", "train": "Train (Bengaluru-Tumakuru)"},
        "vehicle_fuels": sorted(E.FUEL_FACTORS),
        "default_vehicles": E.DEFAULT_VEHICLES,
        "energy_prices_inr": ENERGY_PRICES_INR,
        "bmtc_feed_validity": BMTC_FEED_VALIDITY,
        "office_zones": [o["name"] for o in OFFICE_PRESETS],
        "ranking_features": P.FEATURES,
    }


@app.get("/api/places/search")
def places(q: str = Query(..., min_length=2), limit: int = Query(8, ge=1, le=20)):
    return {"query": q, "results": search_places(q, limit)}


@app.get("/api/context")
def context(lat: float = 12.9716, lon: float = 77.5946, date: str | None = None, time_: str | None = Query(None, alias="time")):
    d, t = _resolve_datetime(date, time_)
    when = datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
    wx = get_weather(lat, lon, when)
    fx = weather_effects(wx)
    return {"when": f"{d} {t}", "weather": wx, "weather_effects": fx, "traffic": traffic_profile(when),
            "ride_hailing_market": market_state(when.hour, fx)}


# ---------------------------------------------------------------------------
# Accounts & sessions (PBKDF2 passwords, revocable hashed session tokens in an
# HttpOnly cookie). The account email is also the commute-profile user id.
# ---------------------------------------------------------------------------
SESSION_COOKIE = "smartcommute_session"
SESSION_DURATION = timedelta(days=14)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


def _utcnow():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _valid_email(email: str) -> bool:
    local, sep, domain = email.partition("@")
    return bool(sep and local and "." in domain and not any(c.isspace() for c in email))


def _start_session(db, email: str, response: Response, remember: bool = True):
    token = create_session_token()
    expires = _utcnow() + SESSION_DURATION
    db.add(LoginSession(token_hash=hash_session_token(token), user_email=email, expires_at=expires))
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, max_age=int(SESSION_DURATION.total_seconds()) if remember else None,
                        httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/api")


def session_email(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    with SessionLocal() as db:
        sess = db.get(LoginSession, hash_session_token(token))
        if not sess:
            return None
        if _aware(sess.expires_at) <= _utcnow():
            db.delete(sess)
            db.commit()
            return None
        return sess.user_email


def require_email(request: Request) -> str:
    email = session_email(request)
    if not email:
        raise HTTPException(401, "Please sign in to continue.")
    return email


def _admin_emails() -> set:
    """ADMIN_EMAILS in .env / environment: comma-separated emails promoted to admin when they sign in."""
    return {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}


def _account_info(db, email: str) -> dict:
    acc = db.get(UserAccount, email)
    role = (acc.role if acc else None) or "employee"
    if acc and role != "admin" and email in _admin_emails():
        acc.role = role = "admin"
        db.commit()
    return {"email": email, "role": role}


def require_admin(request: Request) -> str:
    email = require_email(request)
    with SessionLocal() as db:
        if _account_info(db, email)["role"] != "admin":
            raise HTTPException(403, "Company-wide data is only available to company admins.")
    return email


def _ensure_profile(db, email: str, name: str | None = None) -> User:
    u = db.get(User, email)
    if not u:
        u = User(id=email, name=name, preferences={}, weights=None, choice_count=0)
        db.add(u)
        db.commit()
    return u


def _resolve_user_id(request: Request, user_id: str | None) -> str | None:
    """'me' -> session user. A profile that belongs to an account is only
    reachable by that account's session."""
    email = session_email(request)
    if user_id in (None, "", "me"):
        if user_id == "me" and not email:
            raise HTTPException(401, "Please sign in to continue.")
        return email
    with SessionLocal() as db:
        if db.get(UserAccount, user_id) and user_id != email:
            raise HTTPException(403, "You can only access your own profile.")
    return user_id


@app.post("/api/auth/register", status_code=201)
def register(data: RegisterRequest, response: Response):
    email = _normalize_email(data.email)
    if not _valid_email(email):
        raise HTTPException(422, "Enter a valid email address.")
    with SessionLocal() as db:
        if db.get(UserAccount, email):
            raise HTTPException(409, "An account with this email already exists.")
        db.add(UserAccount(email=email, password_hash=hash_password(data.password)))
        db.commit()
        _ensure_profile(db, email, data.name)
        _start_session(db, email, response)
        return {"user": _account_info(db, email)}


# Brute-force protection: at most 5 failed sign-ins per email per 15 minutes.
_FAILED_LOGINS: dict = {}
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_S = 15 * 60


def _login_blocked(email: str) -> int:
    now = time.time()
    hits = [t for t in _FAILED_LOGINS.get(email, []) if now - t < LOGIN_WINDOW_S]
    _FAILED_LOGINS[email] = hits
    if len(hits) >= LOGIN_MAX_FAILURES:
        return int(LOGIN_WINDOW_S - (now - hits[0])) + 1
    return 0


@app.post("/api/auth/login")
def login(data: LoginRequest, response: Response):
    email = _normalize_email(data.email)
    wait = _login_blocked(email)
    if wait:
        raise HTTPException(429, f"Too many failed sign-in attempts. Try again in {wait // 60 + 1} minutes.")
    with SessionLocal() as db:
        acc = db.get(UserAccount, email)
        if acc and acc.password_hash == GOOGLE_ONLY_HASH:
            raise HTTPException(401, "This account uses Google sign-in. Use the 'Sign in with Google' button.")
        if not acc or not verify_password(data.password, acc.password_hash):
            _FAILED_LOGINS.setdefault(email, []).append(time.time())
            raise HTTPException(401, "Email or password is incorrect.")
        _FAILED_LOGINS.pop(email, None)
        _ensure_profile(db, email)
        _start_session(db, email, response, data.remember)
        return {"user": _account_info(db, email)}


@app.get("/api/auth/me")
def auth_me(request: Request):
    email = require_email(request)
    with SessionLocal() as db:
        return {"user": _account_info(db, email)}


@app.get("/api/admin/users")
def admin_users(request: Request):
    require_admin(request)
    with SessionLocal() as db:
        names = {u.id: u.name for u in db.query(User).all()}
        return {"users": [{"email": a.email, "name": names.get(a.email), "role": a.role or "employee"}
                          for a in db.query(UserAccount).order_by(UserAccount.email).all()]}


@app.patch("/api/admin/users/{email}/role")
def admin_set_role(email: str, body: dict, request: Request):
    me = require_admin(request)
    role = str((body or {}).get("role", "")).lower()
    if role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    with SessionLocal() as db:
        acc = db.get(UserAccount, email.strip().lower())
        if not acc:
            raise HTTPException(404, "No such account.")
        if role == "employee" and acc.role == "admin" and \
                db.query(UserAccount).filter(UserAccount.role == "admin").count() <= 1:
            raise HTTPException(409, "There must be at least one admin.")
        if acc.email == me and role == "employee" and acc.email in _admin_emails():
            raise HTTPException(409, "This email is listed in ADMIN_EMAILS; remove it there first.")
        acc.role = role
        db.commit()
        return {"email": acc.email, "role": acc.role}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with SessionLocal() as db:
            sess = db.get(LoginSession, hash_session_token(token))
            if sess:
                db.delete(sess)
                db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/api", secure=COOKIE_SECURE, httponly=True, samesite="lax")
    return {"message": "Signed out"}


def _serialize_trip(t: SavedTrip) -> dict:
    return {"id": t.id, "request_id": t.request_id, "option_id": t.option_id, "family": t.family,
            "origin": t.origin, "destination": t.destination,
            "origin_lat": t.origin_lat, "origin_lng": t.origin_lng,
            "destination_lat": t.destination_lat, "destination_lng": t.destination_lng,
            "mode": t.mode, "distance_km": t.distance_km, "time_minutes": t.time_minutes, "cost": t.cost,
            "co2_kg": t.co2_kg, "co2_saved_vs_drive_kg": t.co2_saved_vs_drive_kg,
            "money_saved_vs_drive_inr": t.money_saved_vs_drive_inr,
            "segments": t.segments or [], "created_at": t.created_at.isoformat()}


@app.get("/api/trips")
def list_trips(request: Request, limit: int = Query(20, ge=1, le=100)):
    email = require_email(request)
    with SessionLocal() as db:
        rows = db.query(SavedTrip).filter(SavedTrip.user_email == email) \
            .order_by(SavedTrip.created_at.desc()).limit(limit).all()
        return {"trips": [_serialize_trip(t) for t in rows]}


@app.post("/api/trips", status_code=201)
def save_trip(data: TripIn, request: Request):
    """Legacy endpoint (client-supplied values). Prefer /api/recommendations/{id}/choice
    with save_trip=true, which stores the backend's own numbers."""
    email = require_email(request)
    with SessionLocal() as db:
        t = SavedTrip(user_email=email, origin=data.origin, destination=data.destination,
                      origin_lat=data.origin_lat, origin_lng=data.origin_lng,
                      destination_lat=data.destination_lat, destination_lng=data.destination_lng,
                      mode=data.mode, distance_km=data.distance_km, time_minutes=data.time_minutes,
                      cost=data.cost, co2_kg=data.co2_kg,
                      segments=[seg.model_dump() for seg in data.segments])
        db.add(t)
        db.commit()
        return _serialize_trip(t)


# ---------------------------------------------------------------------------
# Recommendations + learning loop
# ---------------------------------------------------------------------------
@app.post("/api/recommendations")
def recommendations(req: RecommendationRequest, request: Request):
    from app.services.recommender import recommend
    req.user_id = _resolve_user_id(request, req.user_id)
    if req.destination is None and not req.destination_office_id:
        raise HTTPException(422, "Provide destination or destination_office_id.")
    if req.destination is not None:
        dest = (req.destination.lat, req.destination.lon)
    else:
        office = next((o for o in OFFICE_PRESETS if o["id"] == req.destination_office_id), None)
        if not office:
            raise HTTPException(404, f"Unknown office id {req.destination_office_id!r}")
        dest = (office["lat"], office["lon"])
    d, t = _resolve_datetime(req.date, req.time)

    with SessionLocal() as db:
        user = db.get(User, req.user_id) if req.user_id else None
        if req.user_id and not user and db.get(UserAccount, req.user_id):
            user = _ensure_profile(db, req.user_id)
        if req.user_id and not user:
            raise HTTPException(404, f"Unknown user {req.user_id!r}; create it with POST /api/users")
        udict = _user_dict(user) or {}
        app_partners = _app_partners_for_trip(db, req.user_id, (req.origin.lat, req.origin.lon), dest, t, d) \
            if req.user_id and db.get(UserAccount, req.user_id) else []
    try:
        result = recommend(
            (req.origin.lat, req.origin.lon), dest, d, t, user=udict, profile=req.profile,
            weights=req.weights.model_dump() if req.weights else None,
            preferences=req.preferences.model_dump(exclude_none=True) if req.preferences else None,
            vehicle=req.vehicle.model_dump(exclude_none=True) if req.vehicle else None,
            app_partners=app_partners)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if req.origin.accuracy_m and req.origin.accuracy_m > 200:
        result.setdefault("notes", []).insert(0, f"Your GPS accuracy is ~{req.origin.accuracy_m:.0f} m; "
                                                 "walking legs may be off. Adjust the pin if needed.")
    # A cached result reuses the computation but gets a fresh request id for choice logging.
    if result.get("cached"):
        result["request_id"] = uuid.uuid4().hex
    with SessionLocal() as db:
        db.add(RecommendationLog(
            request_id=result["request_id"], user_id=req.user_id,
            request=req.model_dump(mode="json"),
            options=[{"id": o["id"], "family": o["family"], "title": o["title"], "features": o["features"],
                      "co2e_kg": o["emissions"]["estimate_kg_co2e"], "cost_inr": o["cost"]["amount_inr"],
                      "duration_min": o["duration_min"], "distance_km": o["distance_km"],
                      "chain": o["chain"],
                      "segments": [{"mode": l["type"], "label": l.get("label") or l["type"],
                                    "color": l.get("color"), "positions": l.get("path") or []}
                                   for l in o["legs"]]} for o in result["options"]],
            recommended_option_id=result["recommended_option_id"]))
        db.commit()
    return result


@app.post("/api/recommendations/{request_id}/choice")
def record_choice(request_id: str, body: ChoiceRequest, request: Request):
    body.user_id = _resolve_user_id(request, body.user_id)
    with SessionLocal() as db:
        log = db.get(RecommendationLog, request_id)
        if not log:
            raise HTTPException(404, "Unknown request_id (recommendation not found).")
        ids = [o["id"] for o in log.options]
        if body.option_id not in ids:
            raise HTTPException(422, "option_id was not part of this recommendation.")
        idx = ids.index(body.option_id)
        user_id = body.user_id or log.user_id
        chosen = log.options[idx]
        baseline = next((o for o in log.options if o["family"] == "car"), None)
        learning = None
        if user_id:
            user = db.get(User, user_id)
            if not user:
                raise HTTPException(404, f"Unknown user {user_id!r}")
            prefs = user.preferences or {}
            start = P.normalise_weights(user.weights or P.PROFILES.get(prefs.get("profile") or P.DEFAULT_PROFILE))
            features = [o["features"] for o in log.options]
            new, diag = P.update_weights(start, features, idx)
            user.weights = new
            user.choice_count = (user.choice_count or 0) + 1
            learning = {"previous_weights": start, "new_weights": new, **diag,
                        "top_priorities": P.explain_weights(new)}
        saved_trip = None
        if body.save_trip:
            email = session_email(request)
            if not email:
                raise HTTPException(401, "Sign in to save trips.")
            rq = log.request or {}
            o_pt = rq.get("origin") or {}
            d_pt = rq.get("destination") or {}
            if not d_pt and rq.get("destination_office_id"):
                office = next((x for x in OFFICE_PRESETS if x["id"] == rq["destination_office_id"]), {})
                d_pt = {"lat": office.get("lat"), "lon": office.get("lon"), "label": office.get("name")}
            money = (baseline["cost_inr"] - chosen["cost_inr"]) if baseline and baseline["cost_inr"] is not None \
                and chosen["cost_inr"] is not None else None
            st = SavedTrip(user_email=email, request_id=request_id, option_id=body.option_id,
                           family=chosen["family"],
                           origin=body.origin_label or o_pt.get("label") or f"{o_pt.get('lat'):.5f}, {o_pt.get('lon'):.5f}",
                           destination=body.destination_label or d_pt.get("label") or f"{d_pt.get('lat'):.5f}, {d_pt.get('lon'):.5f}",
                           origin_lat=o_pt.get("lat"), origin_lng=o_pt.get("lon"),
                           destination_lat=d_pt.get("lat"), destination_lng=d_pt.get("lon"),
                           mode=chosen["title"], distance_km=chosen.get("distance_km") or 0.0,
                           time_minutes=int(round(chosen["duration_min"])), cost=chosen["cost_inr"],
                           co2_kg=chosen["co2e_kg"],
                           co2_saved_vs_drive_kg=round(baseline["co2e_kg"] - chosen["co2e_kg"], 3) if baseline else None,
                           money_saved_vs_drive_inr=round(money, 2) if money is not None else None,
                           segments=chosen.get("segments") or [])
            db.add(st)
            db.flush()
            saved_trip = _serialize_trip(st)
        db.add(TripChoice(user_id=user_id, request_id=request_id, chosen_option_id=body.option_id,
                          chosen_mode=chosen["family"], options=log.options,
                          context={"was_recommended": body.option_id == log.recommended_option_id,
                                   "chosen_co2e_kg": chosen["co2e_kg"], "chosen_cost_inr": chosen["cost_inr"],
                                   "chosen_title": chosen["title"],
                                   "baseline_co2e_kg": baseline["co2e_kg"] if baseline else None,
                                   "baseline_cost_inr": baseline["cost_inr"] if baseline else None}))
        db.commit()
    saved = (baseline["co2e_kg"] - chosen["co2e_kg"]) if baseline else None
    chosen_public = {k: v for k, v in chosen.items() if k != "segments"}
    return {"status": "recorded", "chosen": chosen_public,
            "co2e_saved_vs_drive_alone_kg": round(saved, 3) if saved is not None else None,
            "learning": learning, "saved_trip": saved_trip}


# ---------------------------------------------------------------------------
# Users / profiles
# ---------------------------------------------------------------------------
@app.post("/api/users", status_code=201)
def create_user(body: UserCreate):
    with SessionLocal() as db:
        uid = body.id or uuid.uuid4().hex[:12]
        if db.get(User, uid):
            raise HTTPException(409, "User id already exists.")
        prefs = body.preferences.model_dump(exclude_none=True) if body.preferences else {}
        u = User(id=uid, name=body.name, employee_id=body.employee_id, preferences=prefs,
                 vehicle=body.vehicle.model_dump(exclude_none=True) if body.vehicle else None, weights=None,
                 choice_count=0)
        db.add(u)
        db.commit()
        return _user_dict(u)


@app.get("/api/users/{user_id}")
def get_user(user_id: str, request: Request):
    user_id = _resolve_user_id(request, user_id)
    with SessionLocal() as db:
        u = db.get(User, user_id)
        if not u:
            raise HTTPException(404, "User not found")
        return _user_dict(u)


@app.patch("/api/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, request: Request):
    user_id = _resolve_user_id(request, user_id)
    with SessionLocal() as db:
        u = db.get(User, user_id)
        if not u:
            raise HTTPException(404, "User not found")
        if body.name is not None:
            u.name = body.name
        if body.employee_id is not None:
            u.employee_id = (body.employee_id or "").strip()[:64] or None   # company employee ID (label only)
        if body.preferences is not None:
            u.preferences = {**(u.preferences or {}), **body.preferences.model_dump(exclude_none=True)}
        if body.vehicle is not None:
            u.vehicle = body.vehicle.model_dump(exclude_none=True)
        if body.reset_learning:
            u.weights, u.choice_count = None, 0
        db.commit()
        return _user_dict(u)


@app.get("/api/users/{user_id}/history")
def user_history(user_id: str, request: Request, limit: int = Query(200, ge=1, le=1000)):
    user_id = _resolve_user_id(request, user_id)
    with SessionLocal() as db:
        if not db.get(User, user_id):
            raise HTTPException(404, "User not found")
        rows = db.query(TripChoice).filter(TripChoice.user_id == user_id) \
            .order_by(TripChoice.created_at.desc()).limit(limit).all()
        trips = [{"request_id": r.request_id, "chosen_mode": r.chosen_mode, "option_id": r.chosen_option_id,
                  "created_at": r.created_at.isoformat(), **(r.context or {})} for r in rows]
    with_base = [t for t in trips if t.get("baseline_co2e_kg") is not None]
    co2_saved = sum(t["baseline_co2e_kg"] - (t.get("chosen_co2e_kg") or 0) for t in with_base)
    money_trips = [t for t in with_base if t.get("baseline_cost_inr") is not None and t.get("chosen_cost_inr") is not None]
    money_saved = sum(t["baseline_cost_inr"] - t["chosen_cost_inr"] for t in money_trips)
    modes = {}
    for t in trips:
        modes[t["chosen_mode"]] = modes.get(t["chosen_mode"], 0) + 1
    daily = {}
    for t in with_base:
        day = t["created_at"][:10]
        d = daily.setdefault(day, {"date": day, "trips": 0, "co2e_saved_kg": 0.0, "money_saved_inr": 0.0})
        d["trips"] += 1
        d["co2e_saved_kg"] = round(d["co2e_saved_kg"] + t["baseline_co2e_kg"] - (t.get("chosen_co2e_kg") or 0), 3)
        if t in money_trips:
            d["money_saved_inr"] = round(d["money_saved_inr"] + t["baseline_cost_inr"] - t["chosen_cost_inr"], 2)
    return {"user_id": user_id, "trips": trips,
            "impact": {"trips": len(trips),
                       "trips_with_drive_alone_baseline": len(with_base),
                       "co2e_kg": round(sum(t.get("chosen_co2e_kg") or 0 for t in trips), 3),
                       "co2e_saved_kg": round(co2_saved, 3),
                       "money_saved_inr": round(money_saved, 2),
                       "shared_rides": modes.get("carpool", 0),
                       "accepted_recommendation_rate": round(sum(1 for t in trips if t.get("was_recommended")) / len(trips), 3) if trips else None,
                       "mode_counts": modes,
                       "daily": sorted(daily.values(), key=lambda d: d["date"])}}


# ---------------------------------------------------------------------------
# Employees, clusters, carpool
# ---------------------------------------------------------------------------
@app.get("/api/employees")
def list_employees(request: Request, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                   office: str | None = None, cluster_id: int | None = None):
    require_admin(request)
    """The Census-derived statistical population of one office (not real people)."""
    try:
        return EMP.employees_page(offset, limit, office, cluster_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/employees/{employee_id}")
def get_employee(request: Request, employee_id: str, office: str | None = None):
    require_admin(request)
    try:
        e = EMP.employee(employee_id, office)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if not e:
        raise HTTPException(404, "Not in this office's statistical population")
    e["nearest_home_metro"] = {"name": e.pop("home_metro"), "distance_km": round(float(e.pop("home_metro_km")), 2)}
    e["nearest_office_metro"] = {"name": e.pop("office_metro"), "distance_km": round(float(e.pop("office_metro_km")), 2)}
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in e.items()}


@app.get("/api/clusters")
def clusters(request: Request, office: str | None = None):
    require_admin(request)
    try:
        return EMP.cluster_summary(office)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/clusters/evaluate")
def clusters_evaluate(request: Request, k: int = Query(15, ge=2, le=60), office: str | None = None):
    require_admin(request)
    return EMP.recluster(k, office)


@app.get("/api/carpool/matches")
def carpool_matches():
    raise HTTPException(410, "Simulated colleagues were removed. Carpool matches come only from registered "
                             "colleagues: use /api/carpool/board.")


# ---------------------------------------------------------------------------
# Digital Twin, demand/pricing, emissions
# ---------------------------------------------------------------------------
@app.get("/api/digital-twin/presets")
def twin_presets(request: Request):
    require_admin(request)
    return {"presets": TWIN.preset_scenarios(), "defaults": TWIN.DEFAULT_SCENARIO}


@app.get("/api/digital-twin/baseline")
def twin_baseline(request: Request, office_zone: str | None = None):
    require_admin(request)
    try:
        return TWIN.simulate({"office_zone": office_zone})
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/digital-twin/simulate")
def twin_simulate(request: Request, body: TwinScenario):
    require_admin(request)
    sc = body.model_dump()
    include = sc.pop("include_employees")
    try:
        return TWIN.simulate(sc, include_employees=include)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/population")
def population_info(request: Request, office: str | None = None, headcount: int = Query(2000, ge=50, le=20000),
                    start_time: str = Query("09:30", pattern=r"^\d{2}:\d{2}$")):
    require_admin(request)
    from app.services.population import describe
    try:
        return describe(TWIN.population(office, headcount, start_time))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/shuttles/plan")
def shuttles_plan(request: Request, office: str | None = None, headcount: int = Query(2000, ge=50, le=20000),
                  start_time: str = Query("09:30", pattern=r"^\d{2}:\d{2}$"),
                  capacity: int = Query(40, ge=8, le=60), max_vehicles: int = Query(10, ge=1, le=40),
                  max_ride_min: int = Query(75, ge=20, le=150)):
    require_admin(request)
    from app.services.shuttles import plan_shuttles
    try:
        return plan_shuttles(office, headcount, start_time, capacity, max_vehicles, max_ride_min)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/incentives/optimise")
def incentives_optimise(request: Request, office: str | None = None, monthly_budget_inr: float = Query(200000, ge=0, le=1e8),
                        value_of_time: float = Query(179.2, ge=0, le=5000),
                        headcount: int = Query(2000, ge=50, le=20000),
                        start_time: str = Query("09:30", pattern=r"^\d{2}:\d{2}$"),
                        take_up_pct: float = Query(100, ge=0, le=100),
                        enabled: str = Query("metro_pass,bus_pass,carpool_credit,shuttle_seat"),
                        shuttle_capacity: int = Query(40, ge=8, le=60),
                        shuttle_vehicles: int = Query(10, ge=0, le=40)):
    require_admin(request)
    from app.services.incentives import optimise, LABELS
    kinds = tuple(k for k in enabled.split(",") if k in LABELS)
    if shuttle_vehicles == 0:
        kinds = tuple(k for k in kinds if k != "shuttle_seat")
    try:
        return optimise(office, monthly_budget_inr, value_of_time, headcount, start_time, kinds, take_up_pct,
                        shuttle_capacity, max(1, shuttle_vehicles))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/demand")
def demand(hour: int | None = Query(None, ge=0, le=23), rain: bool = False):
    fx = weather_effects({"rain_expected": rain, "temperature_c": 25})
    if hour is not None:
        return market_state(hour, fx)
    return {"hours": daily_curve(fx), "rain": rain}


@app.get("/api/ml/models")
def ml_models():
    """Model cards for the ML components (MLOps transparency)."""
    from app.ml.ride_hailing_model import model_card, load
    import json as _json
    load()   # trains on first use if the artifact is missing
    card = model_card()
    try:
        fare_val = _json.loads(Path("models/ride_hailing/fare_validation.json").read_text())
    except Exception:
        fare_val = None
    return {
        "ride_hailing": card,
        "fare_validation": fare_val,
        "preference_model": {
            "type": "Conditional-logit choice model, updated online from each route a user picks",
            "features": P.FEATURES, "learning_rate": P.LEARNING_RATE, "temperature": P.TEMPERATURE,
        },
        "how_to_retrain": "python -m app.ml.train_ride_hailing  (then: mlflow ui --backend-store-uri sqlite:///mlflow.db)",
    }


@app.get("/api/emissions/methodology")
def emissions_methodology():
    return E.methodology_notes()


@app.post("/api/emissions/estimate")
def emissions_estimate(body: EmissionRequest):
    v = body.vehicle.model_dump(exclude_none=True) if body.vehicle else None
    km = body.distance_km
    if body.mode == "bus":
        est, cost = E.transit(km, "bmtc_bus"), None
    elif body.mode == "metro":
        est, cost = E.transit(km, "metro"), None
    elif body.mode == "walk":
        est, cost = E.walking(km), None
    else:
        cat = {"car": "car_petrol", "carpool": "car_petrol", "two_wheeler": "two_wheeler_petrol",
               "auto": "auto_cng", "cab": "cab_diesel"}[body.mode]
        if v and v.get("fuel_type") in ("ev", "electric"):
            cat = "two_wheeler_ev" if body.mode == "two_wheeler" else ("auto_ev" if body.mode == "auto" else "car_ev")
        try:
            est = E.road_vehicle(km, cat, body.occupancy, v)
            cost = fuel_cost(km, cat, v) if body.mode in ("car", "carpool", "two_wheeler") else None
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    return {"mode": body.mode, "distance_km": km, "emissions": est.to_dict(), "operating_cost": cost}


# ---------------------------------------------------------------------------
# Google sign-in (Google Identity Services ID token, verified server-side)
# ---------------------------------------------------------------------------
def _load_dotenv():
    """Read KEY=VALUE lines from .env files so a local `uvicorn` run picks up the
    same settings as Docker. Real environment variables always win."""
    here = Path(__file__).resolve().parents[1]          # transit-engine/
    for path in (Path.cwd() / ".env", here / ".env", here.parent / ".env"):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            if key.strip() and value and not os.environ.get(key.strip()):
                os.environ[key.strip()] = value


_load_dotenv()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CONFIG_ERROR = None
if GOOGLE_CLIENT_ID and not GOOGLE_CLIENT_ID.endswith(".apps.googleusercontent.com"):
    GOOGLE_CONFIG_ERROR = ("GOOGLE_CLIENT_ID is not a client ID (it must end with .apps.googleusercontent.com"
                           + ("; you pasted the client secret" if GOOGLE_CLIENT_ID.startswith("GOCSPX-") else "") + ").")
    GOOGLE_CLIENT_ID = ""
GOOGLE_ONLY_HASH = "!google-oauth"   # never matches a PBKDF2 hash -> no password login


def _verify_google_token(credential: str) -> dict:
    """Verify signature, audience, issuer and expiry of a Google ID token."""
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    return id_token.verify_oauth2_token(credential, google_requests.Request(), GOOGLE_CLIENT_ID)


@app.get("/api/auth/config")
def auth_config():
    return {"google_client_id": GOOGLE_CLIENT_ID or None, "google_enabled": bool(GOOGLE_CLIENT_ID),
            "problem": GOOGLE_CONFIG_ERROR}


@app.post("/api/auth/google")
def google_login(data: GoogleLogin, response: Response):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google sign-in is not configured on the server (set GOOGLE_CLIENT_ID).")
    try:
        info = _verify_google_token(data.credential)
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            raise HTTPException(502, "Google sign-in could not be checked: this network (or antivirus) intercepts HTTPS "
                                     "with its own certificate, which the server doesn't trust. Put that root "
                                     "certificate in the certs folder next to docker-compose.yml and restart, or use "
                                     "another network. See README: 'Certificate errors'.")
        raise HTTPException(401, f"Google sign-in could not be verified: {exc}")
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(401, "Invalid Google token issuer.")
    email = _normalize_email(info.get("email") or "")
    if not email or not info.get("email_verified"):
        raise HTTPException(401, "Your Google account email is not verified.")
    with SessionLocal() as db:
        if not db.get(UserAccount, email):
            db.add(UserAccount(email=email, password_hash=GOOGLE_ONLY_HASH))
            db.commit()
        u = _ensure_profile(db, email, info.get("name"))
        if not u.name and info.get("name"):
            u.name = info["name"]
            db.commit()
        _start_session(db, email, response, True)
        return {"user": {**_account_info(db, email), "name": info.get("name")}}


# ---------------------------------------------------------------------------
# Carpool board: real registered colleagues + simulated dataset colleagues.
# Contact details are only shared after a request is accepted.
# ---------------------------------------------------------------------------
import hashlib as _hashlib


def _ref(email: str) -> str:
    return _hashlib.sha256(("carpool:" + email).encode()).hexdigest()[:16]


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}"


def _carpool_profile(u: User) -> dict:
    cp = (u.preferences or {}).get("carpool") or {}
    return {"available": bool(cp.get("available")), "role": cp.get("role", "either"),
            "seats": int(cp.get("seats", 1)), "phone": cp.get("phone"), "share_phone": bool(cp.get("share_phone")),
            "note": cp.get("note")}


def _last_trip_commute(db, email: str):
    t = db.query(SavedTrip).filter(SavedTrip.user_email == email).order_by(SavedTrip.created_at.desc()).first()
    if not t:
        return None
    dep = None
    if t.request_id:
        log = db.get(RecommendationLog, t.request_id)
        dep = ((log.request or {}).get("time")) if log else None
    if not dep:
        dep = _aware(t.created_at).astimezone(IST).strftime("%H:%M")
    return {"home_lat": t.origin_lat, "home_lon": t.origin_lng, "office_lat": t.destination_lat,
            "office_lon": t.destination_lng, "departure_time": dep, "home_label": t.origin,
            "office_label": t.destination}


def _user_commute(db, u: User):
    """Regular commute: saved commute > last saved trip."""
    saved = (u.preferences or {}).get("commute")
    if saved:
        return saved, "saved commute"
    last = _last_trip_commute(db, u.id)
    return (last, "last saved trip") if last else (None, None)


def _commute_match(a: dict, b: dict):
    lim = EMP.DEFAULT_MATCH_LIMITS
    og = float(EMP._hav(a["home_lat"], a["home_lon"], b["home_lat"], b["home_lon"]))
    dg = float(EMP._hav(a["office_lat"], a["office_lon"], b["office_lat"], b["office_lon"]))
    tg = abs(EMP.to_minutes(a["departure_time"]) - EMP.to_minutes(b["departure_time"]))
    direct = max(0.5, float(EMP._hav(a["home_lat"], a["home_lon"], a["office_lat"], a["office_lon"])))
    detour = (og + dg) / direct
    if og > lim["max_origin_km"] or dg > lim["max_destination_km"] or tg > lim["max_departure_diff_min"] \
            or detour > lim["max_detour_ratio"]:
        return None
    score = (0.35 * og / lim["max_origin_km"] + 0.20 * dg / lim["max_destination_km"]
             + 0.20 * tg / max(1, lim["max_departure_diff_min"]) + 0.25 * detour / lim["max_detour_ratio"])
    return {"pickup_distance_km": round(og, 2), "office_distance_km": round(dg, 2),
            "departure_difference_min": int(tg), "detour_ratio": round(detour, 3),
            "match_score": round(score, 4), "compatibility_pct": max(0, round((1 - score) * 100))}


def _match_trip_to_commute(trip: dict, their: dict):
    """Match a planned trip against a colleague's regular commute. Evening trips
    (from 14:00) are compared with the colleague's return journey (office -> home,
    leaving ~9 h after their morning departure)."""
    m = _commute_match(trip, their)
    if m:
        return {**m, "direction": "outbound", "their_time": their["departure_time"]}
    if EMP.to_minutes(trip["departure_time"]) >= EMP.EVENING_FROM_MINUTES and \
            EMP.to_minutes(their["departure_time"]) < EMP.EVENING_FROM_MINUTES:
        t = (EMP.to_minutes(their["departure_time"]) + EMP.WORKDAY_MINUTES) % (24 * 60)
        back = {"home_lat": their["office_lat"], "home_lon": their["office_lon"],
                "office_lat": their["home_lat"], "office_lon": their["home_lon"],
                "departure_time": f"{t // 60:02d}:{t % 60:02d}"}
        m = _commute_match(trip, back)
        if m:
            return {**m, "direction": "return", "their_time": back["departure_time"]}
    return None


def _their_trips_on(db, email: str, date: str) -> list:
    """Colleague's saved (chosen) trips for a given travel date."""
    out = []
    for t in db.query(SavedTrip).filter(SavedTrip.user_email == email).order_by(SavedTrip.created_at.desc()).limit(20):
        log = db.get(RecommendationLog, t.request_id) if t.request_id else None
        rq = (log.request or {}) if log else {}
        if rq.get("date") != date or not rq.get("time"):
            continue
        out.append({"home_lat": t.origin_lat, "home_lon": t.origin_lng, "office_lat": t.destination_lat,
                    "office_lon": t.destination_lng, "departure_time": rq["time"],
                    "home_label": t.origin, "office_label": t.destination})
    return out


def _best_colleague_match(db, u: User, trip: dict, trip_date: str | None):
    """Best match between my trip and what a colleague is doing then:
    their own planned trip that day, else their regular commute (morning or
    estimated return). Returns (match, their_commute, basis) or None."""
    best = None
    if trip_date:
        for t in _their_trips_on(db, u.id, trip_date):
            m = _commute_match(trip, t)
            if m and (best is None or m["match_score"] < best[0]["match_score"]):
                best = ({**m, "direction": "planned", "their_time": t["departure_time"]}, t,
                        f"their planned trip on {trip_date} at {t['departure_time']}")
    if best:
        return best
    their, _src = _user_commute(db, u)
    if not their:
        return None
    m = _match_trip_to_commute(trip, their)
    if not m:
        return None
    basis = ("their regular morning commute" if m["direction"] == "outbound"
             else f"their regular return trip (estimated ~{m['their_time']})")
    return m, their, basis


def _app_partners_for_trip(db, email: str, origin, dest, departure_time: str, trip_date: str | None = None) -> list:
    trip = {"home_lat": origin[0], "home_lon": origin[1], "office_lat": dest[0], "office_lon": dest[1],
            "departure_time": departure_time}
    out = []
    for u in db.query(User).filter(User.id != email).all():
        cp = _carpool_profile(u)
        if not cp["available"] or not db.get(UserAccount, u.id):
            continue
        hit = _best_colleague_match(db, u, trip, trip_date)
        if hit:
            m, _their, basis = hit
            out.append({"ref": _ref(u.id), "name": u.name or _mask(u.id), "role": cp["role"],
                        "seats": cp["seats"], "departure_time": m["their_time"], "direction": m["direction"],
                        "basis": basis,
                        "pickup_distance_km": m["pickup_distance_km"], "office_distance_km": m["office_distance_km"],
                        "departure_difference_min": m["departure_difference_min"], "match_score": m["match_score"],
                        "compatibility_pct": m["compatibility_pct"], "home_zone": "registered colleague"})
    return sorted(out, key=lambda x: x["match_score"])


def _contact(db, email: str) -> dict:
    u = db.get(User, email)
    cp = _carpool_profile(u) if u else {}
    phone = cp.get("phone") if cp.get("share_phone") else None
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits and len(digits) == 10:
        digits = "91" + digits
    return {"name": (u.name if u else None) or email.split("@")[0], "email": email, "phone": phone,
            "whatsapp_url": f"https://wa.me/{digits}" if phone else None,
            "mailto": f"mailto:{email}?subject=Carpool%20on%20SmartCommute"}


def _serialize_request(db, r: CarpoolRequest, me: str) -> dict:
    other = r.to_email if r.from_email == me else r.from_email
    ou = db.get(User, other)
    out = {"id": r.id, "direction": "outgoing" if r.from_email == me else "incoming", "status": r.status,
           "message": r.message, "created_at": r.created_at.isoformat(),
           "responded_at": r.responded_at.isoformat() if r.responded_at else None,
           "other": {"ref": _ref(other), "name": (ou.name if ou and ou.name else _mask(other))}}
    if r.status == "accepted":
        out["contact"] = _contact(db, other)
    return out


@app.get("/api/carpool/profile")
def carpool_profile_get(request: Request):
    email = require_email(request)
    with SessionLocal() as db:
        u = _ensure_profile(db, email)
        commute, source = _user_commute(db, u)
        return {"profile": _carpool_profile(u), "commute": commute, "commute_source": source}


@app.put("/api/carpool/profile")
def carpool_profile_put(body: CarpoolProfileIn, request: Request):
    email = require_email(request)
    with SessionLocal() as db:
        u = _ensure_profile(db, email)
        prefs = dict(u.preferences or {})
        prefs["carpool"] = body.model_dump(exclude={"save_commute_from_last_trip"})
        if body.save_commute_from_last_trip:
            last = _last_trip_commute(db, email)
            if not last:
                raise HTTPException(422, "No saved trip yet. Plan a commute and choose a route first.")
            prefs["commute"] = last
        u.preferences = prefs
        db.commit()
        commute, source = _user_commute(db, u)
        return {"profile": _carpool_profile(u), "commute": commute, "commute_source": source}


@app.get("/api/carpool/board")
def carpool_board(request: Request, limit: int = Query(24, ge=1, le=100),
                  olat: float | None = None, olon: float | None = None, dlat: float | None = None,
                  dlon: float | None = None, time_: str | None = Query(None, alias="time"),
                  date: str | None = None, olabel: str | None = None, dlabel: str | None = None):
    """Everything the Carpooling page needs in one call.

    With trip parameters (the trip planned on the Dashboard), colleagues are
    matched against that exact trip and time; otherwise against the user's
    regular commute."""
    email = require_email(request)
    trip_date = None
    with SessionLocal() as db:
        me = _ensure_profile(db, email)
        if None not in (olat, olon, dlat, dlon, time_):
            try:
                spec = TripSpec(olat=olat, olon=olon, dlat=dlat, dlon=dlon, time=time_,
                                date=date or _now_ist().strftime("%Y-%m-%d"), olabel=olabel, dlabel=dlabel)
            except Exception as exc:
                raise HTTPException(422, f"Invalid trip: {exc}")
            my_commute = {"home_lat": spec.olat, "home_lon": spec.olon, "office_lat": spec.dlat,
                          "office_lon": spec.dlon, "departure_time": spec.time,
                          "home_label": spec.olabel or "your start", "office_label": spec.dlabel or "your destination"}
            source, trip_date = "planned trip", spec.date
        else:
            my_commute, source = _user_commute(db, me)
            trip_date = _now_ist().strftime("%Y-%m-%d")
        reqs = db.query(CarpoolRequest).filter((CarpoolRequest.from_email == email) | (CarpoolRequest.to_email == email)) \
            .order_by(CarpoolRequest.created_at.desc()).all()
        by_other = {}
        for r in reqs:
            other = r.to_email if r.from_email == email else r.from_email
            if other not in by_other or by_other[other].status in ("declined", "cancelled"):
                by_other[other] = r
        app_matches = []
        if my_commute:
            for u in db.query(User).filter(User.id != email).all():
                if not db.get(UserAccount, u.id):
                    continue
                cp = _carpool_profile(u)
                r = by_other.get(u.id)
                if not cp["available"] and not (r and r.status == "accepted"):
                    continue
                hit = _best_colleague_match(db, u, my_commute, trip_date if source == "planned trip" else None)
                if not hit:
                    continue
                m, their, basis = hit
                item = {"ref": _ref(u.id), "name": u.name or _mask(u.id), "role": cp["role"], "seats": cp["seats"],
                        "note": cp["note"], "departure_time": m["their_time"], "direction": m["direction"],
                        "basis": basis,
                        "office_label": their.get("office_label"), **m,
                        "request": None}
                if r:
                    item["request"] = {"id": r.id, "status": r.status,
                                       "direction": "outgoing" if r.from_email == email else "incoming"}
                    if r.status == "accepted":
                        item["contact"] = _contact(db, u.id)
                app_matches.append(item)
            app_matches.sort(key=lambda x: x["match_score"])
        dataset = []      # simulated colleagues removed: only real registered users are matched
        requests_out = [_serialize_request(db, r, email) for r in reqs]
        regular, regular_source = _user_commute(db, me)
        return {"me": {"profile": _carpool_profile(me), "commute": my_commute, "commute_source": source,
                       "trip_date": trip_date if source == "planned trip" else None,
                       "regular_commute": regular, "regular_source": regular_source},
                "app_matches": app_matches, "dataset_matches": dataset,
                "requests": requests_out,
                "pending_incoming": sum(1 for r in reqs if r.to_email == email and r.status == "pending"),
                "limits": EMP.DEFAULT_MATCH_LIMITS,
                "privacy": "Names are shown masked and contact details stay hidden until a request is accepted."}


@app.get("/api/carpool/requests/count")
def carpool_request_count(request: Request):
    email = require_email(request)
    with SessionLocal() as db:
        n = db.query(CarpoolRequest).filter(CarpoolRequest.to_email == email,
                                            CarpoolRequest.status == "pending").count()
    return {"pending_incoming": n}


@app.post("/api/carpool/requests", status_code=201)
def carpool_request_create(body: CarpoolRequestIn, request: Request):
    email = require_email(request)
    with SessionLocal() as db:
        target = next((a.email for a in db.query(UserAccount).all() if _ref(a.email) == body.to_ref), None)
        if not target or target == email:
            raise HTTPException(404, "Colleague not found.")
        me = _ensure_profile(db, email)
        message = body.message
        if body.trip:
            t = body.trip
            my_commute = {"home_lat": t.olat, "home_lon": t.olon, "office_lat": t.dlat, "office_lon": t.dlon,
                          "departure_time": t.time}
            hit = _best_colleague_match(db, _ensure_profile(db, target), my_commute, t.date)
            summary = f"Trip on {t.date} at {t.time}: {t.olabel or 'start'} -> {t.dlabel or 'destination'}"
            message = summary + (f". {message}" if message else "")
        else:
            my_commute, _ = _user_commute(db, me)
            hit = _best_colleague_match(db, _ensure_profile(db, target), my_commute, None) if my_commute else None
        if not hit:
            raise HTTPException(422, "This colleague's commute is not compatible with this trip.")
        existing = db.query(CarpoolRequest).filter(
            ((CarpoolRequest.from_email == email) & (CarpoolRequest.to_email == target)) |
            ((CarpoolRequest.from_email == target) & (CarpoolRequest.to_email == email)),
            CarpoolRequest.status.in_(("pending", "accepted"))).first()
        if existing:
            raise HTTPException(409, "You already have an open or accepted request with this colleague.")
        r = CarpoolRequest(from_email=email, to_email=target, message=message, status="pending")
        db.add(r)
        db.commit()
        return _serialize_request(db, r, email)


@app.post("/api/carpool/requests/{request_id}/respond")
def carpool_request_respond(request_id: int, body: CarpoolRespond, request: Request):
    email = require_email(request)
    with SessionLocal() as db:
        r = db.get(CarpoolRequest, request_id)
        if not r or r.to_email != email:
            raise HTTPException(404, "Request not found.")
        if r.status != "pending":
            raise HTTPException(409, f"Request is already {r.status}.")
        r.status = "accepted" if body.accept else "declined"
        r.responded_at = _utcnow()
        db.commit()
        return _serialize_request(db, r, email)


@app.post("/api/carpool/requests/{request_id}/cancel")
def carpool_request_cancel(request_id: int, request: Request):
    email = require_email(request)
    with SessionLocal() as db:
        r = db.get(CarpoolRequest, request_id)
        if not r or email not in (r.from_email, r.to_email):
            raise HTTPException(404, "Request not found.")
        if r.status not in ("pending", "accepted"):
            raise HTTPException(409, f"Request is already {r.status}.")
        r.status = "cancelled"
        r.responded_at = _utcnow()
        db.commit()
        return _serialize_request(db, r, email)


@app.exception_handler(Exception)
def _unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})
