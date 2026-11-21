import { useEffect, useRef, useState } from "react";
import { Bus, Leaf, MapPin, Wallet, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { RoutesMap } from "../components/Maps";
import CompanyBar, { useCompany } from "../components/CompanyBar";
import { usePersistentState } from "../lib/usePersistentState";

const COLORS = ["#087f78", "#126f99", "#e4775d", "#8257bd", "#c99700", "#2b8a3e", "#d9480f", "#0b7285",
  "#5c7cfa", "#a61e4d", "#495057", "#74b816", "#f76707", "#1098ad", "#862e9c"];
const DEFAULTS = { capacity: 40, max_vehicles: 10, max_ride_min: 75 };
const inr = (v) => `₹${Math.round(v).toLocaleString("en-IN")}`;

// Company shuttle routes for the parts of the city where Metro and BMTC don't
// serve the office: OR-Tools vehicle routing over real BMTC stops.
export default function Shuttles() {
  const [company, setCompany] = useCompany();
  const [form, setForm] = usePersistentState("shuttles", DEFAULTS);
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showGaps, setShowGaps] = useState(true);
  const timer = useRef(null);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setBusy(true);
      try {
        const q = new URLSearchParams({ office: company.office, headcount: company.headcount, start_time: company.start_time,
          capacity: form.capacity, max_vehicles: form.max_vehicles, max_ride_min: form.max_ride_min });
        setRes(await api(`/api/shuttles/plan?${q}`));
        setError("");
      } catch (e) { setError(e.message); } finally { setBusy(false); }
    }, 400);
    return () => clearTimeout(timer.current);
  }, [company, form]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: Number(e.target.value) }));
  const s = res?.summary;
  const routes = (res?.routes || []).map((r, i) => ({
    key: r.vehicle, color: COLORS[i % COLORS.length],
    positions: [...r.stops.map((x) => [x.lat, x.lon]), [res.office_point.lat, res.office_point.lon]],
    label: `Shuttle ${r.vehicle}: ${r.riders} riders · ${r.route_km} km · first pick-up ${r.first_pickup}`,
  }));
  const points = res ? [
    { key: "office", lat: res.office_point.lat, lon: res.office_point.lon, color: "#e4775d", radius: 10, label: res.office },
    ...res.routes.flatMap((r, i) => r.stops.map((x, j) => ({ key: `${r.vehicle}-${j}`, lat: x.lat, lon: x.lon,
      color: COLORS[i % COLORS.length], radius: 5 + Math.sqrt(x.boardings),
      label: `${x.stop} · ${x.boardings} board at ${x.pickup_time} · ${x.ride_to_office_min} min to office` }))),
    ...(showGaps ? res.service_gaps.wards.filter((w) => w.underserved && w.road_commuters > 0).map((w) => ({
      key: `w${w.ward_no}`, lat: w.lat, lon: w.lon, color: "#adb5bd", radius: 3,
      label: `${w.ward}: no Metro or direct BMTC route to the office · ${w.road_commuters} drive/ride` })) : []),
  ] : [];

  return (
    <>
      <div className="panel">
        <div className="panel-heading">
          <div><h3>Shuttle route planner</h3>
            <p>Finds home areas where neither the Metro nor a direct BMTC route reaches the office, then plans shuttle routes that pick people up at real BMTC stops, within the seat and ride-time limits you set.</p></div>
          {busy ? <Loader2 className="spin" color="#16865b"/> : <Bus color="#16865b"/>}
        </div>
        <CompanyBar company={company} setCompany={setCompany}/>
        <div className="vehicle-row">
          <label>Seats per bus<input type="number" min={8} max={60} value={form.capacity} onChange={set("capacity")}/></label>
          <label>Buses available<input type="number" min={1} max={40} value={form.max_vehicles} onChange={set("max_vehicles")}/></label>
          <label>Longest ride (min)<input type="number" min={20} max={150} step={5} value={form.max_ride_min} onChange={set("max_ride_min")}/></label>
        </div>
        {error && <p className="trip-history-error">{error}</p>}
      </div>

      {res && (
        <>
          <div className="stats-grid">
            <div className="stat-card"><div className="stat-top"><span>Underserved home wards</span><div className="stat-icon"><MapPin size={19}/></div></div>
              <h2>{res.service_gaps.wards_underserved} / {res.service_gaps.wards_total}</h2><div className="stat-change"><span>{res.service_gaps.road_commuters_in_underserved_wards} people there drive or ride</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Riders on shuttles</span><div className="stat-icon"><Bus size={19}/></div></div>
              <h2>{s.riders}</h2><div className="stat-change"><span>{s.vehicles} buses · {s.unserved_target_riders} target riders not reached</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Cost</span><div className="stat-icon"><Wallet size={19}/></div></div>
              <h2>{inr(s.cost_per_rider_trip_inr)}</h2><div className="stat-change"><span>per rider trip · {(s.annual_cost_inr / 1e5).toFixed(1)} lakh/year</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>CO₂e avoided</span><div className="stat-icon"><Leaf size={19}/></div></div>
              <h2>{s.annual_co2e_saved_tonnes} t</h2><div className="stat-change"><span>per year · {s.cost_per_tonne_inr ? `${inr(s.cost_per_tonne_inr)}/t` : "—"}</span></div></div>
          </div>

          <div className="panel">
            <div className="panel-heading"><div><h3>Routes</h3><p>Lines run from the first pick-up to the office (straight segments between stops). Grey dots: underserved wards.</p></div>
              <label className="inline-toggle"><input type="checkbox" checked={showGaps} onChange={(e) => setShowGaps(e.target.checked)}/> Show underserved wards</label></div>
            <RoutesMap routes={routes} points={points}/>
            <div className="table-wrap"><table>
              <thead><tr><th>Bus</th><th>Pick-ups (time · boarding)</th><th>Riders</th><th>Seats used</th><th>Route km</th><th>Longest ride</th></tr></thead>
              <tbody>{res.routes.map((r, i) => (
                <tr key={r.vehicle}><td><i className="kind-dot" style={{ background: COLORS[i % COLORS.length] }}/> {r.vehicle}</td>
                  <td>{r.stops.map((x) => `${x.pickup_time} ${x.stop} (${x.boardings})`).join(" → ")}</td>
                  <td>{r.riders}</td><td>{Math.round(r.load_factor * 100)}%</td><td>{r.route_km}</td><td>{r.max_ride_min} min</td></tr>))}
                {!res.routes.length && <tr><td colSpan={6}>No shuttle needed: every home ward with drivers has Metro or a direct BMTC route.</td></tr>}</tbody>
            </table></div>
          </div>

          <div className="panel">
            <div className="panel-heading"><div><h3>Public-transport gaps by home ward</h3><p>Wards with the most people who drive or ride, and whether Metro or a direct BMTC route serves this office.</p></div></div>
            <div className="table-wrap"><table>
              <thead><tr><th>Ward</th><th>Commuters</th><th>Drive / ride</th><th>Metro</th><th>Direct BMTC routes</th><th>Status</th></tr></thead>
              <tbody>{res.service_gaps.wards.slice(0, 25).map((w) => (
                <tr key={w.ward_no}><td>{w.ward}</td><td>{w.commuters}</td><td>{w.road_commuters}</td><td>{w.metro_serves ? "Yes" : "No"}</td>
                  <td>{w.direct_bus_routes ? `${w.direct_bus_routes} (${w.example_routes.join(", ")})` : "None"}</td>
                  <td>{w.underserved ? <span className="soft-tag warn-tag">Underserved</span> : "Served"}</td></tr>))}</tbody>
            </table></div>
            <details className="method-details"><summary>How this is calculated</summary><ul>{res.method.map((m) => <li key={m}>{m}</li>)}</ul></details>
          </div>
        </>
      )}
    </>
  );
}
