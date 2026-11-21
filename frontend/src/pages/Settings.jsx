import { useEffect, useState } from "react";
import { Save, RotateCcw } from "lucide-react";
import { api } from "../lib/api";

const PROFILES = [["green_first", "Lower emissions first"], ["balanced", "Balanced"], ["fastest", "Fastest"],
  ["cheapest", "Cheapest"], ["comfort", "Comfort (less walking, fewer transfers)"]];

// Commute profile stored in PostgreSQL (users table). These preferences are
// applied by the backend to every recommendation.
export default function Settings({ profile, onSaved }) {
  const [form, setForm] = useState(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!profile) return;
    const p = profile.preferences || {};
    const v = profile.vehicle || {};
    setForm({
      name: profile.name || "", employee_id: profile.employee_id || "",
      profile: p.profile || "green_first", max_walking_minutes: p.max_walking_minutes ?? "",
      max_transfers: p.max_transfers ?? "", owns_car: !!p.owns_car, carpool_willing: p.carpool_willing ?? true,
      has_vehicle: !!profile.vehicle, vehicle_type: v.type || "car", fuel_type: v.fuel_type || "petrol",
      efficiency: v.efficiency ?? "",
    });
  }, [profile]);

  if (!form) return <div className="panel"><p className="muted">Loading your profile…</p></div>;
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function save(event, reset = false) {
    event?.preventDefault();
    setStatus(""); setError("");
    const preferences = { profile: form.profile, owns_car: form.owns_car, carpool_willing: form.carpool_willing };
    if (form.max_walking_minutes !== "") preferences.max_walking_minutes = Number(form.max_walking_minutes);
    if (form.max_transfers !== "") preferences.max_transfers = Number(form.max_transfers);
    const body = { name: form.name || null, employee_id: form.employee_id.trim().toUpperCase(), preferences,
      reset_learning: reset };
    if (form.has_vehicle) {
      body.vehicle = { type: form.vehicle_type, fuel_type: form.fuel_type };
      if (form.efficiency !== "") body.vehicle.efficiency = Number(form.efficiency);
    }
    try {
      const updated = await api("/api/users/me", { method: "PATCH", body });
      setStatus(reset ? "Learning reset. Your stated profile is used again." : "Profile saved. It applies to your next search.");
      onSaved?.(updated);
    } catch (e) {
      setError(e.message);
    }
  }

  const unit = form.fuel_type === "electric" ? "kWh per km" : form.fuel_type === "cng" ? "km per kg" : "km per litre";

  return (
    <form className="panel settings-form" onSubmit={save}>
      <h3>Commute profile</h3>
      <p className="muted">Stored in your account and applied by the planner to every search.</p>

      <div className="setting-row"><div><strong>Display name</strong><p>Optional</p></div><input value={form.name} onChange={set("name")} maxLength={120}/></div>
      <div className="setting-row"><div><strong>Employee ID</strong><p>Your company employee ID, shown on your profile. Carpool matches come from colleagues' saved trips, not from this ID.</p></div><input value={form.employee_id} onChange={set("employee_id")} placeholder="e.g. EMP-1042"/></div>
      <div className="setting-row"><div><strong>Starting priority</strong><p>Used until the planner has learned from your choices.</p></div>
        <select value={form.profile} onChange={set("profile")}>{PROFILES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
      <div className="setting-row"><div><strong>Maximum walking (minutes)</strong><p>Total walking per trip; reduced automatically when it rains.</p></div><input type="number" min="1" max="60" value={form.max_walking_minutes} onChange={set("max_walking_minutes")} placeholder="~31 (default 2.5 km)"/></div>
      <div className="setting-row"><div><strong>Maximum transfers</strong><p>Leave empty for no limit.</p></div><input type="number" min="0" max="5" value={form.max_transfers} onChange={set("max_transfers")}/></div>
      <div className="setting-row"><div><strong>I own a car</strong><p>Carpools can then make you the driver.</p></div><input type="checkbox" checked={form.owns_car} onChange={set("owns_car")}/></div>
      <div className="setting-row"><div><strong>Open to carpooling</strong><p>Shown to compatible colleagues as willing to share.</p></div><input type="checkbox" checked={form.carpool_willing} onChange={set("carpool_willing")}/></div>
      <div className="setting-row"><div><strong>Use my own vehicle for emissions</strong><p>Otherwise a documented default vehicle is used (wider uncertainty range).</p></div><input type="checkbox" checked={form.has_vehicle} onChange={set("has_vehicle")}/></div>
      {form.has_vehicle && (
        <div className="vehicle-row">
          <label>Type<select value={form.vehicle_type} onChange={set("vehicle_type")}><option value="car">Car</option><option value="two_wheeler">Two-wheeler</option></select></label>
          <label>Fuel<select value={form.fuel_type} onChange={set("fuel_type")}>
            {["petrol", "diesel", "cng", "lpg", "e20", "hybrid", "electric"].map((f) => <option key={f} value={f}>{f.toUpperCase()}</option>)}</select></label>
          <label>Efficiency ({unit})<input type="number" step="0.001" min="0" value={form.efficiency} onChange={set("efficiency")} placeholder="default"/></label>
        </div>
      )}
      {error && <div className="planner-error" role="alert">{error}</div>}
      {status && <div className="choice-feedback" role="status">{status}</div>}
      <div className="settings-actions">
        <button type="submit" className="plan-button"><Save size={16}/> Save profile</button>
        <button type="button" className="locate-button" onClick={(e) => save(e, true)}><RotateCcw size={15}/> Reset learned preferences{profile.choice_count ? ` (${profile.choice_count} choices)` : ""}</button>
      </div>
    </form>
  );
}
