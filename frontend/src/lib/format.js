export function formatDuration(minutes) {
  if (minutes === null || minutes === undefined) return "—";
  const m = Math.round(minutes);
  const hours = Math.floor(m / 60);
  const rest = m % 60;
  return hours ? `${hours}h ${rest}m` : `${m} min`;
}

export function formatRupees(amount) {
  return amount === null || amount === undefined ? "Not available" : `₹${Math.round(amount).toLocaleString("en-IN")}`;
}

// A cost is shown as a range when the backend gives a meaningfully different low/high.
export function formatCost(cost) {
  if (!cost || cost.amount_inr === null || cost.amount_inr === undefined) return "Fare unavailable";
  const { low_inr: lo, high_inr: hi, amount_inr: amt } = cost;
  if (lo !== null && hi !== null && lo !== undefined && hi !== undefined && Math.round(hi) - Math.round(lo) >= 2) {
    return `₹${Math.round(lo)}–${Math.round(hi)}`;
  }
  return formatRupees(amt);
}

export function formatKg(kg, digits = 2) {
  return kg === null || kg === undefined ? "—" : `${Number(kg).toFixed(digits)} kg`;
}

// CO2e with its uncertainty range when confidence is not high.
export function formatCo2(em) {
  if (!em) return "—";
  const est = em.estimate_kg_co2e;
  if (em.confidence !== "high" && em.upper_kg_co2e - em.lower_kg_co2e >= 0.02) {
    return `${est.toFixed(2)} kg (${em.lower_kg_co2e.toFixed(2)}–${em.upper_kg_co2e.toFixed(2)})`;
  }
  return `${est.toFixed(2)} kg`;
}

export const FAMILY_ICON_KEY = {
  metro: "metro", metro_combo: "metro", bus: "bus", bus_metro: "transit", carpool: "carpool", walk: "walk", bicycle: "bike",
  auto: "auto", cab: "car", two_wheeler: "bike", car: "car", train: "metro",
};

export const LEG_COLORS = {
  walk: "#84959a", bus: "#d9480f", metro: "#8257bd", car: "#126f99", cab: "#126f99", auto: "#c99700",
  two_wheeler: "#0b7285", carpool: "#2b8a3e", bicycle: "#2f9e44", train: "#1864ab",
};

export const MODE_LABELS = {
  walk: "Walk", bicycle: "Cycle", two_wheeler: "Two-wheeler", car: "Drive alone", carpool: "Carpool",
  auto: "Auto", cab: "Cab", bus: "BMTC bus", metro: "Metro", bus_metro: "Bus + Metro",
  metro_combo: "Metro + auto/feeder", train: "Train",
};
