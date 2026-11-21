import { useEffect, useRef, useState } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import { Activity, Leaf, Car, Clock, Wallet, Users, Bus } from "lucide-react";
import { api } from "../lib/api";
import CompanyBar, { useCompany } from "../components/CompanyBar";

const DEFAULTS = { metro_shift_pct: 0, carpool_pct: 0, shuttle_count: 0, shuttle_capacity: 40,
  ride_hailing_price_change_pct: 0, transit_fare_change_pct: 0, rain: false };

function Delta({ value, unit = "", invert = false, digits = 1 }) {
  if (value == null) return <span>—</span>;
  const good = invert ? value > 0 : value < 0;
  const sign = value > 0 ? "+" : "";
  return <span className={good ? "delta-good" : value === 0 ? "" : "delta-bad"}>{sign}{Number(value).toFixed(digits)}{unit}</span>;
}

function Slider({ label, value, min, max, step = 1, unit = "%", onChange, hint }) {
  return (
    <div className="slider-group">
      <label>{label}: <strong>{value}{unit}</strong></label>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}/>
      {hint && <small className="muted">{hint}</small>}
    </div>
  );
}

// Organisation-level what-if simulator over one office's Census-derived commuter
// population. It uses the same per-trip emission and cost functions as the journey planner.
export default function DigitalTwin() {
  const [scenario, setScenario] = useState(DEFAULTS);
  const [presets, setPresets] = useState([]);
  const [company, setCompany] = useCompany();
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    api("/api/digital-twin/presets").then((p) => setPresets(p.presets)).catch(() => {});
  }, []);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setRunning(true);
      try {
        setResult(await api("/api/digital-twin/simulate", { method: "POST",
          body: { ...scenario, office_zone: company.office, headcount: company.headcount, start_time: company.start_time } }));
        setError("");
      } catch (e) {
        setError(e.message);
      } finally {
        setRunning(false);
      }
    }, 350);
    return () => clearTimeout(timer.current);
  }, [scenario, company]);

  const set = (k) => (v) => setScenario((s) => ({ ...s, [k]: v }));
  const b = result?.baseline;
  const s = result?.scenario_result;
  const c = result?.comparison;
  const shareData = b ? Object.keys({ ...b.mode_share, ...s.mode_share }).map((m) => ({
    mode: m, Baseline: b.mode_share[m]?.count || 0, Scenario: s.mode_share[m]?.count || 0 })) : [];

  return (
    <>
      <div className="panel">
        <div className="panel-heading">
          <div><h3>Commute scenario simulator</h3><p>Simulate policies across {b ? b.employees.toLocaleString("en-IN") : "all"} employees of one office and compare against today's baseline. Where they live and how they travel today come from Census 2011 data, not invented people.</p></div>
          <Activity color="#16865b"/>
        </div>
        <CompanyBar company={company} setCompany={setCompany}/>
        <div className="preset-row">
          {presets.map((p) => (
            <button type="button" key={p.id} className="goal-chip" onClick={() => setScenario({ ...DEFAULTS, ...p.scenario })}>{p.name}</button>
          ))}
          <button type="button" className="goal-chip" onClick={() => setScenario(DEFAULTS)}>Reset</button>
        </div>
        <div className="simulator twin-grid">
          <div className="twin-controls">
            <Slider label="Shift eligible drivers to Metro" value={scenario.metro_shift_pct} min={0} max={100} step={5}
              onChange={set("metro_shift_pct")} hint={result ? `${result.metro.eligible_employees} employees live and work within ${result.metro.catchment_km} km of a station` : ""}/>
            <Slider label="Carpool adoption (of feasible groups)" value={scenario.carpool_pct} min={0} max={100} step={5} onChange={set("carpool_pct")}/>
            <Slider label="Company shuttles" value={scenario.shuttle_count} min={0} max={60} unit="" onChange={set("shuttle_count")}/>
            <Slider label="Ride-hailing price change" value={scenario.ride_hailing_price_change_pct} min={-50} max={100} step={5} onChange={set("ride_hailing_price_change_pct")}/>
            <Slider label="BMTC/Metro fare change" value={scenario.transit_fare_change_pct} min={-100} max={100} step={10} onChange={set("transit_fare_change_pct")}/>
            <div className="setting-row compact"><div><strong>Rainy day</strong><p>Walk/cycle trips shift, roads slow down</p></div>
              <input type="checkbox" checked={scenario.rain} onChange={(e) => set("rain")(e.target.checked)}/></div>
          </div>
          <div className="simulation-result">
            <span>Annual CO₂e change {running && "· updating…"}</span>
            <h1>{c ? <Delta value={c.annual_co2e_tonnes.pct} unit="%"/> : "…"}</h1>
            <p>{c ? `${b.annual.co2e_tonnes} → ${s.annual.co2e_tonnes} t CO₂e / year (${c.annual_co2e_tonnes.abs > 0 ? "+" : ""}${c.annual_co2e_tonnes.abs} t)` : ""}</p>
            {error && <p className="trip-history-error">{error}</p>}
          </div>
        </div>
      </div>

      {result && (
        <>
          <div className="stats-grid">
            <div className="stat-card"><div className="stat-top"><span>Vehicles on the road</span><div className="stat-icon"><Car size={19}/></div></div><h2>{s.vehicles_on_road.toLocaleString("en-IN")}</h2><div className="stat-change"><Delta value={c.vehicles_on_road.abs} digits={0}/>&nbsp;<span>vs. {b.vehicles_on_road} today</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Avg commute (one way)</span><div className="stat-icon"><Clock size={19}/></div></div><h2>{s.avg_commute_min} min</h2><div className="stat-change"><Delta value={c.avg_commute_min.abs} unit=" min"/>&nbsp;<span>vs. {b.avg_commute_min} min</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Daily cost (round trip)</span><div className="stat-icon"><Wallet size={19}/></div></div><h2>₹{Math.round(s.daily_round_trip.total_cost_inr).toLocaleString("en-IN")}</h2><div className="stat-change"><Delta value={c.total_cost_inr_one_way.pct} unit="%"/>&nbsp;<span>commuter + operator</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Daily CO₂e (round trip)</span><div className="stat-icon"><Leaf size={19}/></div></div><h2>{Math.round(s.daily_round_trip.co2e_kg).toLocaleString("en-IN")} kg</h2><div className="stat-change"><Delta value={c.co2e_kg_one_way.pct} unit="%"/>&nbsp;<span>vs. {Math.round(b.daily_round_trip.co2e_kg)} kg</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Carpool</span><div className="stat-icon"><Users size={19}/></div></div><h2>{result.carpool.groups} groups</h2><div className="stat-change"><span>{result.carpool.employees} people · avg {result.carpool.avg_occupancy ?? "—"} per car</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Shuttles</span><div className="stat-icon"><Bus size={19}/></div></div><h2>{result.shuttle.deployed}</h2><div className="stat-change"><span>{result.shuttle.riders} riders · {result.shuttle.utilisation != null ? `${Math.round(result.shuttle.utilisation * 100)}% full` : "—"}</span></div></div>
          </div>
          <div className="panel">
            <div className="panel-heading"><div><h3>Mode split: baseline vs. scenario</h3><p>Employees by main commute mode.</p></div></div>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={shareData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false}/>
                <XAxis dataKey="mode" interval={0} angle={-20} textAnchor="end" height={60}/><YAxis/><Tooltip/><Legend/>
                <Bar dataKey="Baseline" fill="#b8c7d6" radius={[6, 6, 0, 0]}/>
                <Bar dataKey="Scenario" fill="#087f78" radius={[6, 6, 0, 0]}/>
              </BarChart>
            </ResponsiveContainer>
            {result.events.length > 0 && <><h4>What changed</h4><ul>{result.events.map((e) => <li key={e}>{e}</li>)}</ul></>}
            <details className="method-details"><summary>Model assumptions</summary><ul>{result.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></details>
            {result.population && <details className="method-details"><summary>Where the population comes from</summary>
              <p>{result.population.type}: {result.population.headcount.toLocaleString("en-IN")} commuters from {result.population.wards_used} BBMP wards.</p>
              <ul>{result.population.sources.map((x) => <li key={x}>{x}</li>)}{result.population.assumptions.map((x) => <li key={x}>{x}</li>)}</ul></details>}
          </div>
        </>
      )}
    </>
  );
}
