import { useCallback, useEffect, useState } from "react";
import { MapPin, Users, Car, Clock, Route, Phone, Mail, MessageCircle, Check, X, Send, ShieldCheck, Info } from "lucide-react";
import { api } from "../lib/api";
import { PointsMap } from "../components/Maps";
import { usePersistentState } from "../lib/usePersistentState";

const ROLE_LABEL = { driver: "Drives", rider: "Needs a ride", either: "Drive or ride" };

function ContactCard({ contact }) {
  return (
    <div className="contact-card">
      <strong>{contact.name}</strong>
      <div className="contact-actions">
        <a className="contact-btn" href={contact.mailto}><Mail size={15}/> {contact.email}</a>
        {contact.phone && <a className="contact-btn" href={`tel:${contact.phone.replace(/\s/g, "")}`}><Phone size={15}/> {contact.phone}</a>}
        {contact.whatsapp_url && <a className="contact-btn whatsapp" href={contact.whatsapp_url} target="_blank" rel="noreferrer"><MessageCircle size={15}/> WhatsApp</a>}
      </div>
      {!contact.phone && <small className="muted">Phone not shared. Use email to coordinate.</small>}
    </div>
  );
}

function ProfileForm({ me, onSaved }) {
  const p = me.profile;
  const [form, setForm] = useState({ available: p.available, role: p.role, seats: p.seats, phone: p.phone || "",
    share_phone: p.share_phone, note: p.note || "" });
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function save(e, fromTrip = false) {
    e?.preventDefault();
    setMsg(""); setErr("");
    try {
      await api("/api/carpool/profile", { method: "PUT", body: { ...form, seats: Number(form.seats),
        phone: form.phone.trim() || null, note: form.note.trim() || null, save_commute_from_last_trip: fromTrip } });
      setMsg(fromTrip ? "Your regular commute was set from your last saved trip." : "Carpool profile saved.");
      onSaved();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  const c = me.regular_commute;
  return (
    <form className="panel carpool-profile" onSubmit={save}>
      <div className="panel-heading"><div><h3>Your carpool profile</h3>
        <p>Colleagues only see your name, role and how compatible your commutes are. Contact details are shared only when you accept a request, or when someone accepts yours.</p></div>
        <ShieldCheck size={20} color="#16865b"/></div>
      <div className="commute-summary">
        <Route size={16}/>
        {c ? <span><strong>Regular commute</strong> ({me.regular_source}): {c.home_label || "home"} → {c.office_label || "office"}, leaving {c.departure_time}</span>
          : <span><strong>No regular commute yet.</strong> Link your employee ID in Settings, or plan a trip on the Dashboard and choose a route.</span>}
        {me.regular_source !== "employee profile" && <button type="button" className="link-btn" onClick={(e) => save(e, true)}>Use my last saved trip</button>}
      </div>
      <div className="carpool-form-grid">
        <label className="check"><input type="checkbox" checked={form.available} onChange={set("available")}/> Available for carpooling</label>
        <label>I can<select value={form.role} onChange={set("role")}>
          <option value="either">Drive or ride</option><option value="driver">Drive (offer seats)</option><option value="rider">Ride (need a seat)</option></select></label>
        <label>Seats offered<input type="number" min="1" max="6" value={form.seats} onChange={set("seats")} disabled={form.role === "rider"}/></label>
        <label>Phone (optional)<input value={form.phone} onChange={set("phone")} placeholder="98450 12345"/></label>
        <label className="check"><input type="checkbox" checked={form.share_phone} onChange={set("share_phone")}/> Share my phone after a request is accepted</label>
        <label className="wide">Note for colleagues<input value={form.note} onChange={set("note")} maxLength={280} placeholder="e.g. Leave 8:30 from HSR 27th Main, back by 6:30"/></label>
      </div>
      {err && <div className="planner-error">{err}</div>}
      {msg && <div className="choice-feedback">{msg}</div>}
      <button type="submit" className="plan-button">Save carpool profile</button>
    </form>
  );
}

export default function Carpooling({ goTo, onRequestsChanged }) {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);
  const [drafts, setDrafts] = useState({});
  // The trip planned on the Dashboard (shared planner state).
  const [originPt] = usePersistentState("originPt", null);
  const [destinationPt] = usePersistentState("destinationPt", null);
  const [when] = usePersistentState("when", null);
  const [originLabel] = usePersistentState("origin", "");
  const [destinationLabel] = usePersistentState("destination", "");
  const [roundTrip] = usePersistentState("roundTrip", { enabled: false, time: "18:00" });
  const hasPlannedTrip = !!(originPt && destinationPt && when?.time);
  const hasReturn = hasPlannedTrip && !!roundTrip?.enabled;
  const [basis, setBasis] = useState(hasPlannedTrip ? "planned" : "regular");
  const trip = basis === "planned" && hasPlannedTrip ? {
    olat: originPt.lat, olon: originPt.lng, dlat: destinationPt.lat, dlon: destinationPt.lng,
    time: when.time, date: when.date, olabel: originLabel.slice(0, 200), dlabel: destinationLabel.slice(0, 200),
  } : basis === "return" && hasReturn ? {
    olat: destinationPt.lat, olon: destinationPt.lng, dlat: originPt.lat, dlon: originPt.lng,
    time: roundTrip.time, date: when.date, olabel: destinationLabel.slice(0, 200), dlabel: originLabel.slice(0, 200),
  } : null;
  const tripKey = trip ? JSON.stringify(trip) : "regular";

  const load = useCallback(() => {
    const qs = trip ? `?${new URLSearchParams({ olat: trip.olat, olon: trip.olon, dlat: trip.dlat, dlon: trip.dlon,
      time: trip.time, date: trip.date, olabel: trip.olabel, dlabel: trip.dlabel })}` : "";
    api(`/api/carpool/board${qs}`).then((b) => { setBoard(b); setError(""); onRequestsChanged?.(b.pending_incoming); })
      .catch((e) => setError(e.message));
  }, [onRequestsChanged, tripKey]);

  useEffect(() => { load(); }, [load]);

  async function act(key, fn) {
    setBusy(key);
    try { await fn(); load(); } catch (e) { setError(e.message); } finally { setBusy(null); }
  }

  if (error && !board) return <div className="panel"><p className="trip-history-error">{error}</p></div>;
  if (!board) return <div className="panel"><p className="muted">Loading carpool board…</p></div>;

  const incoming = board.requests.filter((r) => r.direction === "incoming" && r.status === "pending");
  const outgoing = board.requests.filter((r) => r.direction === "outgoing" && r.status === "pending");
  const accepted = board.requests.filter((r) => r.status === "accepted");
  const c = board.me.commute;

  return (
    <>
      {error && <div className="planner-error" role="alert">{error}</div>}
      <ProfileForm me={board.me} onSaved={load}/>

      <div className="panel match-basis">
        <div><strong>Find colleagues for:</strong></div>
        <label className={`goal-chip ${basis === "planned" ? "selected" : ""} ${!hasPlannedTrip ? "disabled" : ""}`}>
          <input type="radio" name="basis" checked={basis === "planned"} disabled={!hasPlannedTrip} onChange={() => setBasis("planned")}/>
          {hasPlannedTrip ? `My planned trip: ${originLabel || "start"} → ${destinationLabel || "destination"}, ${when.date} at ${when.time}` : "My planned trip (plan one on the Dashboard first)"}
        </label>
        {hasReturn && (
          <label className={`goal-chip ${basis === "return" ? "selected" : ""}`}>
            <input type="radio" name="basis" checked={basis === "return"} onChange={() => setBasis("return")}/>
            My return trip: {destinationLabel || "destination"} → {originLabel || "start"}, {when.date} at {roundTrip.time}
          </label>
        )}
        <label className={`goal-chip ${basis === "regular" ? "selected" : ""}`}>
          <input type="radio" name="basis" checked={basis === "regular"} onChange={() => setBasis("regular")}/>
          My regular commute{board.me.regular_commute ? `: ${board.me.regular_commute.home_label || "home"} → ${board.me.regular_commute.office_label || "office"}, ${board.me.regular_commute.departure_time}` : " (not set)"}
        </label>
        <small className="muted">Colleagues are matched on what they are doing at that time: their own planned trip that day if they have one, otherwise their regular morning commute or their evening return trip.</small>
      </div>

      {(incoming.length > 0 || outgoing.length > 0 || accepted.length > 0) && (
        <div className="panel">
          <div className="panel-heading"><div><h3>Carpool requests</h3><p>Accept a request to exchange contact details.</p></div></div>
          {incoming.map((r) => (
            <div className="request-row" key={r.id}>
              <div><strong>{r.other.name}</strong> wants to carpool with you{r.message ? `: “${r.message}”` : "."}
                <small className="muted"> · {new Date(r.created_at).toLocaleString()}</small></div>
              <div className="request-actions">
                <button className="choose-btn" disabled={busy === r.id} onClick={() => act(r.id, () => api(`/api/carpool/requests/${r.id}/respond`, { method: "POST", body: { accept: true } }))}><Check size={15}/> Accept</button>
                <button className="locate-button" disabled={busy === r.id} onClick={() => act(r.id, () => api(`/api/carpool/requests/${r.id}/respond`, { method: "POST", body: { accept: false } }))}><X size={15}/> Decline</button>
              </div>
            </div>
          ))}
          {outgoing.map((r) => (
            <div className="request-row" key={r.id}>
              <div>Waiting for <strong>{r.other.name}</strong> to respond<small className="muted"> · sent {new Date(r.created_at).toLocaleString()}</small></div>
              <button className="locate-button" disabled={busy === r.id} onClick={() => act(r.id, () => api(`/api/carpool/requests/${r.id}/cancel`, { method: "POST" }))}>Cancel</button>
            </div>
          ))}
          {accepted.map((r) => (
            <div className="request-row accepted" key={r.id}>
              {r.contact && <ContactCard contact={r.contact}/>}
              <button className="locate-button" disabled={busy === r.id} onClick={() => act(r.id, () => api(`/api/carpool/requests/${r.id}/cancel`, { method: "POST" }))}>End carpool</button>
            </div>
          ))}
        </div>
      )}

      <div className="panel">
        <div className="panel-heading">
          <div><h3>Available colleagues on SmartCommute</h3>
            <p>Registered colleagues who are available and travelling {board.me.commute_source === "planned trip" ? `your planned trip (${board.me.commute?.home_label} → ${board.me.commute?.office_label}, ${board.me.trip_date} at ${board.me.commute?.departure_time})` : "your regular commute"}: start within {board.limits.max_origin_km} km, destination within {board.limits.max_destination_km} km, leaving within ±{board.limits.max_departure_diff_min} min.</p></div>
          <span className="green-tag">{board.app_matches.length} available</span>
        </div>
        {!c && <div className="empty-state"><Users size={28}/><p>Set your regular commute first: link your employee ID in <button type="button" className="link-btn" onClick={() => goTo("Settings")}>Settings</button>, or <button type="button" className="link-btn" onClick={() => goTo("Dashboard")}>plan and save a trip</button>.</p></div>}
        {c && board.app_matches.length === 0 && (
          <div className="empty-state"><Info size={24}/><p>{board.me.commute_source === "planned trip"
            ? `No available colleague is travelling a similar route around ${board.me.commute?.departure_time} on ${board.me.trip_date}. For a demo, have a colleague plan the same trip on their Dashboard and press "I'll take this", or switch to your regular commute above.`
            : "No registered colleague with a compatible regular commute is available right now. Ask your team to register, link their employee IDs and mark themselves available."}</p></div>
        )}
        <div className="employee-grid">
          {board.app_matches.map((m) => (
            <div className="employee-card" key={m.ref}>
              <div className="avatar">{m.role === "driver" ? <Car size={20}/> : <Users size={20}/>}</div>
              <h3>{m.name}</h3>
              <p><MapPin size={14}/> {m.office_label ? `Works near ${m.office_label}` : "Compatible commute"}</p>
              <div className="employee-details"><span><Clock size={13}/> Leaves</span><strong>{m.departure_time} ({m.departure_difference_min} min apart)</strong></div>
              <p className="muted basis-note">Based on {m.basis}</p>
              <div className="employee-details"><span><Route size={13}/> From your home</span><strong>{m.pickup_distance_km} km</strong></div>
              <div className="employee-details"><span>Role</span><strong>{ROLE_LABEL[m.role]}{m.role !== "rider" ? ` · ${m.seats} seat${m.seats > 1 ? "s" : ""}` : ""}</strong></div>
              <div className="employee-details"><span>Compatibility</span><strong className="match">{m.compatibility_pct}%</strong></div>
              {m.note && <p className="muted note">“{m.note}”</p>}
              {m.contact ? <ContactCard contact={m.contact}/>
                : m.request?.status === "pending" ? (
                  <button className="primary-btn full" disabled>{m.request.direction === "outgoing" ? "Request sent · waiting" : "They asked you · see requests above"}</button>
                ) : (
                  <>
                    <input className="request-note" placeholder="Optional message" value={drafts[m.ref] || ""}
                      onChange={(e) => setDrafts((d) => ({ ...d, [m.ref]: e.target.value }))} maxLength={500}/>
                    <button className="primary-btn full" disabled={busy === m.ref}
                      onClick={() => act(m.ref, () => api("/api/carpool/requests", { method: "POST", body: { to_ref: m.ref, message: drafts[m.ref] || null, trip } }))}>
                      <Send size={14}/> Request to carpool
                    </button>
                  </>
                )}
            </div>
          ))}
        </div>
      </div>

      <p className="map-note">{board.privacy}</p>
    </>
  );
}
