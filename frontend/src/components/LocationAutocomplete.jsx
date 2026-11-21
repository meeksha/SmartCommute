import { useEffect, useState } from "react";
import { MapPin, Building2, TrainFront, Bus } from "lucide-react";
import { api } from "../lib/api";

const KIND_ICON = { office: Building2, metro_station: TrainFront, rail_station: TrainFront, bus_stop: Bus };
const KIND_LABEL = { office: "Office zone", metro_station: "Namma Metro station", rail_station: "Railway station", bus_stop: "BMTC stop", osm: "OpenStreetMap" };

// Place search goes through the backend: OpenStreetMap Nominatim when the
// server is online, plus offices, Metro stations and BMTC stops from the GTFS
// data, so search still works offline.
export default function LocationAutocomplete({ id, label, value, placeholder, onChange, onSelect, action }) {
  const [suggestions, setSuggestions] = useState([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [focused, setFocused] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");

  useEffect(() => {
    if (!focused || value.trim().length < 2) {
      setSuggestions([]);
      setSearchError("");
      setSearching(false);
      return undefined;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setSearching(true);
      setSearchError("");
      try {
        const { results } = await api(`/api/places/search?${new URLSearchParams({ q: value.trim(), limit: "8" })}`,
          { signal: controller.signal });
        setSuggestions(results.map((r, i) => ({
          id: `${r.kind}-${i}-${r.lat}`,
          name: r.name,
          detail: r.kind === "osm" ? (r.label || "").split(",").slice(1, 3).join(",").trim() || "Bengaluru region" : KIND_LABEL[r.kind],
          label: r.name,
          kind: r.kind,
          lat: r.lat,
          lng: r.lon,
        })));
        setActiveIndex(-1);
      } catch (error) {
        if (error.name !== "AbortError") {
          setSuggestions([]);
          setSearchError(error.message || "Place suggestions could not be loaded.");
        }
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }, 450);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [focused, value]);

  function choose(place) {
    onSelect(place);
    setSuggestions([]);
    setFocused(false);
    setActiveIndex(-1);
  }

  function handleKeyDown(event) {
    if (event.key === "ArrowDown" && suggestions.length) {
      event.preventDefault();
      setActiveIndex((i) => (i + 1) % suggestions.length);
    } else if (event.key === "ArrowUp" && suggestions.length) {
      event.preventDefault();
      setActiveIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      choose(suggestions[activeIndex]);
    } else if (event.key === "Escape") {
      setFocused(false);
      setSuggestions([]);
    }
  }

  const showDropdown = focused && (searching || searchError || suggestions.length > 0 || value.trim().length >= 2);

  return (
    <div className="planner-field">
      <label htmlFor={id} className="planner-field-label">
        <span><i className={id === "commute-origin" ? "origin-dot" : "destination-dot"}/>{label}</span>
      </label>
      <div className="place-autocomplete">
        <div className="planner-field-input">
          <input
            id={id}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={showDropdown}
            aria-controls={`${id}-suggestions`}
            aria-activedescendant={activeIndex >= 0 ? `${id}-option-${activeIndex}` : undefined}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setTimeout(() => setFocused(false), 120)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            autoComplete="off"
          />
          {action}
        </div>
        {showDropdown && (
          <div className="place-suggestions" id={`${id}-suggestions`} role="listbox" aria-label={`${label} suggestions`}>
            {searching && <div className="place-suggestion-status">Searching Bengaluru places, Metro stations and bus stops…</div>}
            {searchError && <div className="place-suggestion-status place-suggestion-error">{searchError}</div>}
            {!searching && !searchError && suggestions.map((place, index) => {
              const Icon = KIND_ICON[place.kind] || MapPin;
              return (
                <button type="button" id={`${id}-option-${index}`} key={place.id} role="option"
                  aria-selected={index === activeIndex}
                  className={`place-suggestion ${index === activeIndex ? "active" : ""}`}
                  onMouseDown={(e) => e.preventDefault()} onClick={() => choose(place)}>
                  <Icon size={15}/>
                  <span><strong>{place.name}</strong><small>{place.detail}</small></span>
                </button>
              );
            })}
            {!searching && !searchError && suggestions.length === 0 && (
              <div className="place-suggestion-status">No match. Try an area, landmark, Metro station or bus stop.</div>
            )}
            <div className="place-suggestion-credit">OpenStreetMap · BMTC & Namma Metro GTFS</div>
          </div>
        )}
      </div>
    </div>
  );
}
