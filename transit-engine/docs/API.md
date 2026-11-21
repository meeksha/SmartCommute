# Sustainable Commute API — contract (v2.0)

Base URL: `http://localhost:8000` · Interactive docs: `/docs` · All bodies are JSON.
**Rule for the frontend:** render the numbers the API returns; never recompute CO2e, cost or time in the UI. That is what keeps the dashboard consistent with the backend.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + warm-up state (`starting` → `warming` → `ready`). Poll until `ready` before the first search (~30 s after start). |
| GET | `/api/meta` | Office presets, ranking profiles, families, fuels, default vehicles, BMTC feed validity. |
| GET | `/api/places/search?q=` | Place search: Nominatim when online, otherwise offices, Metro stations and BMTC stops. |
| GET | `/api/context?lat&lon&date&time` | Weather (+ effects), traffic profile, ride-hailing market at that hour. |
| POST | `/api/recommendations` | **Main call.** Ranked multimodal journeys. |
| POST | `/api/recommendations/{request_id}/choice` | Record the option the user picked; updates their learned weights. |
| POST | `/api/users` · GET/PATCH `/api/users/{id}` | Profiles (preferences, vehicle, learned weights). |
| GET | `/api/users/{id}/history` | Trips chosen and personal CO2e saved vs. driving alone. |
| GET | `/api/employees` · `/api/employees/{id}` | Employee dataset (paged; filter by `office_zone`, `cluster_id`). |
| GET | `/api/clusters` · `/api/clusters/evaluate?k=` | K-Means carpool zones; silhouette/inertia for a chosen k. |
| GET | `/api/carpool/matches?employee_id=` (or origin/dest coords + `time`) | Compatible colleagues. |
| GET | `/api/digital-twin/presets` · `/api/digital-twin/baseline` | Scenario presets; organisation baseline. |
| POST | `/api/digital-twin/simulate` | What-if simulation. |
| GET | `/api/demand?hour=&rain=` | Namma Yatri demand/supply, price pressure, driver earnings (24 h curve if no hour). |
| GET | `/api/emissions/methodology` · POST `/api/emissions/estimate` | Factors and sources; single-trip calculator. |

## POST /api/recommendations

```json
{
  "origin": {"lat": 12.9177, "lon": 77.4838, "accuracy_m": 25},
  "destination": {"lat": 12.975, "lon": 77.605},
  "destination_office_id": "cbd",
  "date": "2026-11-20",
  "time": "08:30",
  "user_id": "optional",
  "profile": "green_first | balanced | fastest | cheapest | comfort",
  "weights": {"emissions": 0.4, "duration": 0.3, "cost": 0.1, "walking": 0.1, "transfers": 0.05, "uncertainty": 0.05},
  "preferences": {"max_walking_minutes": 15, "max_transfers": 2, "avoid_modes": ["cab"], "owns_car": true},
  "vehicle": {"type": "car", "fuel_type": "electric", "efficiency": 0.14}
}
```
Send either `destination` or `destination_office_id`. `date`/`time` default to now (IST); the date must fall inside the BMTC feed (2026-11-09 to 2027-11-09). The origin must be inside Bengaluru. Weight precedence: `weights` > `profile` > the user's learned weights > `preferences.profile` > `green_first`.

### Response (top level)
| Field | Meaning |
|---|---|
| `request_id` | Pass to `/choice` when the user picks an option. |
| `summary` | One-line explanation of the top pick, e.g. *"Bus + Metro: 56 min, Rs 56, ~0.48 kg CO2e/passenger (90% less than driving alone)"*. |
| `recommended_option_id` | = `options[0].id`. |
| `options[]` | Ranked journeys (best first), at most ~10, at most 2 per transit family. |
| `baseline_drive_alone` | `{duration_min, cost_inr, co2e_kg}` reference for "savings" UI. |
| `context` | `weather`, `weather_effects`, `traffic`, `ride_hailing_market`, `live_traffic`. |
| `personalisation` | Active `weights`, `source` (`learned`/`profile:x`/`request`), `top_priorities`, `constraints` (walking limits after the weather adjustment). |
| `carpool_matches[]` | Compatible colleagues (up to 10). |
| `rejected[]` | Options removed by walking/transfer limits, each with `reasons`. |
| `unavailable[]` | Families that could not be planned, with `reason` (e.g. no Metro within walking distance). |
| `stats` | Candidate counts and timing. |

### `options[i]`
| Field | Type | Notes |
|---|---|---|
| `id`, `family`, `title` | str | family ∈ `metro, bus, bus_metro, carpool, walk, auto, cab, two_wheeler, car` |
| `chain` | str[] | e.g. `["Walk","Bus 502-HC","Walk","Purple Line","Walk"]` |
| `duration_min`, `depart_time`, `arrive_time` | num, "HH:MM" | Door-to-door, including waiting time |
| `distance_km` | num | In-vehicle distance |
| `walking` | `{total_m, origin_access_m, destination_egress_m, transfer_walk_m}` | |
| `transfers` | int | |
| `cost` | `{amount_inr, low_inr, high_inr, kind, detail}` | kind ∈ `fare, fuel_operating, ride_hailing_estimate, shared_fuel, free`; `amount_inr` may be `null` (unknown, never shown as free) |
| `emissions` | `{estimate_kg_co2e, lower_kg_co2e, upper_kg_co2e, vehicle_trip_kg_co2e, occupancy, tailpipe_kg_co2e, methodology, scope, confidence, data_source, vehicle_label, assumptions[]}` | **Per passenger.** Show it as a range when `confidence` is `low`. |
| `legs[]` | see below | |
| `badges` | str[] | `Recommended, Fastest, Lowest CO2e, Cheapest` |
| `reasons` | str[] | Human-readable trade-offs vs. driving alone |
| `rank`, `score`, `score_breakdown`, `features`, `predicted_choice_probability`, `pareto_optimal` | | Ranking transparency |
| `availability` | `{quote_probability, pickup_wait_min, market}` | auto/cab only |
| `carpool` | `{role, occupancy, partners[], compatible_colleagues, pickup_detour_km}` | carpool only |
| `is_live`, `data_sources`, `limitations` | | Provenance |

### `legs[j]`
`{type: walk|bus|metro|car|two_wheeler|auto|cab|carpool, from:{name,lat,lon,stop_id?}, to:{...}, duration_min, path:[[lat,lon],...]}`, plus:
- bus/metro: `route`, `label`, `color`, `departure_time`, `arrival_time`, `stops_count`, `wait_before_min`, `direction` (metro), `route_long_name` (bus)
- walk: `distance_m`, `segment` (`origin_access`, `destination_egress`, `bmtc_metro_interchange`, `direct`)
- road: `distance_km`, `traffic_delay_min`; carpool adds `pickups[]`

`path` follows the stop sequence for transit legs. Road legs are straight origin→destination lines, because TomTom summaries carry no geometry.

## POST /api/recommendations/{request_id}/choice
`{"option_id": "...", "user_id": "optional"}` → `{chosen, co2e_saved_vs_drive_alone_kg, learning: {previous_weights, new_weights, prob_of_chosen_before, prob_of_chosen_after, top_priorities}}`.

## POST /api/digital-twin/simulate
```json
{"metro_shift_pct": 20, "carpool_pct": 30, "shuttle_count": 10, "shuttle_capacity": 40,
 "ride_hailing_price_change_pct": 0, "transit_fare_change_pct": 0, "rain": false,
 "office_zone": null, "max_carpool_occupancy": 4, "include_employees": false}
```
Response: `baseline` and `scenario_result`, each with `{employees, one_way{co2e_kg, commuter_cost_inr, operator_cost_inr, total_cost_inr}, daily_round_trip, annual{co2e_tonnes, total_cost_inr_lakh}, vehicles_on_road, avg_commute_min, avg_co2e_per_employee_kg, avg_car_occupancy, mode_share{label:{count,share}}}`. Also returns `comparison` (abs/pct deltas), `carpool{groups, employees, avg_occupancy, seat_utilisation}`, `shuttle{deployed, riders, utilisation, corridors[]}`, `events[]`, `assumptions[]` and `data_quality`.

## Errors
`422` validation (with `detail`), `404` unknown ids, `500` `{detail}`.

## v3 additions (frontend integration)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | `{email, password(>=8), name?}` creates the account and profile, then sets the `smartcommute_session` HttpOnly cookie |
| POST | `/api/auth/login` | `{email, password, remember}` |
| GET | `/api/auth/me` · POST `/api/auth/logout` | Session check / revoke |
| GET | `/api/trips?limit=` | The signed-in user's saved trips |
| GET/PATCH | `/api/users/me`, GET `/api/users/me/history` | `me` means the session user. A profile linked to an account is only accessible through that account's session (403 otherwise). |

- `POST /api/recommendations` uses the session user automatically. `preferences.usual_mode` ∈ `driving, carpool, transit, twoWheeler, bicycling, walking` adds `usual_option` and `comparisons.recommended_vs_usual`. `comparisons.recommended_vs_drive_alone` = `{time_saved_min, co2e_saved_kg, money_saved_inr}`; positive values mean the recommended option saves.
- Changing only the profile, weights or preferences for the same trip reuses the planned candidates for 5 minutes (`cached: true`, about 0.1–0.5 s).
- `POST /api/recommendations/{id}/choice` accepts `{option_id, save_trip, origin_label, destination_label}`. The saved trip stores the engine's own numbers for that option, and the response returns it as `saved_trip`.
- New option family: `bicycle` (straight-line distance up to 8 km, 13 km/h, zero CO₂e).
- `/api/users/{id}/history` → `impact` = `{trips, co2e_saved_kg, money_saved_inr, shared_rides, accepted_recommendation_rate, mode_counts, daily[]}`.

## v4 additions
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/auth/config` | `{google_enabled, google_client_id}` |
| POST | `/api/auth/google` | `{credential}` (Google ID token): verified server-side, then a session cookie is set. Google-only accounts can't use password login. |
| GET/PUT | `/api/carpool/profile` | `{available, role: driver|rider|either, seats, phone, share_phone, note, save_commute_from_last_trip}` |
| GET | `/api/carpool/board` | `me` (profile + regular commute), `app_matches` (registered available colleagues: masked name, role, seats, distances, compatibility, request state, `contact` once accepted), `dataset_matches` (simulated), `requests`, `pending_incoming` |
| POST | `/api/carpool/requests` | `{to_ref, message}` (`to_ref` is an opaque id from the board, never an email) |
| POST | `/api/carpool/requests/{id}/respond` · `/cancel` | `{accept}`: only the recipient can respond. Accepting reveals `contact {name, email, phone?, whatsapp_url?, mailto}` to both sides. |
| GET | `/api/carpool/requests/count` | Pending incoming requests (bell badge) |
