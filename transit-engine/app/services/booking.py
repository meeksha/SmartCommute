"""Where to book or pay for each part of a journey.

Only official apps and documented links (checked 20 Nov 2026). None of these apps
publish a deep link that pre-fills the trip, so they open at their home screen;
Google Maps' documented directions URL is pre-filled with the route's ends.

Sources:
- Namma Metro (BMRCL official app): play.google.com/store/apps/details?id=com.aum.nammametro
- Metro QR tickets on WhatsApp: +91 81055 56677 (BMRCL chatbot, send "Hi")
- Namma Yatri (Moving Tech): auto, cab and metro tickets
- Rapido: bike taxi, auto, cab
- Tummoc (Transhelp): BMTC daily / weekly / monthly passes; single tickets "coming soon"
- RailOne (CRIS): unreserved train tickets (replaced UTS on 1 Mar 2026)
- Google Maps URLs: developers.google.com/maps/documentation/urls/get-started
"""
from __future__ import annotations

from urllib.parse import urlencode

APPS = {
    "namma_metro": {"name": "Namma Metro (BMRCL)",
                    "android": "https://play.google.com/store/apps/details?id=com.aum.nammametro",
                    "ios": "https://apps.apple.com/in/app/namma-metro-bmrcl-official-app/id6740857835",
                    "web": "https://english.bmrc.co.in/"},
    "metro_whatsapp": {"name": "Metro QR ticket on WhatsApp",
                       "web": "https://wa.me/918105556677?text=Hi"},
    "namma_yatri": {"name": "Namma Yatri",
                    "android": "https://play.google.com/store/apps/details?id=in.juspay.nammayatri",
                    "ios": "https://apps.apple.com/in/app/id1637429831",
                    "web": "https://nammayatri.in/"},
    "rapido": {"name": "Rapido",
               "android": "https://play.google.com/store/apps/details?id=com.rapido.passenger",
               "web": "https://www.rapido.bike/"},
    "tummoc": {"name": "Tummoc (BMTC passes)",
               "android": "https://play.google.com/store/apps/details?id=org.transhelp.bykerr",
               "ios": "https://apps.apple.com/in/app/id1534144729"},
    "railone": {"name": "RailOne (Indian Railways)",
                "android": "https://play.google.com/store/apps/details?id=org.cris.aikyam",
                "ios": "https://apps.apple.com/in/app/railone/id6473384334"},
}

BIKE_TAXI_NOTE = ("Bike taxis are legally contested in Karnataka: the High Court lifted the ban in Jan 2026, "
                  "but the state's appeal is pending in the Supreme Court and enforcement drives continue.")


def _app(key: str, purpose: str, note: str | None = None) -> dict:
    a = APPS[key]
    return {"kind": "app", "provider": a["name"], "purpose": purpose, "android": a.get("android"),
            "ios": a.get("ios"), "web": a.get("web"), "prefilled": False, "note": note}


def maps_link(origin: dict, destination: dict, travelmode: str) -> dict:
    q = urlencode({"api": 1, "origin": f"{origin['lat']:.6f},{origin['lon']:.6f}",
                   "destination": f"{destination['lat']:.6f},{destination['lon']:.6f}", "travelmode": travelmode})
    return {"kind": "maps", "provider": "Google Maps", "purpose": "Open this route",
            "web": f"https://www.google.com/maps/dir/?{q}", "prefilled": True, "note": None}


def booking_links(option: dict) -> list[dict]:
    legs = option.get("legs") or []
    if not legs:
        return []
    types = [l.get("type") for l in legs]
    fam = option.get("family")
    out: list[dict] = []
    if "metro" in types:
        out.append(_app("namma_metro", "Metro QR ticket"))
        out.append(_app("metro_whatsapp", "Metro QR ticket", "Send \"Hi\" and pick your stations."))
    if "train" in types:
        out.append(_app("railone", "Unreserved train ticket",
                        "Buy an unreserved (general) ticket for the stations shown before boarding."))
    if "bus" in types:
        out.append(_app("tummoc", "BMTC daily / weekly / monthly pass",
                        "Single bus tickets are bought from the conductor on board."))
    if "auto" in types or fam == "auto":
        out.append(_app("namma_yatri", "Book the auto"))
        out.append(_app("rapido", "Book the auto"))
    if fam == "cab":
        out.append(_app("namma_yatri", "Book the cab"))
        out.append(_app("rapido", "Book the cab"))
    if fam == "two_wheeler":
        out.append(_app("rapido", "No two-wheeler of your own? Bike taxi", BIKE_TAXI_NOTE))
    if fam == "carpool":
        out.append({"kind": "internal", "provider": "SmartCommute", "purpose": "Send a carpool request",
                    "page": "Carpooling", "prefilled": True, "note": None})
    first, last = legs[0].get("from") or {}, legs[-1].get("to") or {}
    if {"lat", "lon"} <= set(first) and {"lat", "lon"} <= set(last):
        mode = ("transit" if any(t in ("bus", "metro", "train") for t in types) else
                "walking" if fam == "walk" else "bicycling" if fam == "bicycle" else "driving")
        out.append(maps_link(first, last, mode))
    return out
