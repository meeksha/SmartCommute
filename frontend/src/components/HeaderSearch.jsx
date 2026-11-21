import { useEffect, useRef, useState } from "react";
import { Search, MapPin, Building2, TrainFront, Bus, ArrowRight, CornerDownRight } from "lucide-react";
import { api } from "../lib/api";
import { setPersistentValue } from "../lib/usePersistentState";

const KIND_ICON = { office: Building2, metro_station: TrainFront, rail_station: TrainFront, bus_stop: Bus };
const KIND_LABEL = { office: "Office zone", metro_station: "Namma Metro station", rail_station: "Railway station", bus_stop: "BMTC stop" };

// Global search: jump to a page, or pick a place and drop it into the
// Dashboard planner as the destination (or starting point).
export default function HeaderSearch({ pages, onNavigate }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [places, setPlaces] = useState([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [active, setActive] = useState(-1);
  const inputRef = useRef(null);

  const term = q.trim().toLowerCase();
  const pageHits = term.length >= 2
    ? pages.filter((p) => p.name.toLowerCase().includes(term) || p.keywords.some((k) => k.includes(term))).slice(0, 3)
    : [];

  useEffect(() => {
    if (!open || term.length < 2) { setPlaces([]); setSearching(false); setError(""); return undefined; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setSearching(true); setError("");
      try {
        const { results } = await api(`/api/places/search?${new URLSearchParams({ q: q.trim(), limit: "6" })}`, { signal: controller.signal });
        setPlaces(results.map((r, i) => ({
          id: `${r.kind}-${i}-${r.lat}`, name: r.name, kind: r.kind, lat: r.lat, lng: r.lon,
          detail: r.kind === "osm" ? (r.label || "").split(",").slice(1, 3).join(",").trim() || "Bengaluru region" : KIND_LABEL[r.kind],
        })));
        setActive(-1);
      } catch (e) {
        if (e.name !== "AbortError") { setPlaces([]); setError(e.message || "Place search failed."); }
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }, 400);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [open, q, term.length]);

  const items = [
    ...pageHits.map((p) => ({ type: "page", key: `page-${p.name}`, page: p })),
    ...places.map((pl) => ({ type: "place", key: pl.id, place: pl })),
  ];

  function reset() { setQ(""); setPlaces([]); setOpen(false); setActive(-1); inputRef.current?.blur(); }

  function usePlace(place, field) {
    const label = place.name;
    const pt = { lat: place.lat, lng: place.lng };
    setPersistentValue(field, label);
    setPersistentValue(`${field}Pt`, pt);
    setPersistentValue("result", null);
    setPersistentValue("selectedId", null);
    setPersistentValue("resultBack", null);
    onNavigate("Dashboard");
    reset();
  }

  function pick(item, field = "destination") {
    if (item.type === "page") { onNavigate(item.page.name); reset(); }
    else usePlace(item.place, field);
  }

  function onKeyDown(e) {
    if (e.key === "ArrowDown" && items.length) { e.preventDefault(); setActive((i) => (i + 1) % items.length); }
    else if (e.key === "ArrowUp" && items.length) { e.preventDefault(); setActive((i) => (i <= 0 ? items.length - 1 : i - 1)); }
    else if (e.key === "Enter") {
      const it = items[active >= 0 ? active : 0];
      if (it) { e.preventDefault(); pick(it); }
    } else if (e.key === "Escape") reset();
  }

  const show = open && term.length >= 2;

  return (
    <div className="search-box header-search">
      <Search size={17}/>
      <input ref={inputRef} value={q} placeholder="Search a place or page (e.g. Whitefield, Carpooling)"
        aria-label="Search places and pages" role="combobox" aria-expanded={show} autoComplete="off"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} onKeyDown={onKeyDown}/>
      {show && (
        <div className="header-search-results" role="listbox">
          {pageHits.length > 0 && <div className="hs-group">Pages</div>}
          {items.map((it, idx) => it.type === "page" ? (
            <button key={it.key} type="button" role="option" aria-selected={idx === active}
              className={`hs-item ${idx === active ? "active" : ""}`}
              onMouseDown={(e) => e.preventDefault()} onClick={() => pick(it)}>
              <it.page.icon size={16}/><span><strong>{it.page.name}</strong><small>{it.page.hint}</small></span><ArrowRight size={15}/>
            </button>
          ) : null)}
          <div className="hs-group">Places: set as your trip on the Dashboard</div>
          {searching && <div className="hs-status">Searching Bengaluru places, Metro stations and bus stops…</div>}
          {error && <div className="hs-status hs-error">{error}</div>}
          {!searching && !error && places.length === 0 && <div className="hs-status">No place found. Try an area, landmark, Metro station or bus stop.</div>}
          {!searching && items.map((it, idx) => {
            if (it.type !== "place") return null;
            const Icon = KIND_ICON[it.place.kind] || MapPin;
            return (
              <div key={it.key} className={`hs-item hs-place ${idx === active ? "active" : ""}`} role="option" aria-selected={idx === active}>
                <Icon size={16}/>
                <span><strong>{it.place.name}</strong><small>{it.place.detail}</small></span>
                <div className="hs-actions">
                  <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(it, "origin")} title="Use as starting point"><CornerDownRight size={14}/>From here</button>
                  <button type="button" className="primary" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(it, "destination")} title="Use as destination">To here</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
