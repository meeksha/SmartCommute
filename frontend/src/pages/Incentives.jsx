import { useEffect, useMemo, useRef, useState } from "react";
import { ResponsiveContainer, ComposedChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from "recharts";
import { BadgeIndianRupee, Leaf, Users, Target, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import CompanyBar, { useCompany } from "../components/CompanyBar";
import { usePersistentState } from "../lib/usePersistentState";

const KINDS = [
  { id: "metro_pass", label: "Metro pass subsidy" },
  { id: "bus_pass", label: "BMTC bus pass subsidy" },
  { id: "carpool_credit", label: "Carpool credit" },
  { id: "shuttle_seat", label: "Company shuttle seats" },
];
const KIND_COLOR = { metro_pass: "#8257bd", bus_pass: "#d9480f", carpool_credit: "#2b8a3e", shuttle_seat: "#126f99" };
const DEFAULTS = { budget: 200000, vot: 179.2, take_up: 100, shuttle_vehicles: 10,
  enabled: ["metro_pass", "bus_pass", "carpool_credit", "shuttle_seat"] };

const inr = (v) => `₹${Math.round(v).toLocaleString("en-IN")}`;
const lakh = (v) => (v >= 1e5 ? `₹${(v / 1e5).toFixed(1)} lakh` : inr(v));

// "Where should we spend ₹X a month to cut the most CO2e?" A marginal abatement
// cost curve for one office's commuting, computed by the backend.
export default function Incentives() {
  const [company, setCompany] = useCompany();
  const [form, setForm] = usePersistentState("incentives", DEFAULTS);
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setBusy(true);
      try {
        const q = new URLSearchParams({ office: company.office, headcount: company.headcount, start_time: company.start_time,
          monthly_budget_inr: form.budget, value_of_time: form.vot, take_up_pct: form.take_up,
          shuttle_vehicles: form.shuttle_vehicles, enabled: form.enabled.join(",") });
        setRes(await api(`/api/incentives/optimise?${q}`));
        setError("");
      } catch (e) { setError(e.message); } finally { setBusy(false); }
    }, 400);
    return () => clearTimeout(timer.current);
  }, [company, form]);

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const toggle = (id) => setForm((f) => ({ ...f, enabled: f.enabled.includes(id) ? f.enabled.filter((x) => x !== id) : [...f.enabled, id] }));

  // Step-shaped MAC curve: x = cumulative tonnes, y = ₹ per tonne; budget line where funding stops.
  const curve = useMemo(() => {
    if (!res) return [];
    let prev = 0;
    const pts = [];
    res.curve.forEach((p) => {
      const y = Math.min(p.inr_per_tonne, 150000);
      pts.push({ t: prev, funded: p.funded ? y : null, unfunded: p.funded ? null : y });
      pts.push({ t: p.cum_tonnes, funded: p.funded ? y : null, unfunded: p.funded ? null : y });
      prev = p.cum_tonnes;
    });
    return pts;
  }, [res]);
  const r = res?.result;
  const lastFunded = res ? [...res.curve].reverse().find((p) => p.funded) : null;

  return (
    <>
      <div className="panel">
        <div className="panel-heading">
          <div><h3>Where should the company spend its commute budget?</h3>
            <p>Each greener option is priced as the smallest incentive per trip that makes it at least as good as the person's current mode in money plus time. The cheapest tonnes of CO₂e are funded first, up to your budget.</p></div>
          {busy ? <Loader2 className="spin" color="#16865b"/> : <Target color="#16865b"/>}
        </div>
        <CompanyBar company={company} setCompany={setCompany}/>
        <div className="twin-grid">
          <div className="twin-controls">
            <div className="slider-group">
              <label>Monthly budget: <strong>{inr(form.budget)}</strong></label>
              <input type="range" min={0} max={1000000} step={10000} value={form.budget} onChange={(e) => set("budget")(Number(e.target.value))}/>
            </div>
            <div className="slider-group">
              <label>Value of time: <strong>₹{form.vot}/hour</strong></label>
              <input type="range" min={0} max={600} step={0.1} value={form.vot} onChange={(e) => set("vot")(Number(e.target.value))}/>
              <small className="muted">Default ₹179.2/h: IIT Bombay study of Mumbai commuters (Hindustan Times, 2018).</small>
            </div>
            <div className="slider-group">
              <label>Expected take-up: <strong>{form.take_up}%</strong></label>
              <input type="range" min={10} max={100} step={5} value={form.take_up} onChange={(e) => set("take_up")(Number(e.target.value))}/>
              <small className="muted">100% = everyone offered a break-even incentive switches (upper bound).</small>
            </div>
            <div className="slider-group">
              <label>Shuttle fleet: <strong>{form.shuttle_vehicles} buses</strong></label>
              <input type="range" min={1} max={30} step={1} value={form.shuttle_vehicles} onChange={(e) => set("shuttle_vehicles")(Number(e.target.value))}/>
            </div>
            <div className="kind-toggles">
              {KINDS.map((k) => (
                <label key={k.id} className="inline-toggle"><input type="checkbox" checked={form.enabled.includes(k.id)} onChange={() => toggle(k.id)}/>
                  <i className="kind-dot" style={{ background: KIND_COLOR[k.id] }}/>{k.label}</label>
              ))}
            </div>
          </div>
          <div className="simulation-result">
            <span>CO₂e avoided per year</span>
            <h1>{r ? `${r.annual_co2e_saved_tonnes} t` : "…"}</h1>
            <p>{r ? `${r.people_switched} people switch · ${lakh(r.annual_spend_inr)} a year (${inr(r.monthly_spend_inr)}/month)` : ""}</p>
            {r?.avg_inr_per_tonne && <p>Average {inr(r.avg_inr_per_tonne)} per tonne</p>}
            {error && <p className="trip-history-error">{error}</p>}
          </div>
        </div>
      </div>

      {res && (
        <>
          <div className="stats-grid">
            <div className="stat-card"><div className="stat-top"><span>Commuters who drive or ride</span><div className="stat-icon"><Users size={19}/></div></div>
              <h2>{res.potential.road_commuters}</h2><div className="stat-change"><span>of {res.inputs.headcount} at {res.office}</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Could be moved with money</span><div className="stat-icon"><BadgeIndianRupee size={19}/></div></div>
              <h2>{res.potential.people_with_a_feasible_incentive}</h2><div className="stat-change"><span>all of them: {inr(res.potential.budget_for_all_inr_per_month)}/month for {res.potential.max_annual_co2e_tonnes} t</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Organisation CO₂e (Twin check)</span><div className="stat-icon"><Leaf size={19}/></div></div>
              <h2>{res.twin_check.annual_after_tonnes} t</h2><div className="stat-change"><span className="delta-good">−{res.twin_check.reduction_pct}%</span>&nbsp;<span>from {res.twin_check.annual_baseline_tonnes} t / year</span></div></div>
          </div>

          <div className="panel">
            <div className="panel-heading"><div><h3>Abatement cost curve</h3>
              <p>Each step is one person's cheapest incentive, ordered from lowest to highest cost per tonne. Green steps fit in the budget; grey ones don't.</p></div></div>
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={curve} margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false}/>
                <XAxis dataKey="t" type="number" unit=" t" domain={[0, "dataMax"]} tickFormatter={(v) => Math.round(v)}/>
                <YAxis tickFormatter={(v) => `₹${Math.round(v / 1000)}k`}/>
                <Tooltip formatter={(v) => (v == null ? null : `${inr(v)} / t`)} labelFormatter={(v) => `${Number(v).toFixed(1)} t CO₂e / year`}/>
                <Area type="stepAfter" dataKey="funded" name="Funded" stroke="#087f78" fill="#b8e3d4" connectNulls={false} isAnimationActive={false}/>
                <Area type="stepAfter" dataKey="unfunded" name="Over budget" stroke="#9aa5ad" fill="#e3e8eb" connectNulls={false} isAnimationActive={false}/>
                {lastFunded && <ReferenceLine x={lastFunded.cum_tonnes} stroke="#e4775d" strokeDasharray="4 4" label={{ value: "budget", position: "top", fill: "#e4775d" }}/>}
              </ComposedChart>
            </ResponsiveContainer>
            <p className="muted">Steps above ₹1.5 lakh/t are drawn at the top of the chart.</p>
          </div>

          <div className="panel">
            <div className="panel-heading"><div><h3>What the budget buys</h3></div></div>
            <div className="table-wrap"><table>
              <thead><tr><th>Incentive</th><th>People</th><th>Avg per trip</th><th>Time change</th><th>Cost / year</th><th>CO₂e / year</th><th>₹ per tonne</th></tr></thead>
              <tbody>{res.by_incentive.map((k) => (
                <tr key={k.incentive}><td>{k.incentive}</td><td>{k.people}</td><td>{inr(k.avg_per_trip_inr)}</td>
                  <td>{k.avg_minutes_change > 0 ? "+" : ""}{k.avg_minutes_change} min</td><td>{lakh(k.annual_cost_inr)}</td>
                  <td>{k.annual_co2e_tonnes} t</td><td>{k.inr_per_tonne ? inr(k.inr_per_tonne) : "—"}</td></tr>))}
                {!res.by_incentive.length && <tr><td colSpan={7}>Nothing fits in this budget. Try a higher budget or more incentive types.</td></tr>}</tbody>
            </table></div>
            <div className="callout">
              <strong>{res.potential.nudge_pool} people</strong> already have a greener option that is as good in money and time, yet the Census shows people in their situation still drive. Money isn't what holds them back (information, reliability or comfort might be), so they aren't counted above.
              {" "}<strong>{res.potential.money_alone_not_enough}</strong> more would need more than a free pass to make up the extra travel time.
            </div>
            <details className="method-details"><summary>How this is calculated</summary><ul>{res.method.map((m) => <li key={m}>{m}</li>)}</ul></details>
          </div>
        </>
      )}
    </>
  );
}
