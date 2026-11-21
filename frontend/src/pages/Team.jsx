import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api } from "../lib/api";

// Company admins can make other accounts admins (or turn them back into employees).
export default function Team({ me }) {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);

  const load = () => api("/api/admin/users").then((r) => { setUsers(r.users); setError(""); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function setRole(email, role) {
    setBusy(email);
    try {
      await api(`/api/admin/users/${encodeURIComponent(email)}/role`, { method: "PATCH", body: { role } });
      await load();
    } catch (e) { setError(e.message); } finally { setBusy(null); }
  }

  return (
    <div className="panel">
      <div className="panel-heading">
        <div><h3>Team and roles</h3>
          <p>Employees see their own commute pages: Dashboard, Carpooling, Recommendations, Savings and Settings. Admins also see company-wide pages: Digital Twin, Incentives, Shuttles and Analytics. A role change applies the next time that person reloads the page.</p></div>
        <ShieldCheck color="#16865b"/>
      </div>
      {error && <p className="trip-history-error">{error}</p>}
      {!users && !error && <p className="muted">Loading accounts…</p>}
      {users && (
        <div className="table-wrap"><table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th></th></tr></thead>
          <tbody>{users.map((u) => (
            <tr key={u.email}><td>{u.name || "—"}</td><td>{u.email}{u.email === me?.email ? " (you)" : ""}</td>
              <td>{u.role === "admin" ? <span className="soft-tag">Admin</span> : "Employee"}</td>
              <td>{u.role === "admin"
                ? <button type="button" className="locate-button" disabled={busy === u.email} onClick={() => setRole(u.email, "employee")}>Make employee</button>
                : <button type="button" className="locate-button" disabled={busy === u.email} onClick={() => setRole(u.email, "admin")}>Make admin</button>}</td></tr>))}</tbody>
        </table></div>
      )}
    </div>
  );
}
