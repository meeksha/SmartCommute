# Transit engine — backend (v2)

## Run
```bash
# from the transit-engine folder (the one containing app/ and data/)
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000/docs ; wait for /api/health -> warmup.state == "ready" (~30 s)
python -m pytest -q tests          # 15 end-to-end tests (~1 min)
```
Optional environment variables:
- `TOMTOM_API_KEY` (or `.env`): live traffic for departures within the next 90 minutes. Otherwise a time-of-day model is used.
- `DATABASE_URL`: default is `sqlite:///data/app.sqlite3`. For PostgreSQL use e.g. `postgresql+psycopg://user:pw@localhost/commute` (`pip install psycopg[binary]`).
- `CORS_ORIGINS`: comma-separated frontend origins (default `*`).
- `SKIP_WARMUP=1`: lazy loading (tests).

On first run the backend builds two small cache files: `data/processed/bmtc_latest/bmtc_shape_dist_index.pkl` and `bmtc_fare_curve.json`.

## What changed vs. the prototype
| Area | Before | Now |
|---|---|---|
| API | `app/main.py` empty | FastAPI with 20 endpoints (`docs/API.md`) |
| Speed | ~104 s per request; walking graph reloaded every call | ~30 s one-off warm-up at startup, then 5-9 s per request (5-min result cache) |
| Output | 53 near-duplicate options | Deduplicated, at most 2 per transit family; badges, reasons, Pareto flag, explanation |
| Road modes | Failed without TomTom | TomTom live, or a labelled time-of-day/circuity fallback |
| Emissions | One factor per mode | Vehicle/fuel/EV-aware, occupancy-split, congestion penalty, range + confidence + methodology |
| Ranking | Fixed weights | 5 profiles + per-user weights learned online (conditional-logit) from chosen trips |
| Carpool | Not in recommendations | Employee-aware matching gives a real carpool option with split cost and CO2e |
| Context | None | Weather (Open-Meteo / climatology) changes walking limits, road time and ride-hailing demand |
| Pricing | Static fares | Namma Yatri demand/supply gives availability, wait, price pressure and driver earnings by hour |
| Digital Twin | Carpool only, pairs | Metro shift, carpools up to 4, shuttles, ride-hailing and transit price elasticity, rain; same emission/cost functions as the recommender |
| Dataset | Modes independent of distance (e.g. 1,419 "walkers" averaging 14.5 km) | Twin baseline re-sampled from Census B-28 mode × distance |

## Code map
- `app/main.py`: API. `app/schemas.py`: request validation. `app/database.py`: users, choices, logs.
- `app/services/recommender.py`: candidate generation → filtering → ranking → explanation.
- `app/services/emissions.py`, `costs.py`: the single source of CO2e and cost numbers.
- `app/services/context.py` (weather, traffic, road fallback), `demand_pricing.py` (Namma Yatri), `employees.py` (clusters, carpool), `places.py` (search, geometry), `preferences.py` (ranking and learning), `digital_twin.py`.
- Performance patches in `app/routing/`: `planner.py` (cached graph, bounded Dijkstra), `metro_planner.py` (time-window scan), `bmtc_connection_scan.py` (list fast path, 3 h horizon), `bmtc_metro_planner.py` / `bmtc_latest_planner.py` (shared cached timetable, stop sequences on legs), and `app/services/carbon.py` (shape-distance index). I checked the outputs against the original code: same best journeys.
