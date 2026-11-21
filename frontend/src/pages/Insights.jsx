import { useEffect, useState } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell } from "recharts";
import { Lightbulb, Brain, Target, Bus, Users, TrainFront } from "lucide-react";
import { api } from "../lib/api";
import { MODE_LABELS } from "../lib/format";

const FEATURE_LABELS = { emissions: "Low CO₂e", duration: "Travel time", cost: "Cost", walking: "Less walking",
  transfers: "Fewer transfers", uncertainty: "Reliability" };

// Personalised insights: the weights the ranking model has learned from the
// routes this user actually chose, and what that means.
export default function Insights({ profile, goTo }) {
  const [meta, setMeta] = useState(null);
  const [hist, setHist] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api("/api/meta"), api("/api/users/me/history")])
      .then(([m, h]) => { setMeta(m); setHist(h); })
      .catch((e) => setError(e.message));
  }, [profile?.choice_count]);

  if (error) return <div className="panel"><p className="trip-history-error">{error}</p></div>;
  if (!meta || !hist) return <div className="panel"><p className="muted">Loading your insights…</p></div>;

  const profileName = profile?.preferences?.profile || meta.default_profile;
  const learned = profile?.weights;
  const weights = learned || meta.profiles[profileName];
  const chart = Object.entries(weights).map(([k, v]) => ({ name: FEATURE_LABELS[k], value: Math.round(v * 100),
    start: Math.round((meta.profiles[profileName][k] || 0) * 100) }));
  const modes = Object.entries(hist.impact.mode_counts).map(([k, v]) => ({ name: MODE_LABELS[k] || k, value: v }));
  const accept = hist.impact.accepted_recommendation_rate;

  const tips = [];
  const counts = hist.impact.mode_counts;
  if ((counts.car || 0) + (counts.cab || 0) + (counts.auto || 0) > (counts.bus || 0) + (counts.metro || 0) + (counts.bus_metro || 0))
    tips.push({ icon: Bus, title: "Try transit on one day a week", text: "Most of your chosen trips are by road. Each bus or Metro commute you swap in typically cuts that trip's CO₂e by 70–90 %." });
  tips.push({ icon: Users, title: "Open up to carpooling", text: "Mark yourself available on the Carpooling page and save your usual trip: colleagues who travel the same way at a similar time will see you and can send a request.", action: "Carpooling" });
  if (!profile?.preferences?.max_walking_minutes)
    tips.push({ icon: Target, title: "Set your walking limit", text: "Tell the planner how far you are happy to walk so it filters out options you would never take.", action: "Settings" });
  tips.push({ icon: TrainFront, title: "Check the Metro at peak hours", text: "At 8–10 am and 5–8 pm road travel times are typically 1.6–2× free-flow, while Metro times stay close to the timetable." });

  return (
    <>
      <div className="content-grid two-col">
        <div className="panel">
          <div className="panel-heading"><div><h3>What the planner has learned about you</h3>
            <p>{learned ? `Learned from ${profile.choice_count} route choice${profile.choice_count === 1 ? "" : "s"} (conditional-logit model).` : `Starting profile: ${profileName.replace("_", " ")}. Choose routes on the Dashboard to personalise it.`}</p></div>
            <Brain size={20} color="#16865b"/></div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chart} layout="vertical" margin={{ left: 30 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false}/>
              <XAxis type="number" unit="%"/><YAxis type="category" dataKey="name" width={110}/>
              <Tooltip formatter={(v, n) => [`${v}%`, n === "value" ? "Current weight" : "Starting weight"]}/>
              {learned && <Bar dataKey="start" fill="#cfe3df" radius={[0, 6, 6, 0]}/>}
              <Bar dataKey="value" fill="#087f78" radius={[0, 6, 6, 0]}/>
            </BarChart>
          </ResponsiveContainer>
          <p className="muted">{learned ? "Pale bars: starting weights · dark bars: learned weights." : ""} Higher weight = that factor matters more when ranking your options.</p>
        </div>
        <div className="panel">
          <div className="panel-heading"><div><h3>Your choices</h3><p>{hist.impact.trips} trip{hist.impact.trips === 1 ? "" : "s"} chosen{accept != null ? ` · ${Math.round(accept * 100)}% matched our top pick` : ""}</p></div></div>
          {modes.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={modes}>
                <CartesianGrid strokeDasharray="3 3" vertical={false}/>
                <XAxis dataKey="name"/><YAxis allowDecimals={false}/><Tooltip/>
                <Bar dataKey="value" name="Trips" radius={[7, 7, 0, 0]}>{modes.map((m, i) => <Cell key={i} fill="#16865b"/>)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="muted">No choices yet. On the Dashboard, press “I'll take this” on a route.</p>}
        </div>
      </div>
      <div className="employee-grid">
        {tips.map((t) => {
          const Icon = t.icon || Lightbulb;
          return (
            <div className="recommend-card" key={t.title}>
              <div className="large-icon"><Icon size={26}/></div><h3>{t.title}</h3><p>{t.text}</p>
              {t.action && <button type="button" className="link-btn" onClick={() => goTo(t.action)}>Open {t.action}</button>}
            </div>
          );
        })}
      </div>
    </>
  );
}
