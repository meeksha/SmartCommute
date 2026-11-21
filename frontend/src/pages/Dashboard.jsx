import { useEffect, useRef, useState } from "react";
import {
  Car, Users, Train, Bike, Footprints, Bus, TrainFront, MapPin, Clock, Wallet, Leaf, Zap, Activity,
  LocateFixed, ArrowRight, ShieldCheck, X, CloudRain, Sun, Gauge, CheckCircle2, AlertTriangle, Info,
  Building2, Navigation,
} from "lucide-react";
import { api, GOAL_TO_PROFILE, todayIST } from "../lib/api";
import { formatDuration, formatRupees, formatCost, formatCo2, formatKg } from "../lib/format";
import LocationAutocomplete from "../components/LocationAutocomplete";
import BookingLinks from "../components/BookingLinks";
import { CommuteMap, LocationPickerMap } from "../components/Maps";
import { usePersistentState } from "../lib/usePersistentState";

export const transportModes = [
  { id: "driving", short: "Drive", icon: Car },
  { id: "carpool", short: "Carpool", icon: Users },
  { id: "transit", short: "Bus + Metro", icon: Train },
  { id: "twoWheeler", short: "2-wheeler", icon: Bike },
  { id: "bicycling", short: "Cycle", icon: Bike },
  { id: "walking", short: "Walk", icon: Footprints },
];

const commuteGoals = [
  { id: "balanced", label: "Balanced" },
  { id: "cost", label: "Save money" },
  { id: "time", label: "Save time" },
  { id: "eco", label: "Lower emissions" },
];

const FAMILY_ICON = {
  metro: TrainFront, metro_combo: TrainFront, train: Train, bus: Bus, bus_metro: Train, carpool: Users, walk: Footprints, bicycle: Bike,
  auto: Car, cab: Car, two_wheeler: Bike, car: Car,
};

function getSavedMode() {
  const saved = localStorage.getItem("smartcommute-usual-mode");
  return transportModes.some((m) => m.id === saved) ? saved : "driving";
}

function ContextStrip({ context }) {
  if (!context) return null;
  const w = context.weather || {};
  const t = context.traffic || {};
  const m = context.ride_hailing_market || {};
  return (
    <div className="context-strip">
      <span className="context-chip">{w.rain_expected ? <CloudRain size={15}/> : <Sun size={15}/>}
        {w.temperature_c != null ? `${Math.round(w.temperature_c)}°C · ` : ""}{w.condition}
        <small>{w.is_live ? "live" : "climatology"}</small></span>
      <span className="context-chip"><Gauge size={15}/>Traffic {t.level} (×{t.congestion_multiplier})
        <small>{context.live_traffic ? "live TomTom" : "time-of-day model"}</small></span>
      <span className="context-chip"><Car size={15}/>Auto/cab market {m.market_condition} · {Math.round((m.quote_probability || 0) * 100)}% driver quote
        <small>Namma Yatri data</small></span>
      {context.weather_effects?.note && context.weather_effects.note !== "No weather adjustment" &&
        <span className="context-chip context-chip-warn"><Info size={15}/>{context.weather_effects.note}</span>}
    </div>
  );
}

function LegList({ option }) {
  return (
    <ol className="leg-list">
      {option.legs.map((leg, i) => (
        <li key={i} className={`leg leg-${leg.type}`}>
          <span className="leg-dot" style={{ background: leg.color || undefined }}/>
          <div>
            <strong>
              {leg.type === "walk" ? `Walk ${Math.round(leg.distance_m)} m` : leg.label || leg.type}
              {leg.departure_time && <em> · {leg.departure_time} → {leg.arrival_time}</em>}
            </strong>
            <small>
              {leg.from?.name} → {leg.to?.name}
              {leg.stops_count ? ` · ${leg.stops_count} stops` : ""}
              {leg.wait_before_min ? ` · wait ${Math.round(leg.wait_before_min)} min` : ""}
              {leg.direction ? ` · towards ${leg.direction}` : ""}
              {leg.traffic_delay_min ? ` · +${Math.round(leg.traffic_delay_min)} min traffic` : ""}
              {leg.duration_min != null ? ` · ${formatDuration(leg.duration_min)}` : ""}
            </small>
          </div>
        </li>
      ))}
    </ol>
  );
}

function OptionCard({ option, selected, onSelect, onChoose, choosing, chosenId, goTo }) {
  const Icon = FAMILY_ICON[option.family] || Car;
  const em = option.emissions;
  return (
    <article className={`transport-card ${option.rank === 1 ? "transport-card-best" : ""} ${selected ? "transport-card-selected" : ""}`}
      onClick={onSelect} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onSelect()}>
      <div className="transport-card-top">
        <div className="transport-icon"><Icon size={20}/></div>
        <div className="badge-row">{option.badges.map((b) => <span key={b} className={b === "Recommended" ? "best-tag" : "soft-tag"}>{b}</span>)}</div>
      </div>
      <h4>{option.title}</h4>
      {option.chain.length > 1 && <p className="chain">{option.chain.join(" → ")}</p>}
      <div className="transport-metrics">
        <span><Clock size={14}/>{formatDuration(option.duration_min)} · arrive {option.arrive_time}</span>
        <span><Wallet size={14}/>{formatCost(option.cost)}{option.cost.kind === "fuel_operating" ? " fuel" : option.cost.kind === "shared_fuel" ? " each" : ""}</span>
        <span><Leaf size={14}/>{formatCo2(em)} CO₂e / person</span>
        {option.distance_km != null && <span><MapPin size={14}/>{option.distance_km.toFixed(1)} km{option.walking.total_m ? ` · ${option.walking.total_m} m walk` : ""}</span>}
      </div>
      {option.carpool && (option.carpool.real_colleagues ? (
        <div className="carpool-inline">
          <span>With {option.carpool.partners.map((p) => p.name).join(", ")} · {option.carpool.role === "rider" ? "they drive" : "you drive"} · {option.carpool.direction === "return" ? "return trip" : "morning trip"}</span>
          <button type="button" className="link-btn" onClick={(e) => { e.stopPropagation(); goTo?.("Carpooling"); }}>Send a carpool request →</button>
        </div>
      ) : <p className="transport-details">Simulated colleagues from the organisation dataset (matching demo, not contactable).</p>)}
      {option.availability && <p className="transport-details">{Math.round(option.availability.quote_probability * 100)}% chance of a driver · ~{Math.round(option.availability.pickup_wait_min)} min pickup ({option.availability.market} market)</p>}
      <ul className="reason-list">{option.reasons.slice(0, 3).map((r) => <li key={r}>{r}</li>)}</ul>
      <div className="card-footer">
        {option.is_usual_mode && <span className="usual-tag">Your usual mode</span>}
        <span className={`data-tag ${option.is_live ? "live" : ""}`}>{option.is_live ? "Live traffic" : option.family === "metro_combo" ? (option.last_mile === "bus" && option.first_mile !== "auto" ? "Timetable" : "Timetable + auto model") : option.family === "train" ? (option.first_mile === "auto" || option.last_mile === "auto" ? "Rail timetable + auto model" : "Rail timetable") : option.family.includes("bus") || option.family === "metro" ? "Timetable" : "Modelled"} · {em.confidence} confidence</span>
        <button type="button" className="choose-btn" disabled={choosing || chosenId === option.id}
          onClick={(e) => { e.stopPropagation(); onChoose(option); }}>
          {chosenId === option.id ? <><CheckCircle2 size={15}/> Chosen</> : "I'll take this"}
        </button>
      </div>
    </article>
  );
}

// Going + coming back: the pick (or chosen option) for each leg, and the day's totals.
function RoundTripSummary({ out, back, chosenOut, chosenBack, leg, setLeg, outLabel, backLabel, outTime, backTime }) {
  const pick = (res, ch) => res.options.find((o) => o.id === ch?.id) || res.options[0];
  const a = pick(out, chosenOut);
  const b = pick(back, chosenBack);
  if (!a || !b) return null;
  const cost = a.cost.amount_inr != null && b.cost.amount_inr != null ? a.cost.amount_inr + b.cost.amount_inr : null;
  const legs = [
    { id: "out", label: "Going", when: outTime, route: outLabel, o: a, chosen: !!chosenOut },
    { id: "back", label: "Coming back", when: backTime, route: backLabel, o: b, chosen: !!chosenBack },
  ];
  return (
    <div className="panel round-trip">
      <div className="round-trip-tabs" role="tablist">
        {legs.map((l) => (
          <button key={l.id} type="button" role="tab" aria-selected={leg === l.id} className={`round-trip-tab ${leg === l.id ? "active" : ""}`}
            onClick={() => setLeg(l.id)}>
            <span className="rt-label">{l.label} · {l.when}{l.chosen ? " · chosen" : ""}</span>
            <strong>{l.o.title}</strong>
            <small>{l.route}</small>
            <small>{formatDuration(l.o.duration_min)} · {formatCost(l.o.cost)} · {formatKg(l.o.emissions.estimate_kg_co2e)} CO₂e</small>
          </button>
        ))}
        <div className="round-trip-total">
          <span className="rt-label">Whole day</span>
          <strong>{formatDuration(a.duration_min + b.duration_min)}</strong>
          <small>{cost != null ? formatRupees(cost) : "Fare unavailable"} · {formatKg(a.emissions.estimate_kg_co2e + b.emissions.estimate_kg_co2e)} CO₂e</small>
        </div>
      </div>
      <p className="muted">Pick a tab to see and choose options for that direction. Each direction is planned for its own time, with traffic, timetables and carpool matches for that time.</p>
    </div>
  );
}

// Short, skimmable nudge: one cheaper option, what it saves, what it costs in time.
function CheaperPopup({ suggest, onSwitch, onKeep, onClose }) {
  const { option, alt, mode } = suggest;
  const mins = Math.round(alt.extra_min);
  const timeText = mins > 0 ? `${mins} min longer` : mins < 0 ? `${-mins} min faster` : "about the same time";
  const co2 = alt.co2e_change_kg;
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal cheaper-modal" role="dialog" aria-modal="true" aria-labelledby="cheaper-title" onClick={(e) => e.stopPropagation()}>
        <span className="rt-label">Save money</span>
        <h3 id="cheaper-title">{alt.title} saves {formatRupees(alt.saves_inr)} a trip</h3>
        <p className="cheaper-big">About {formatRupees(alt.saves_inr_per_month)} a month</p>
        <ul className="cheaper-facts">
          <li><strong>{option.title}</strong>: {formatCost(option.cost)} · {formatDuration(option.duration_min)}</li>
          <li><strong>{alt.option.title}</strong>: {formatCost(alt.option.cost)} · {formatDuration(alt.option.duration_min)} ({timeText})</li>
          {Math.abs(co2) >= 0.05 && <li>{co2 < 0 ? `${formatKg(-co2)} less CO₂e` : `${formatKg(co2)} more CO₂e`}</li>}
        </ul>
        <div className="modal-actions">
          <button type="button" className="choose-btn" onClick={onSwitch}>{mode === "choose" ? `Take ${alt.option.title} instead` : `Show ${alt.option.title}`}</button>
          <button type="button" className="locate-button" onClick={onKeep}>{mode === "choose" ? `Keep ${option.title}` : "No thanks"}</button>
        </div>
        <small className="muted">A monthly figure assumes two trips a working day.</small>
      </div>
    </div>
  );
}

export default function Dashboard({ user, onTripsChanged, goTo }) {
  const watchIdRef = useRef(null);
  const [offices, setOffices] = useState([]);
  // Trip inputs and the last result persist across page switches and reloads.
  const [origin, setOrigin] = usePersistentState("origin", "");
  const [destination, setDestination] = usePersistentState("destination", "");
  const [originPt, setOriginPt] = usePersistentState("originPt", null);
  const [destinationPt, setDestinationPt] = usePersistentState("destinationPt", null);
  const [{ date, time }, setWhen] = usePersistentState("when", todayIST);
  const [usualMode, setUsualMode] = useState(getSavedMode);
  const [goal, setGoal] = useState(() => localStorage.getItem("smartcommute-goal") || "eco");
  const [loading, setLoading] = useState(false);
  const [reranking, setReranking] = useState(false);
  const [locating, setLocating] = useState(false);
  const [liveLocation, setLiveLocation] = useState(null);
  const [tracking, setTracking] = useState(false);
  const [trackingError, setTrackingError] = useState("");
  const [error, setError] = useState("");
  // Going (out) and coming back (back) each keep their own result, selection and choice.
  const [resultOut, setResultOut] = usePersistentState("result", null);
  const [resultBack, setResultBack] = usePersistentState("resultBack", null);
  const [selOut, setSelOut] = usePersistentState("selectedId", null);
  const [selBack, setSelBack] = usePersistentState("selectedIdBack", null);
  const [choosing, setChoosing] = useState(false);
  // "A cheaper option exists" pop-up: shown once per option per plan, when it is selected or chosen.
  const [suggest, setSuggest] = useState(null);           // { option, alt, mode: "select" | "choose" }
  const [suggestSeen, setSuggestSeen] = useState({});
  const [chosenOut, setChosenOut] = usePersistentState("chosen", null);
  const [chosenBack, setChosenBack] = usePersistentState("chosenBack", null);
  const [roundTrip, setRoundTrip] = usePersistentState("roundTrip", { enabled: false, time: "18:00" });
  const [leg, setLeg] = usePersistentState("leg", "out");
  const isBack = leg === "back" && !!resultBack;
  const result = isBack ? resultBack : resultOut;
  const selectedId = isBack ? selBack : selOut;
  const setSelectedId = isBack ? setSelBack : setSelOut;
  const chosen = isBack ? chosenBack : chosenOut;
  const setResult = (v) => { setResultOut(v); setResultBack(v === null ? null : resultBack); };
  const legFrom = isBack ? destination : origin;
  const legTo = isBack ? origin : destination;
  const [plannedAt, setPlannedAt] = usePersistentState("plannedAt", null);
  const [trips, setTrips] = useState([]);
  const [tripsLoading, setTripsLoading] = useState(true);
  const [tripsError, setTripsError] = useState("");
  const [saveTripHistory, setSaveTripHistory] = useState(true);
  const [pickerTarget, setPickerTarget] = useState(null);
  const [pendingPoint, setPendingPoint] = useState(null);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => () => {
    if (watchIdRef.current !== null) navigator.geolocation?.clearWatch(watchIdRef.current);
  }, []);

  useEffect(() => {
    api("/api/meta").then((m) => setOffices(m.offices)).catch(() => {});
    api("/api/trips?limit=8").then(({ trips: t }) => setTrips(t)).catch((e) => setTripsError(e.message))
      .finally(() => setTripsLoading(false));
  }, []);

  async function plan(nextGoal = goal, nextUsual = usualMode, { rerank = false } = {}) {
    if (!originPt || !destinationPt) {
      setError("Choose a suggestion, use GPS or pin both your starting point and destination on the map.");
      return;
    }
    setError("");
    const withReturn = roundTrip.enabled;
    if (withReturn && roundTrip.time <= time) {
      setError("The return trip must be later in the day than the outbound trip.");
      return;
    }
    rerank ? setReranking(true) : setLoading(true);
    if (!rerank) { setResultOut(null); setResultBack(null); setChosenOut(null); setChosenBack(null); setLeg("out"); }
    const request = (from, fromLabel, to, toLabel, at, accuracy) => api("/api/recommendations", {
      method: "POST",
      body: {
        origin: { lat: from.lat, lon: from.lng, accuracy_m: accuracy ?? undefined, label: fromLabel },
        destination: { lat: to.lat, lon: to.lng, label: toLabel },
        date, time: at,
        profile: GOAL_TO_PROFILE[nextGoal],
        preferences: { usual_mode: nextUsual },
      },
    });
    try {
      // Outbound first (it warms the timetable caches), then the return leg with the ends swapped.
      const r = await request(originPt, origin, destinationPt, destination, time, originPt.accuracy);
      setResultOut(r);
      setSelOut(r.recommended_option_id);
      if (!rerank) setChosenOut(null);
      if (withReturn) {
        const back = await request(destinationPt, destination, originPt, origin, roundTrip.time);
        setResultBack(back);
        setSelBack(back.recommended_option_id);
        if (!rerank) setChosenBack(null);
      } else {
        setResultBack(null);
        setLeg("out");
      }
      setPlannedAt(new Date().toISOString());
      if (r.status !== "success") setError("No commute option passed your constraints. See the details below.");
    } catch (e) {
      setError(e.message || "Unable to plan this commute. Please try again.");
    } finally {
      setLoading(false);
      setReranking(false);
    }
  }

  function handlePlan(event) {
    event.preventDefault();
    plan();
  }

  function cheaperFor(option) {
    const c = option?.cheaper_alternative;
    if (!c || !result) return null;
    const alt = result.options.find((o) => o.id === c.option_id);
    return alt ? { ...c, option: alt } : null;
  }

  function selectOption(option) {
    setSelectedId(option.id);
    const key = `${result?.request_id}:${option.id}`;
    const alt = cheaperFor(option);
    if (alt && !suggestSeen[key]) {
      setSuggestSeen((s) => ({ ...s, [key]: true }));
      setSuggest({ option, alt, mode: "select" });
    }
  }

  async function choose(option, { skipCheck = false } = {}) {
    if (!result) return;
    const key = `${result.request_id}:${option.id}`;
    const alt = cheaperFor(option);
    if (!skipCheck && alt && !suggestSeen[key]) {        // not already shown when it was selected
      setSuggestSeen((s) => ({ ...s, [key]: true }));
      setSuggest({ option, alt, mode: "choose" });
      return;
    }
    setChoosing(true);
    try {
      const r = await api(`/api/recommendations/${result.request_id}/choice`, {
        method: "POST",
        body: { option_id: option.id, save_trip: saveTripHistory, origin_label: legFrom, destination_label: legTo },
      });
      (isBack ? setChosenBack : setChosenOut)({ id: option.id, ...r });
      if (r.saved_trip) {
        setTrips((cur) => [r.saved_trip, ...cur].slice(0, 8));
        setTripsError("");
      }
      onTripsChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setChoosing(false);
    }
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setError("Location access is not available in this browser.");
      return;
    }
    setError("");
    setLocating(true);
    navigator.geolocation.getCurrentPosition(({ coords }) => {
      const point = { lat: coords.latitude, lng: coords.longitude, accuracy: coords.accuracy };
      setOriginPt(point);
      setOrigin(`My current location (${point.lat.toFixed(5)}, ${point.lng.toFixed(5)})`);
      setResult(null);
      setLocating(false);
    }, () => {
      setLocating(false);
      setError("Location permission was denied. Enter your starting location instead.");
    }, { enableHighAccuracy: true, timeout: 10000 });
  }

  function confirmPickedPoint() {
    if (!pickerTarget || !pendingPoint) return;
    const point = { lat: Number(pendingPoint.lat.toFixed(6)), lng: Number(pendingPoint.lng.toFixed(6)) };
    const label = `Pinned location (${point.lat.toFixed(5)}, ${point.lng.toFixed(5)})`;
    if (pickerTarget === "origin") { setOrigin(label); setOriginPt(point); }
    else { setDestination(label); setDestinationPt(point); }
    setResult(null);
    setPickerTarget(null);
    setPendingPoint(null);
  }

  function stopTracking() {
    if (watchIdRef.current !== null) {
      navigator.geolocation?.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
    setTracking(false);
    setLiveLocation(null);
  }

  function toggleTracking() {
    if (tracking) return stopTracking();
    if (!navigator.geolocation) return setTrackingError("Live location is not supported by this browser.");
    setTrackingError("");
    setTracking(true);
    watchIdRef.current = navigator.geolocation.watchPosition(
      ({ coords }) => setLiveLocation({ lat: coords.latitude, lng: coords.longitude, accuracy: coords.accuracy }),
      (err) => {
        const messages = { 1: "Location permission was denied.", 2: "Your location is unavailable.", 3: "Getting your location timed out." };
        setTrackingError(messages[err.code] || "Unable to get your live location.");
        stopTracking();
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 },
    );
  }

  function chooseUsualMode(mode) {
    setUsualMode(mode);
    localStorage.setItem("smartcommute-usual-mode", mode);
    if (result) plan(goal, mode, { rerank: true });
  }

  function chooseGoal(next) {
    setGoal(next);
    localStorage.setItem("smartcommute-goal", next);
    if (result) plan(next, usualMode, { rerank: true });
  }

  // Recalculate when conditions may have changed: departures within the next
  // hour are re-planned every 5 minutes (live traffic, weather, auto supply).
  const departingSoon = (() => {
    const now = todayIST();
    if (!result || date !== now.date) return false;
    const toMin = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
    const diff = toMin(time) - toMin(now.time);
    return diff >= -15 && diff <= 60;
  })();
  useEffect(() => {
    if (!departingSoon) return undefined;
    const id = setInterval(() => plan(goal, usualMode, { rerank: true }), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [departingSoon, goal, usualMode, originPt, destinationPt, date, time]);

  const options = result?.options || [];
  const recommended = options[0];
  const selected = options.find((o) => o.id === selectedId) || recommended;
  const vsDrive = result?.comparisons?.recommended_vs_drive_alone;
  const vsUsual = result?.comparisons?.recommended_vs_usual;
  const RecIcon = recommended ? FAMILY_ICON[recommended.family] || Car : Car;

  return (
    <>
      <div className="welcome planner-welcome">
        <div>
          <span className="eyebrow">YOUR PERSONAL COMMUTE PLANNER</span>
          <h1>Find your <span>better way.</span></h1>
          <p>Real BMTC and Namma Metro timetables, live traffic where available, carpools with colleagues, and per-person CO₂e for every option.</p>
        </div>
        <div className="date-chip"><Leaf size={16}/> Small trips, real impact</div>
      </div>

      <section className="panel planner-panel">
        <div className="panel-heading">
          <div><h3>Where are you headed?</h3><p>Add your trip details for a personalised commute plan.</p></div>
          <MapPin size={20} color="#16865b"/>
        </div>
        <form className="planner-form" onSubmit={handlePlan}>
          <div className="planner-fields">
            <LocationAutocomplete id="commute-origin" label="Starting point" value={origin}
              placeholder="Area, landmark, Metro station or bus stop"
              onChange={(v) => { setOrigin(v); setOriginPt(null); setResult(null); setError(""); }}
              onSelect={(p) => { setOrigin(p.label); setOriginPt({ lat: p.lat, lng: p.lng }); setResult(null); setError(""); }}
              action={<div className="location-field-actions">
                <button type="button" className="locate-button" onClick={useCurrentLocation} disabled={locating}><LocateFixed size={16}/>{locating ? "Locating..." : "Use my location"}</button>
                <button type="button" className="locate-button" onClick={() => { setPickerTarget("origin"); setPendingPoint(originPt); }}><MapPin size={16}/>Pick on map</button>
              </div>}
            />
            <LocationAutocomplete id="commute-destination" label="Destination" value={destination}
              placeholder="Office, neighbourhood or station"
              onChange={(v) => { setDestination(v); setDestinationPt(null); setResult(null); setError(""); }}
              onSelect={(p) => { setDestination(p.label); setDestinationPt({ lat: p.lat, lng: p.lng }); setResult(null); setError(""); }}
              action={<button type="button" className="locate-button" onClick={() => { setPickerTarget("destination"); setPendingPoint(destinationPt); }}><MapPin size={16}/>Pick on map</button>}
            />
          </div>
          {offices.length > 0 && (
            <div className="office-presets">
              <span className="preference-label"><Building2 size={14}/> Office shortcuts</span>
              {offices.map((o) => (
                <button type="button" key={o.id} className={`goal-chip ${destinationPt && Math.abs(destinationPt.lat - o.lat) < 1e-6 ? "selected" : ""}`}
                  onClick={() => { setDestination(o.name); setDestinationPt({ lat: o.lat, lng: o.lon }); setResult(null); }}>{o.name}</button>
              ))}
            </div>
          )}

          <div className="planner-preferences">
            <div className="preference-group">
              <span className="preference-label">Departure</span>
              <div className="when-inputs">
                <input type="date" value={date} onChange={(e) => { setWhen((w) => ({ ...w, date: e.target.value })); setResult(null); }} aria-label="Departure date"/>
                <input type="time" value={time} onChange={(e) => { setWhen((w) => ({ ...w, time: e.target.value })); setResult(null); }} aria-label="Departure time"/>
                <button type="button" className="goal-chip" onClick={() => { setWhen(todayIST()); setResult(null); }}>Now</button>
              </div>
            </div>
            <div className="preference-group">
              <span className="preference-label">Coming back</span>
              <div className="when-inputs">
                <label className="inline-toggle"><input type="checkbox" checked={roundTrip.enabled}
                  onChange={(e) => {
                    const on = e.target.checked;
                    const h = Math.min(23, Number(time.slice(0, 2)) + 9);
                    setRoundTrip((rt) => ({ enabled: on, time: on && rt.time <= time ? `${String(h).padStart(2, "0")}:${time.slice(3, 5)}` : rt.time }));
                    setResult(null);
                  }}/> Plan my return trip too</label>
                {roundTrip.enabled && <input type="time" value={roundTrip.time} aria-label="Return time"
                  onChange={(e) => { setRoundTrip((rt) => ({ ...rt, time: e.target.value })); setResult(null); }}/>}
              </div>
            </div>
            <div className="preference-group">
              <span className="preference-label">Your usual transport</span>
              <div className="mode-chips">
                {transportModes.map(({ id, short, icon: Icon }) => (
                  <button type="button" key={id} className={`mode-chip ${usualMode === id ? "selected" : ""}`} onClick={() => chooseUsualMode(id)}><Icon size={15}/>{short}</button>
                ))}
              </div>
            </div>
            <div className="preference-group goal-group">
              <span className="preference-label">Prioritise</span>
              <div className="mode-chips">
                {commuteGoals.map(({ id, label }) => <button type="button" key={id} className={`goal-chip ${goal === id ? "selected" : ""}`} onClick={() => chooseGoal(id)}>{label}</button>)}
              </div>
            </div>
          </div>
          {error && <div className="planner-error" role="alert">{error}</div>}
          <div className="planner-form-bottom">
            <label className="trip-history-consent"><input type="checkbox" checked={saveTripHistory} onChange={(e) => setSaveTripHistory(e.target.checked)}/><span><ShieldCheck size={14}/> Save trips I choose, including start and destination coordinates, to my account.</span></label>
            <p>Use a suggestion, GPS or a map pin to set exact points. Routes, fares and CO₂e are computed by the SmartCommute engine from BMTC/Metro GTFS, TomTom traffic and Namma Yatri open data.</p>
            <button type="submit" className="plan-button" disabled={loading} aria-busy={loading}>{loading ? "Searching timetables..." : <>Plan my commute <ArrowRight size={17}/></>}</button>
          </div>
        </form>
      </section>

      {loading && <div className="panel loading-panel" role="status"><Activity size={18}/> Planning walk, bus, Metro, carpool and road options from the live timetables… this usually takes 5–10 seconds.</div>}

      {result && recommended && (
        <div className={`planner-results ${reranking ? "is-reranking" : ""}`}>
          {resultBack && resultOut && (
            <RoundTripSummary out={resultOut} back={resultBack} chosenOut={chosenOut} chosenBack={chosenBack}
              leg={leg} setLeg={setLeg} outLabel={`${origin} → ${destination}`} backLabel={`${destination} → ${origin}`}
              outTime={time} backTime={roundTrip.time}/>
          )}
          {suggest && (
            <CheaperPopup suggest={suggest} onClose={() => setSuggest(null)}
              onSwitch={() => {
                const { alt, mode } = suggest;
                setSuggest(null);
                setSelectedId(alt.option.id);
                if (mode === "choose") choose(alt.option, { skipCheck: true });
              }}
              onKeep={() => {
                const { option, mode } = suggest;
                setSuggest(null);
                if (mode === "choose") choose(option, { skipCheck: true });
              }}/>
          )}
          <div className="recommendation-banner">
            <div className="recommendation-icon"><RecIcon size={23}/></div>
            <div className="recommendation-copy">
              <span>PERSONALISED PICK · {result.personalisation.top_priorities.join(" · ")}</span>
              <h2>{recommended.title}</h2>
              <p>{result.summary}</p>
            </div>
          </div>

          <ContextStrip context={result.context}/>

          {result.unavailable.length > 0 && (
            <div className="route-warning" role="status"><AlertTriangle size={15}/> <strong>Not available for this trip:</strong>{" "}
              {result.unavailable.map((u) => `${u.family.replace("_", " + ")}: ${u.reason}`).join(" · ")}</div>
          )}

          <div className="stats-grid planner-stats">
            <div className="stat-card"><div className="stat-top"><span>Travel time</span><div className="stat-icon"><Clock size={19}/></div></div><h2>{formatDuration(recommended.duration_min)}</h2><div className="stat-change"><span>Depart {recommended.depart_time} · arrive {recommended.arrive_time}</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>One-way cost</span><div className="stat-icon"><Wallet size={19}/></div></div><h2>{formatCost(recommended.cost)}</h2><div className="stat-change"><span>{recommended.cost.kind.replaceAll("_", " ")}</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>CO₂e per person</span><div className="stat-icon"><Leaf size={19}/></div></div><h2>{formatKg(recommended.emissions.estimate_kg_co2e)}</h2><div className="stat-change"><span>range {recommended.emissions.lower_kg_co2e.toFixed(2)}–{recommended.emissions.upper_kg_co2e.toFixed(2)} kg</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>CO₂e vs. driving alone</span><div className="stat-icon"><Leaf size={19}/></div></div>
              <h2>{vsDrive ? formatKg(Math.abs(vsDrive.co2e_saved_kg)) : "—"}</h2>
              <div className="stat-change"><span>{!vsDrive ? (result.baseline_drive_alone ? "this is driving alone" : "driving route unavailable") : vsDrive.co2e_saved_kg >= 0 ? "avoided" : "more than driving"}</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Money vs. driving</span><div className="stat-icon"><Wallet size={19}/></div></div>
              <h2>{vsDrive?.money_saved_inr != null ? formatRupees(Math.abs(vsDrive.money_saved_inr)) : "—"}</h2>
              <div className="stat-change"><span>{vsDrive?.money_saved_inr == null ? "not comparable" : vsDrive.money_saved_inr >= 0 ? "saved vs. fuel for driving" : "more than fuel for driving"}</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Time vs. usual mode</span><div className="stat-icon"><Zap size={19}/></div></div>
              <h2>{vsUsual ? formatDuration(Math.abs(vsUsual.time_saved_min)) : "—"}</h2>
              <div className="stat-change"><span>{!vsUsual ? (result.usual_option ? "recommendation is your usual mode" : "usual mode unavailable") : vsUsual.time_saved_min >= 0 ? `faster than ${vsUsual.vs_title}` : `longer than ${vsUsual.vs_title}`}</span></div></div>
          </div>

          {chosen && (
            <div className="choice-feedback" role="status">
              <CheckCircle2 size={18}/>
              <div>
                <strong>Saved your choice: {chosen.chosen.title}.</strong>
                {chosen.co2e_saved_vs_drive_alone_kg != null && <span> {chosen.co2e_saved_vs_drive_alone_kg >= 0 ? `${chosen.co2e_saved_vs_drive_alone_kg.toFixed(2)} kg CO₂e avoided vs. driving alone.` : ""}</span>}
                {chosen.learning && <span> Your profile is learning: you value {chosen.learning.top_priorities.join(", ")}.</span>}
                {chosen.saved_trip && <span> Added to your trip history.</span>}
              </div>
            </div>
          )}

          <section className="panel comparison-panel">
            <div className="panel-heading">
              <div><h3>Compare your options</h3><p>Ranked for “{commuteGoals.find((g) => g.id === goal)?.label}”. Click a card to see it on the map. {reranking && "Re-ranking…"}</p></div>
              <div className="refresh-box">
                <span className="green-tag">{result.stats.candidates_generated} journeys checked · {result.stats.shown} shown</span>
                <button type="button" className="locate-button" disabled={reranking || loading}
                  onClick={() => plan(goal, usualMode, { rerank: true })}>↻ Refresh</button>
                {plannedAt && <small className="muted">Updated {new Date(plannedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}{departingSoon ? " · auto-refresh every 5 min" : ""}</small>}
              </div>
            </div>
            <div className="transport-grid">
              {options.map((o) => (
                <OptionCard key={o.id} option={o} selected={o.id === selected?.id} onSelect={() => selectOption(o)}
                  onChoose={choose} choosing={choosing} chosenId={chosen?.id} goTo={goTo}/>
              ))}
            </div>
          </section>

          <section className="panel route-panel">
            <div className="panel-heading">
              <div><h3>{selected.id === recommended.id ? "Your recommended route" : selected.title}{resultBack ? (isBack ? " · coming back" : " · going") : ""}</h3><p>{legFrom} → {legTo}</p></div>
              <div className="route-map-actions">
                <button type="button" className={`track-location-button ${tracking ? "tracking" : ""}`} onClick={toggleTracking} aria-pressed={tracking}>
                  <Navigation size={15}/>{tracking ? "Stop tracking" : "Track my location"}
                </button>
              </div>
            </div>
            {trackingError && <p className="location-tracking-error" role="alert">{trackingError}</p>}
            {tracking && <p className="location-tracking-status" role="status">{liveLocation ? `Live location on · accuracy ±${Math.round(liveLocation.accuracy)} m` : "Waiting for your location..."}</p>}
            <div className="route-split">
              <CommuteMap key={selected.id} option={selected} origin={isBack ? destinationPt : originPt}
                destination={isBack ? originPt : destinationPt} liveLocation={liveLocation}/>
              <div className="route-steps">
                <h4>Step by step</h4>
                <LegList option={selected}/>
                <BookingLinks option={selected} goTo={goTo}/>
                <details className="method-details">
                  <summary>How this was calculated</summary>
                  <p><strong>CO₂e:</strong> {selected.emissions.methodology.replaceAll("_", " ")} · {selected.emissions.scope}. {selected.emissions.assumptions.join(" · ")}</p>
                  <p><strong>Sources:</strong> {selected.data_sources.join(" · ")}</p>
                  {selected.limitations.length > 0 && <p><strong>Limitations:</strong> {selected.limitations.join(" ")}</p>}
                  <p><strong>Ranking:</strong> {selected.why_ranked} Score {selected.score} (lower is better).</p>
                </details>
              </div>
            </div>
            <p className="map-note">Street lines for road legs are drawn with OSRM for display only; all times, fares and CO₂e come from the SmartCommute engine. Transit times are scheduled (GTFS), not real-time. <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>.</p>
          </section>

          <section className="panel">
            <button type="button" className="details-toggle" onClick={() => setShowDetails((s) => !s)}>{showDetails ? "Hide" : "Show"} filtered-out options and notes ({result.rejected.length})</button>
            {showDetails && (
              <div className="details-body">
                {result.rejected.length === 0 && <p className="muted">No options were removed by your walking or transfer limits.</p>}
                <ul>{result.rejected.slice(0, 15).map((r, i) => <li key={i}><strong>{r.title}</strong> ({formatDuration(r.duration_min)}): {r.reasons.join("; ")}</li>)}</ul>
                <p className="muted">Walking limits for this search: {Math.round(result.personalisation.constraints.max_total_walking_m)} m total (adjusted for weather).</p>
                <ul>{result.notes.map((n) => <li key={n} className="muted">{n}</li>)}</ul>
              </div>
            )}
          </section>
        </div>
      )}

      <section className="panel trip-history-panel">
        <div className="panel-heading">
          <div><h3>Recent saved trips</h3><p>Your route history is private to your account.</p></div>
          <Activity size={19}/>
        </div>
        {tripsLoading && <p className="trip-history-message">Loading your saved trips...</p>}
        {!tripsLoading && tripsError && <p className="trip-history-message trip-history-error" role="alert">{tripsError}</p>}
        {!tripsLoading && !tripsError && trips.length === 0 && <p className="trip-history-message">No saved trips yet. Plan a commute and choose a route to add one.</p>}
        {trips.length > 0 && (
          <div className="trip-history-list">
            {trips.map((t) => (
              <article className="trip-history-item" key={t.id}>
                <div className="trip-history-route"><MapPin size={16}/><span><strong>{t.origin}</strong><small>to {t.destination}</small></span></div>
                <div className="trip-history-details"><strong>{t.mode}</strong>
                  <span>{t.distance_km.toFixed(1)} km · {formatDuration(t.time_minutes)} · {t.co2_kg.toFixed(2)} kg CO₂e{t.co2_saved_vs_drive_kg > 0 ? ` (−${t.co2_saved_vs_drive_kg.toFixed(2)} vs. car)` : ""}</span>
                  <time dateTime={t.created_at}>{new Date(t.created_at).toLocaleString()}</time></div>
              </article>
            ))}
          </div>
        )}
      </section>

      {pickerTarget && (
        <div className="location-picker-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) { setPickerTarget(null); setPendingPoint(null); } }}>
          <section className="location-picker-modal" role="dialog" aria-modal="true" aria-labelledby="location-picker-title">
            <div className="location-picker-heading">
              <div><h3 id="location-picker-title">Pin your {pickerTarget === "origin" ? "starting point" : "destination"}</h3><p>Click the map to place the pin exactly where you want it.</p></div>
              <button type="button" className="location-picker-close" aria-label="Close map picker" onClick={() => { setPickerTarget(null); setPendingPoint(null); }}><X size={19}/></button>
            </div>
            <LocationPickerMap selectedPoint={pendingPoint} onSelect={setPendingPoint}/>
            <div className="location-picker-footer">
              <span>{pendingPoint ? `${pendingPoint.lat.toFixed(5)}, ${pendingPoint.lng.toFixed(5)}` : "No point selected yet"}</span>
              <button type="button" className="plan-button" onClick={confirmPickedPoint} disabled={!pendingPoint}>Use this point</button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
