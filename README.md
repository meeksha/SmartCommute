# SmartCommute

Multimodal commute planner for Bengaluru and Tumakuru: real BMTC, Metro and train timetables, cost and CO₂e ranges, carpools between registered colleagues, preference learning, and company tools (Census-based Digital Twin, incentive optimiser, shuttle planner). Built with FastAPI, React and PostgreSQL.

**Quick start for teammates**
1. `git clone https://github.com/meeksha/SmartCommute.git` and `cd SmartCommute`.
2. Download `smartcommute-data.zip` from this repo's **Releases** and extract it into `transit-engine/` (it adds `transit-engine/data/raw` and `data/processed`).
3. `copy .env.example .env`, then fill in the values you were sent privately.
4. `docker compose up -d --build` and open http://localhost:8080.

- **How everything works** (concepts, formulas, models, sources): [`docs/SmartCommute_Technical_Reference.docx`](docs/SmartCommute_Technical_Reference.docx).
- **Sharing and deploying:** [`GIT_AND_DEPLOY.md`](GIT_AND_DEPLOY.md).

---

## Full system

```
<your folder>/
├── docker-compose.yml     PostgreSQL + engine + frontend
├── transit-engine/        FastAPI engine (your existing folder; this zip overlays the code)
│   ├── app/  data/  models/  tests/  docs/API.md
└── frontend/              React + Vite UI (replaces the old frontend + demo backend)
```
Extract this zip **directly into the folder that contains your `transit-engine/` folder** (e.g. `Desktop/major`), replacing files when asked. The code is overlaid; your `data/`, `models/` and `.env` stay as they are. The old `sustainable-commute-recommender/backend` (demo routes) is no longer used: its accounts, sessions and saved trips now live in the engine, on PostgreSQL.

## Option A: run locally (development)
1. **PostgreSQL**: create a database, e.g. `createdb smartcommute`.
2. **Backend** (from `transit-engine/`):
   ```bash
   pip install -r requirements.txt
   # Windows PowerShell:  $env:DATABASE_URL="postgresql+psycopg://postgres:YOURPASS@localhost:5432/smartcommute"
   # macOS/Linux:         export DATABASE_URL=postgresql+psycopg://postgres:YOURPASS@localhost:5432/smartcommute
   uvicorn app.main:app --port 8000
   ```
   Tables are created automatically. The warm-up takes about 30 s; the badge at the top right of the UI shows "Engine ready" when it's done. Needs about 4 GB of RAM.
3. **Frontend** (from `frontend/`):
   ```bash
   npm install
   npm run dev        # http://localhost:5173  (proxies /api to :8000)
   ```

## Option B: Docker
```bash
docker compose up --build      # http://localhost:8080
```
Set `TOMTOM_API_KEY` in your shell or in a `.env` next to `docker-compose.yml` for live traffic. Give Docker at least 6 GB of RAM.

## Tests
```bash
cd transit-engine
DATABASE_URL=postgresql+psycopg://postgres:YOURPASS@localhost:5432/smartcommute_test python -m pytest -q tests
```
30 end-to-end tests: API contract, accounts and sessions, the learning loop, saved trips, carpool matching (including trip-specific matching), Tumakuru trains and intercity buses, the Census population, the shuttle planner, the incentive optimiser, the Digital Twin, and consistency between the emissions model and the Twin.

## What each screen uses
| Screen | Backend |
|---|---|
| Sign in / register | `/api/auth/*`: email + password (PBKDF2) or Google; HttpOnly session cookie, PostgreSQL |
| Dashboard | `/api/places/search`, `/api/recommendations`, `/api/recommendations/{id}/choice`, `/api/trips` |
| Carpooling | `/api/carpool/board`, `/api/carpool/profile`, `/api/carpool/requests` (real colleagues, contact after acceptance) |
| Recommendations (insights) | `/api/users/me`, `/api/users/me/history` (learned weights) |
| Savings | `/api/users/me/history` (CO₂e and money saved vs. driving alone) |
| Digital Twin | `/api/digital-twin/presets`, `/api/digital-twin/simulate` |
| Incentives | `/api/incentives/optimise` (budget → CO₂e abatement cost curve) |
| Shuttles | `/api/shuttles/plan` (underserved wards → OR-Tools routes over real BMTC stops) |
| Analytics | `/api/clusters`, `/api/demand`, `/api/digital-twin/simulate`, `/api/population` |
| Settings | `PATCH /api/users/me` (preferences, employee ID, vehicle, reset learning) |

The UI never computes CO₂e, cost or time itself. It displays the engine's numbers, and a saved trip stores the engine's numbers, not values sent by the browser. The browser calls OSRM only to draw street lines for road legs on the map.


## Google sign-in setup (one-time, about 5 minutes)
1. Go to https://console.cloud.google.com, then create or select a project.
2. **APIs & Services → OAuth consent screen**: choose External, fill in the app name and your email, and add yourself (and your team) as **Test users**.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**: choose application type **Web application**.
   - **Authorized JavaScript origins**: `http://localhost`, `http://localhost:8080`, `http://localhost:5173`
   - No redirect URI is needed (the button uses a popup).
4. Copy the **Client ID** (ends with `.apps.googleusercontent.com`) into the `.env` next to `docker-compose.yml`:
   ```
   GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
   ```
   For a local (non-Docker) run, set it as an environment variable before `uvicorn`.
5. Restart the backend. The login page loads the real Google button. The backend verifies Google's signed ID token (signature, audience, expiry, verified email) and creates or links the account.

## Carpooling between real colleagues
- Each user sets **Carpooling → Your carpool profile**: Available, drive or ride, seats, an optional phone number (shared only if they tick it), and a note.
- The regular commute comes from the linked employee ID, else a saved commute, else the last saved trip.
- **Find colleagues for:** your trip planned on the Dashboard (matched at its date and time against what each colleague is doing then: their saved trip that day, else their regular morning commute or estimated evening return) or your regular commute.
- Colleagues with compatible trips appear under **Available colleagues on SmartCommute** (same matching rules: home within 2.5 km, office within 2 km, departure within ±30 min).
- **Request to carpool** → the colleague sees a badge on the bell and in the sidebar → **Accept** reveals both people's email, plus the phone and WhatsApp link if shared.
- Only real registered users are matched. The old simulated colleagues are gone.

## Machine learning & MLOps (ride-hailing demand/supply)
Adapted from the pattern in [scariadon5/Namma-Yatri-Pricing-MLOPS-](https://github.com/scariadon5/Namma-Yatri-Pricing-MLOPS-) (MIT): train → track in MLflow → versioned artifact → served by FastAPI.
- **Data:** Namma Yatri ward × hour trends (244 wards, 3 days, 16,592 rows) + ward driver availability.
- **Models:** four gradient-boosted regressors: demand, driver-quote rate, booking completion, fare per ride. Trained on two days and tested on the third (unseen) day. A model is served only if it beats the hour-of-day baseline.
- **Use:** auto/cab availability ("chance the ride happens"), the price-pressure input (prediction + bounded pricing rule) and driver-side earnings. Results are shown on the Analytics page.
- **Retrain and browse runs** (from `transit-engine/`):
  ```bash
  pip install -r requirements-ml.txt          # MLflow (training only; the server doesn't need it)
  python -m app.ml.train_ride_hailing         # trains, logs to mlflow.db, writes models/ride_hailing/
  python -m app.ml.validate_fares             # checks the auto-fare model against observed ward averages
  mlflow ui --backend-store-uri sqlite:///mlflow.db    # http://127.0.0.1:5000
  ```
  If `models/ride_hailing/model.joblib` is missing, or was made with another scikit-learn version, the backend retrains it automatically at startup (~10–20 s, without MLflow).

## Real data only (v5)
Nothing in the app is an invented person or a made-up number without a source. Every dataset and assumption is listed here and shown in the UI.

**Coverage: Bengaluru + Tumakuru.**
- **Trains:** 40 daily Bengaluru–Tumakuru trains (MEMU, passenger and express). Times come from published timetables (etrain.info, erail.in), and station coordinates have a stated source for each. See `transit-engine/data/external/rail/README.md`.
- **Buses:** the BMTC Vajra Vistara buses Majestic/Electronic City ⇄ Tumakuru come from the BMTC GTFS feed, which already contained them.
- **Fares:** BMTC fares follow the Nov 2026 revision (the GTFS feed is dated 9 Nov 2026). A train fare is ₹20 unreserved SBC→TK.
- **Trips inside Tumakuru:** walk, auto, car, two-wheeler and cab. There is no public timetable for Tumakuru city buses, so none is invented.
- **Limits:** auto-rickshaws aren't offered for intercity trips over 35 km. Roads outside Bengaluru use free-flow speeds. On your machine, road distance and time come from OpenStreetMap (OSRM); if it's unreachable, a stated fallback model is used.

**Commuter population** (Digital Twin, Analytics, Incentives, Shuttles):
- Built from Census 2011 data: 198 BBMP ward populations, plus Table B-28 (distance to work × mode).
- People are allocated deterministically for the office, headcount and start time you choose. No random sampling and no fake names.
- See `transit-engine/data/external/census/README.md`.

**Costs, values and elasticities:**
- Shuttle cost: ₹62/km, the KSRTC ordinary bus hire rate (Nov 2026).
- Value of time: ₹179.2/h (IIT Bombay study).
- Transit fare elasticity: −0.22, from the Namma Metro fare hike of Feb 2025.

**New pages:**
- **Incentives:** how to spend a monthly budget to cut the most CO₂e.
- **Shuttles:** routes for areas that Metro and BMTC don't connect to the office.

`ortools` is now in `requirements.txt`; the Docker build installs it.

## Roles: employee vs company admin (v5.1)
- **Everyone is an employee by default.** Employees see their own commute pages: Dashboard, Carpooling, Recommendations, Savings and Settings.
- **Company admins** also see the company-wide pages: Digital Twin, Incentives, Shuttles, Analytics and Team. The server enforces this; an employee calling those APIs gets "403".
- **Making the first admin** (the account must already exist; the person just reloads the page):
  ```bash
  docker compose exec backend python -m app.tools.set_role friend@example.com admin
  ```
  Or add `ADMIN_EMAILS=friend@example.com` to the `.env` beside `docker-compose.yml` and run `docker compose up -d`. After that, an admin can make others admins on the **Team** page.

## Going and coming back (v5.1)
On the Dashboard, tick **Plan my return trip too** and set the time. Each direction is planned for its own time, with its own traffic, timetables and carpool matches. Evening trips are matched with colleagues' trips home. Tabs switch between **Going** and **Coming back**, and a third box shows the whole day's time, cost and CO₂e. Choose an option in each tab to save both trips. On Carpooling you can also find colleagues for **My return trip**.

## Certificate errors ("CERTIFICATE_VERIFY_FAILED ... self-signed certificate")
Your network or antivirus inspects HTTPS (college/office firewalls, Kaspersky, Avast, ESET, Zscaler, FortiGate...). It re-signs every site with its own root certificate. Windows trusts that certificate, but the backend container doesn't, so Google sign-in, TomTom traffic and live weather fail.
1. **Quick check:** connect the laptop to a phone hotspot and try again. If it works, the network was the cause.
2. **Permanent fix:** export the inspecting root certificate as Base-64 into `certs/`, then run `docker compose up -d --build`. Certificates are still fully verified; the backend just also trusts that one root.
