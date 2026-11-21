import { useEffect, useState } from "react";
import { ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, BarChart } from "recharts";
import { MapPin, Users, Leaf, Clock } from "lucide-react";
import { api } from "../lib/api";
import { PointsMap } from "../components/Maps";
import CompanyBar, { useCompany } from "../components/CompanyBar";

const PALETTE = ["#087f78", "#126f99", "#e4775d", "#8257bd", "#c99700", "#2b8a3e", "#d9480f", "#0b7285",
  "#5c7cfa", "#a61e4d", "#495057", "#74b816", "#f76707", "#1098ad", "#862e9c"];

export default function Analytics() {
  const [clusters, setClusters] = useState(null);
  const [demand, setDemand] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [rain, setRain] = useState(false);
  const [ml, setMl] = useState(null);
  const [error, setError] = useState("");
  const [company, setCompany] = useCompany();

  useEffect(() => { api("/api/ml/models").then(setMl).catch(() => {}); }, []);
  useEffect(() => {
    api(`/api/clusters?office=${company.office}`).then(setClusters).catch((e) => setError(e.message));
    api("/api/digital-twin/simulate", { method: "POST", body: { office_zone: company.office, headcount: company.headcount,
      start_time: company.start_time } }).then(setBaseline).catch((e) => setError(e.message));
  }, [company]);
  useEffect(() => {
    api(`/api/demand?rain=${rain}`).then(setDemand).catch((e) => setError(e.message));
  }, [rain]);

  const curve = (demand?.hours || []).map((h) => ({
    hour: `${String(h.hour).padStart(2, "0")}:00`,
    demand: h.demand_index, quote: Math.round(h.quote_probability * 100),
    price: h.price_pressure_multiplier, earning: h.driver_side.auto.est_hourly_earning_inr,
    success: Math.round((h.trip_success_probability ?? h.quote_probability) * 100),
  }));
  const b = baseline?.baseline;
  const share = b ? Object.entries(b.mode_share).map(([m, v]) => ({ mode: m, share: Math.round(v.share * 1000) / 10 })) : [];

  return (
    <>
      {error && <div className="panel"><p className="trip-history-error">{error}</p></div>}
      <div className="panel"><CompanyBar company={company} setCompany={setCompany}
        note="Organisation figures below are for this office's Census-derived commuter population."/></div>
      {b && (
        <div className="stats-grid">
          <div className="stat-card"><div className="stat-top"><span>Employees modelled</span><div className="stat-icon"><Users size={19}/></div></div><h2>{b.employees.toLocaleString("en-IN")}</h2><div className="stat-change"><span>Census 2011 ward populations + Table B-28</span></div></div>
          <div className="stat-card"><div className="stat-top"><span>Average commute</span><div className="stat-icon"><Clock size={19}/></div></div><h2>{b.avg_commute_min} min</h2><div className="stat-change"><span>one way, baseline</span></div></div>
          <div className="stat-card"><div className="stat-top"><span>Organisation CO₂e</span><div className="stat-icon"><Leaf size={19}/></div></div><h2>{b.annual.co2e_tonnes} t / yr</h2><div className="stat-change"><span>{b.avg_co2e_per_employee_kg} kg per employee per trip</span></div></div>
          <div className="stat-card"><div className="stat-top"><span>Carpool zones</span><div className="stat-icon"><MapPin size={19}/></div></div><h2>{clusters?.cluster_count ?? "…"}</h2><div className="stat-change"><span>K-Means on home ward location</span></div></div>
        </div>
      )}

      <div className="panel">
        <div className="panel-heading"><div><h3>Ride-hailing demand & driver side (Namma Yatri open data)</h3>
          <p>Demand index, chance of getting a driver quote, modelled price pressure and estimated auto-driver hourly earnings.</p></div>
          <label className="inline-toggle"><input type="checkbox" checked={rain} onChange={(e) => setRain(e.target.checked)}/> Rainy day</label></div>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={curve}>
            <CartesianGrid strokeDasharray="3 3" vertical={false}/>
            <XAxis dataKey="hour" interval={2}/>
            <YAxis yAxisId="l"/><YAxis yAxisId="r" orientation="right" unit="%"/>
            <Tooltip/><Legend/>
            <Bar yAxisId="l" dataKey="demand" name="Demand index (1 = daily mean)" fill="#b8e3d4"/>
            <Line yAxisId="l" dataKey="price" name="Price pressure ×" stroke="#e4775d" strokeWidth={2} dot={false}/>
            <Line yAxisId="r" dataKey="quote" name="Driver-quote probability %" stroke="#126f99" strokeWidth={2} dot={false}/>
            <Line yAxisId="r" dataKey="success" name="Ride actually happens %" stroke="#8257bd" strokeWidth={2} strokeDasharray="5 4" dot={false}/>
          </ComposedChart>
        </ResponsiveContainer>
        <p className="muted">{demand?.hours?.[0]?.model?.predictor}. {demand?.hours?.[0]?.model?.note} Source: {demand?.hours?.[0]?.source}.</p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={curve}>
            <CartesianGrid strokeDasharray="3 3" vertical={false}/>
            <XAxis dataKey="hour" interval={2}/><YAxis unit="₹"/><Tooltip/>
            <Bar dataKey="earning" name="Est. auto-driver earning per active hour (₹)" fill="#087f78"/>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {ml?.ride_hailing && (
        <div className="panel">
          <div className="panel-heading"><div><h3>Machine-learning models (MLOps)</h3>
            <p>Gradient-boosted ward × hour models trained on {ml.ride_hailing.data.train_dates.join(", ")} and tested on the unseen day {ml.ride_hailing.data.test_date} ({ml.ride_hailing.data.rows.toLocaleString("en-IN")} rows, {ml.ride_hailing.data.wards} wards). A model is only used if it beats the hour-of-day baseline.</p></div>
            <span className="soft-tag">version {ml.ride_hailing.version}</span></div>
          <div className="table-wrap"><table>
            <thead><tr><th>Predicts</th><th>Model R²</th><th>Baseline R²</th><th>Model RMSE</th><th>Baseline RMSE</th><th>Error reduction</th><th>Served</th></tr></thead>
            <tbody>{Object.entries(ml.ride_hailing.targets).map(([k, t]) => (
              <tr key={k}><td>{t.description}</td><td>{t.model.r2.toFixed(2)}</td><td>{t.baseline_hour_of_day.r2.toFixed(2)}</td>
                <td>{t.model.rmse.toFixed(3)}</td><td>{t.baseline_hour_of_day.rmse.toFixed(3)}</td>
                <td className={t.rmse_improvement_pct > 0 ? "delta-good" : "delta-bad"}>{t.rmse_improvement_pct > 0 ? "−" : "+"}{Math.abs(t.rmse_improvement_pct)}%</td>
                <td>{t.champion === "model" ? "ML model" : "Baseline"}</td></tr>))}</tbody>
          </table></div>
          {ml.fare_validation && <p className="muted">Fare model check against {ml.fare_validation.wards} wards' observed Namma Yatri averages: trip-weighted error {ml.fare_validation.trip_weighted_mape_pct}% (bias {ml.fare_validation.trip_weighted_bias_pct > 0 ? "+" : ""}{ml.fare_validation.trip_weighted_bias_pct}%; ₹{ml.fare_validation.predicted_fare_per_km}/km predicted vs ₹{ml.fare_validation.observed_fare_per_km}/km observed).</p>}
          <p className="muted">Experiments are tracked in MLflow{ml.ride_hailing.mlflow ? ` (run ${ml.ride_hailing.mlflow.run_id.slice(0, 8)})` : ""}. Retrain: <code>{ml.how_to_retrain}</code>. User preferences: {ml.preference_model.type}.</p>
        </div>
      )}

      <div className="content-grid two-col">
        <div className="panel">
          <div className="panel-heading"><div><h3>Carpool zones (K-Means)</h3><p>{clusters?.algorithm}</p></div></div>
          {clusters && <PointsMap points={clusters.clusters.map((c, i) => ({ key: c.cluster_id, lat: c.centroid_lat, lon: c.centroid_lon,
            radius: 6 + Math.sqrt(c.employee_count) / 3, color: PALETTE[i % PALETTE.length],
            label: `Zone ${c.cluster_id}: ${c.employee_count} employees · avg departure ${c.avg_departure} · ${c.car_owners} drive today` }))}/>}
          {clusters && (
            <div className="table-wrap"><table>
              <thead><tr><th>Zone</th><th>Employees</th><th>Departure</th><th>Avg km</th><th>Drive today</th><th>Main home areas</th></tr></thead>
              <tbody>{clusters.clusters.map((c) => (
                <tr key={c.cluster_id}><td>{c.cluster_id}</td><td>{c.employee_count}</td><td>{c.avg_departure}</td><td>{c.avg_commute_km}</td>
                  <td>{c.car_owners}</td><td>{Object.keys(c.top_home_zones).join(", ")}</td></tr>))}</tbody>
            </table></div>
          )}
        </div>
        <div className="panel">
          <div className="panel-heading"><div><h3>Baseline mode share</h3><p>{baseline?.assumptions?.[0]}</p></div></div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={share} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false}/>
              <XAxis type="number" unit="%"/><YAxis type="category" dataKey="mode" width={110}/><Tooltip formatter={(v) => `${v}%`}/>
              <Bar dataKey="share" fill="#087f78" radius={[0, 6, 6, 0]}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}
