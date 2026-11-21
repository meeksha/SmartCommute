import { useEffect, useState } from "react";
import { Building2 } from "lucide-react";
import { api } from "../lib/api";
import { usePersistentState } from "../lib/usePersistentState";

export const DEFAULT_COMPANY = { office: "cbd", headcount: 2000, start_time: "09:30" };

// Shared by the organisation pages (Digital Twin, Incentives, Shuttles, Analytics):
// which office, how many employees and when they start. The commuter population
// itself is built by the backend from Census 2011 data for that office.
export function useCompany() {
  return usePersistentState("company", DEFAULT_COMPANY);
}

export default function CompanyBar({ company, setCompany, note }) {
  const [offices, setOffices] = useState([]);
  const [count, setCount] = useState(String(company.headcount));
  useEffect(() => { api("/api/meta").then((m) => setOffices(m.offices || [])).catch(() => {}); }, []);
  useEffect(() => { setCount(String(company.headcount)); }, [company.headcount]);
  const commitCount = () => {
    const n = Math.max(50, Math.min(20000, Math.round(Number(count) || DEFAULT_COMPANY.headcount)));
    setCount(String(n));
    if (n !== company.headcount) setCompany({ ...company, headcount: n });
  };
  return (
    <div className="company-bar">
      <Building2 size={18} color="#16865b"/>
      <label>Office
        <select value={company.office} onChange={(e) => setCompany({ ...company, office: e.target.value })}>
          {offices.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </label>
      <label>Employees
        <input type="number" min={50} max={20000} step={50} value={count}
          onChange={(e) => setCount(e.target.value)} onBlur={commitCount}
          onKeyDown={(e) => { if (e.key === "Enter") commitCount(); }}/>
      </label>
      <label>Office start
        <input type="time" value={company.start_time}
          onChange={(e) => e.target.value && setCompany({ ...company, start_time: e.target.value })}/>
      </label>
      {note && <small className="muted">{note}</small>}
    </div>
  );
}
