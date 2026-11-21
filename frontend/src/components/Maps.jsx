import { useEffect, useMemo, useState } from "react";
import { Circle, CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { LEG_COLORS, formatDuration } from "../lib/format";

export const BENGALURU_CENTER = [12.9716, 77.5946];
const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>';
const ROAD_LEGS = new Set(["car", "cab", "auto", "two_wheeler", "carpool", "bicycle"]);
const geometryCache = new Map();

// Road legs from the backend carry only their endpoints (the routing APIs it
// uses return summaries, not shapes). For display we ask OSRM for the street
// geometry. Times, costs and CO2e still come only from the backend.
async function fetchRoadGeometry(leg) {
  const pts = [[leg.from.lat, leg.from.lon], ...(leg.pickups || []).map((p) => [p.lat, p.lon]), [leg.to.lat, leg.to.lon]];
  const key = `${leg.type}:${pts.map((p) => p.map((x) => x.toFixed(5)).join(",")).join(";")}`;
  if (geometryCache.has(key)) return geometryCache.get(key);
  const profile = leg.type === "bicycle" ? "routed-bike" : "routed-car";
  const coords = pts.map(([lat, lon]) => `${lon},${lat}`).join(";");
  const res = await fetch(`https://routing.openstreetmap.de/${profile}/route/v1/driving/${coords}?overview=full&geometries=geojson`);
  if (!res.ok) throw new Error(`OSRM ${res.status}`);
  const data = await res.json();
  const line = (data.routes?.[0]?.geometry?.coordinates || []).map(([lon, lat]) => [lat, lon]);
  geometryCache.set(key, line);
  return line;
}

export function optionSegments(option) {
  return (option?.legs || []).map((leg, i) => ({
    key: i,
    type: leg.type,
    positions: (leg.path || []).filter((p) => p && p[0] != null),
    color: leg.color || LEG_COLORS[leg.type] || "#126f99",
    label: leg.type === "walk"
      ? `Walk ${Math.round(leg.distance_m || 0)} m · ${formatDuration(leg.duration_min)}`
      : `${leg.label || leg.type}${leg.departure_time ? ` · ${leg.departure_time}→${leg.arrival_time}` : ""}${leg.from?.name ? ` · ${leg.from.name} → ${leg.to?.name}` : ""}`,
    leg,
  })).filter((s) => s.positions.length > 1);
}

function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points, { padding: [28, 28], maxZoom: 15 });
  }, [map, JSON.stringify(points.slice(0, 2)), points.length]);
  return null;
}

function FollowLiveLocation({ location }) {
  const map = useMap();
  useEffect(() => {
    if (location) map.panTo([location.lat, location.lng], { animate: true });
  }, [location, map]);
  return null;
}

export function CommuteMap({ option, origin, destination, liveLocation }) {
  const base = useMemo(() => optionSegments(option), [option]);
  const [roadLines, setRoadLines] = useState({});

  useEffect(() => {
    let active = true;
    setRoadLines({});
    base.forEach((seg) => {
      if (!ROAD_LEGS.has(seg.type) && !(seg.type === "walk" && seg.leg.segment === "direct")) return;
      fetchRoadGeometry(seg.leg)
        .then((line) => { if (active && line.length > 1) setRoadLines((cur) => ({ ...cur, [seg.key]: line })); })
        .catch(() => {});
    });
    return () => { active = false; };
  }, [base]);

  const segments = base.map((s) => ({ ...s, positions: roadLines[s.key] || s.positions }));
  const points = [origin && [origin.lat, origin.lng], destination && [destination.lat, destination.lng],
    ...segments.flatMap((s) => s.positions)].filter(Boolean);
  const stops = (option?.legs || []).filter((l) => l.type === "bus" || l.type === "metro" || l.type === "train");
  const pickups = (option?.legs || []).flatMap((l) => l.pickups || []);

  return (
    <MapContainer center={BENGALURU_CENTER} zoom={12} scrollWheelZoom={false} className="leaflet-route-map">
      <TileLayer attribution={TILE_ATTR} url={TILE_URL} maxZoom={19}/>
      {segments.map((s) => (
        <Polyline key={`${option.id}-${s.key}-${roadLines[s.key] ? "r" : "s"}`} positions={s.positions}
          pathOptions={{ color: s.color, weight: s.type === "walk" ? 4 : 6, opacity: 0.9,
            dashArray: s.type === "walk" ? "7 8" : undefined }}>
          <Popup>{s.label}</Popup>
        </Polyline>
      ))}
      {stops.map((l, i) => [l.from, l.to].map((p, j) => p?.lat && (
        <CircleMarker key={`stop-${i}-${j}`} center={[p.lat, p.lon]} radius={5}
          pathOptions={{ color: "#fff", weight: 2, fillColor: l.color || "#444", fillOpacity: 1 }}>
          <Popup>{p.name}{j === 0 && l.departure_time ? ` · departs ${l.departure_time}` : ""}</Popup>
        </CircleMarker>
      )))}
      {pickups.map((p) => (
        <CircleMarker key={p.employee_id} center={[p.lat, p.lon]} radius={6}
          pathOptions={{ color: "#fff", weight: 2, fillColor: "#2b8a3e", fillOpacity: 1 }}>
          <Popup>Pickup · colleague {p.employee_id} ({p.home_zone})</Popup>
        </CircleMarker>
      ))}
      {origin && <CircleMarker center={[origin.lat, origin.lng]} radius={8} pathOptions={{ color: "#fff", weight: 3, fillColor: "#087f70", fillOpacity: 1 }}><Popup>Starting point</Popup></CircleMarker>}
      {destination && <CircleMarker center={[destination.lat, destination.lng]} radius={8} pathOptions={{ color: "#fff", weight: 3, fillColor: "#e4775d", fillOpacity: 1 }}><Popup>Destination</Popup></CircleMarker>}
      {liveLocation && <>
        <Circle center={[liveLocation.lat, liveLocation.lng]} radius={liveLocation.accuracy} pathOptions={{ color: "#1479e8", fillColor: "#318bfa", fillOpacity: 0.12, weight: 1 }}/>
        <CircleMarker center={[liveLocation.lat, liveLocation.lng]} radius={9} pathOptions={{ color: "#fff", weight: 3, fillColor: "#1479e8", fillOpacity: 1 }}><Popup>You are here · live</Popup></CircleMarker>
        <FollowLiveLocation location={liveLocation}/>
      </>}
      <FitBounds points={points}/>
    </MapContainer>
  );
}

function MapClickSelector({ onSelect }) {
  useMapEvents({ click({ latlng }) { onSelect({ lat: latlng.lat, lng: latlng.lng }); } });
  return null;
}

export function LocationPickerMap({ selectedPoint, onSelect }) {
  return (
    <MapContainer center={selectedPoint ? [selectedPoint.lat, selectedPoint.lng] : BENGALURU_CENTER}
      zoom={selectedPoint ? 15 : 12} scrollWheelZoom className="location-picker-map">
      <TileLayer attribution={TILE_ATTR} url={TILE_URL} maxZoom={19}/>
      <MapClickSelector onSelect={onSelect}/>
      {selectedPoint && <CircleMarker center={[selectedPoint.lat, selectedPoint.lng]} radius={9} pathOptions={{ color: "#fff", weight: 3, fillColor: "#087f78", fillOpacity: 1 }}><Popup>Selected point</Popup></CircleMarker>}
    </MapContainer>
  );
}

export function PointsMap({ points, className = "leaflet-route-map", center }) {
  const pts = points.filter((p) => p.lat != null);
  return (
    <MapContainer center={center || BENGALURU_CENTER} zoom={11} scrollWheelZoom={false} className={className}>
      <TileLayer attribution={TILE_ATTR} url={TILE_URL} maxZoom={19}/>
      {pts.map((p) => (
        <CircleMarker key={p.key} center={[p.lat, p.lon]} radius={p.radius || 6}
          pathOptions={{ color: "#fff", weight: 2, fillColor: p.color || "#087f78", fillOpacity: 0.9 }}>
          <Popup>{p.label}</Popup>
        </CircleMarker>
      ))}
      {pts.length > 1 && <FitBounds points={pts.map((p) => [p.lat, p.lon])}/>}
    </MapContainer>
  );
}

// Several coloured routes with stop markers (e.g. company shuttle plans).
export function RoutesMap({ routes, points = [], className = "leaflet-route-map" }) {
  const all = [...routes.flatMap((r) => r.positions), ...points.map((p) => [p.lat, p.lon])];
  return (
    <MapContainer center={BENGALURU_CENTER} zoom={11} scrollWheelZoom={false} className={className}>
      <TileLayer attribution={TILE_ATTR} url={TILE_URL} maxZoom={19}/>
      {routes.map((r) => (
        <Polyline key={r.key} positions={r.positions} pathOptions={{ color: r.color, weight: 5, opacity: 0.85 }}>
          <Popup>{r.label}</Popup>
        </Polyline>
      ))}
      {points.map((p) => (
        <CircleMarker key={p.key} center={[p.lat, p.lon]} radius={p.radius || 6}
          pathOptions={{ color: "#fff", weight: 2, fillColor: p.color || "#087f78", fillOpacity: 0.95 }}>
          <Popup>{p.label}</Popup>
        </CircleMarker>
      ))}
      {all.length > 1 && <FitBounds points={all}/>}
    </MapContainer>
  );
}
