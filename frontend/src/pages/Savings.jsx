import { useEffect, useState } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";
import { Wallet, Leaf, Users, Route } from "lucide-react";
import { api } from "../lib/api";
import { formatRupees } from "../lib/format";

function Stat({ title, value, note, icon: Icon }) {
  return (
    <div className="stat-card">
      <div className="stat-top"><span>{title}</span><div className="stat-icon"><Icon size={20}/></div></div>
      <h2>{value}</h2>
      <div className="stat-change"><span>{note}</span></div>
    </div>
  );
}

// Personal impact = sum over chosen trips of (drive-alone baseline - chosen
// option) as computed by the backend at the time of the choice.
export default function Savings({ goTo }) {
  const [hist, setHist] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/users/me/history").then(setHist).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="panel"><p className="trip-history-error">{error}</p></div>;
  if (!hist) return <div className="panel"><p className="muted">Loading your impact…</p></div>;
  const im = hist.impact;
  const co2 = im.co2e_saved_kg;

  return (
    <>
      <div className="stats-grid">
        <Stat title="Money saved vs. driving" value={formatRupees(im.money_saved_inr)} note={`over ${im.trips_with_drive_alone_baseline} comparable trip${im.trips_with_drive_alone_baseline === 1 ? "" : "s"} (fuel cost)`} icon={Wallet}/>
        <Stat title="CO₂e avoided" value={`${co2.toFixed(2)} kg`} note="vs. driving alone, per-person estimate" icon={Leaf}/>
        <Stat title="Shared rides" value={im.shared_rides} note="carpool trips chosen" icon={Users}/>
        <Stat title="Trips planned & chosen" value={im.trips} note={im.accepted_recommendation_rate != null ? `${Math.round(im.accepted_recommendation_rate * 100)}% were our top pick` : "no trips yet"} icon={Route}/>
      </div>
      <div className="panel">
        <div className="panel-heading"><div><h3>Your environmental impact</h3><p>Daily CO₂e avoided by the routes you chose.</p></div></div>
        {im.daily.length ? (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={im.daily}>
              <CartesianGrid strokeDasharray="3 3" vertical={false}/>
              <XAxis dataKey="date"/><YAxis unit=" kg"/>
              <Tooltip formatter={(v, n) => n === "co2e_saved_kg" ? [`${v} kg`, "CO₂e avoided"] : [`₹${v}`, "Money saved"]}/>
              <Bar dataKey="co2e_saved_kg" fill="#16865b" radius={[7, 7, 0, 0]}/>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty-state"><Leaf size={28}/><p>No impact recorded yet. <button type="button" className="link-btn" onClick={() => goTo("Dashboard")}>Plan a commute</button> and press “I'll take this” on a route.</p></div>
        )}
        <div className="impact-box"><Leaf size={35}/><div><h2>{co2.toFixed(1)} kg</h2><p>Estimated CO₂e avoided so far by the routes you chose.</p></div></div>
        <p className="muted">Figures are estimates from the same emissions model used for recommendations (well-to-wheel for road vehicles, life-cycle for transit) and assume the drive-alone trip is what you would otherwise have made.</p>
      </div>
    </>
  );
}
