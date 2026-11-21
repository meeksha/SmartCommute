"""Request schemas (validated at the API boundary)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

BENGALURU_BBOX = (12.6, 13.45, 76.95, 78.0)  # lat_min, lat_max, lon_min, lon_max (Bengaluru + Tumakuru)


class Point(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    accuracy_m: Optional[float] = Field(None, ge=0, description="GPS accuracy reported by the browser")
    label: Optional[str] = None

    @field_validator("lon")
    @classmethod
    def _in_bengaluru(cls, v, info):
        lat = info.data.get("lat")
        lo, hi, wlo, whi = BENGALURU_BBOX
        if lat is not None and not (lo <= lat <= hi and wlo <= v <= whi):
            raise ValueError("Location must be within the Bengaluru-Tumakuru region (transit data coverage).")
        return v


class Vehicle(BaseModel):
    type: Literal["car", "two_wheeler"] = "car"
    fuel_type: Literal["petrol", "diesel", "cng", "lpg", "e20", "electric", "ev", "hybrid"] = "petrol"
    efficiency: Optional[float] = Field(None, gt=0, description="km/L, km/kg, or kWh/km for EVs")
    seats: Optional[int] = Field(None, ge=1, le=8)
    label: Optional[str] = None


class Preferences(BaseModel):
    profile: Optional[Literal["balanced", "green_first", "fastest", "cheapest", "comfort"]] = None
    max_walking_minutes: Optional[float] = Field(None, gt=0, le=60)
    max_transfers: Optional[int] = Field(None, ge=0, le=5)
    avoid_modes: Optional[list[Literal["metro", "bus", "bus_metro", "carpool", "walk", "auto", "cab",
                                       "two_wheeler", "car", "bicycle", "metro_combo"]]] = None
    usual_mode: Optional[Literal["driving", "carpool", "transit", "twoWheeler", "bicycling", "walking"]] = None
    owns_car: Optional[bool] = None
    carpool_willing: Optional[bool] = None


class Weights(BaseModel):
    emissions: float = Field(0.25, ge=0)
    duration: float = Field(0.30, ge=0)
    cost: float = Field(0.20, ge=0)
    walking: float = Field(0.10, ge=0)
    transfers: float = Field(0.07, ge=0)
    uncertainty: float = Field(0.08, ge=0)


class RecommendationRequest(BaseModel):
    origin: Point
    destination: Optional[Point] = None
    destination_office_id: Optional[str] = Field(None, description="Use an office preset from /api/meta")
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD; default today (IST)")
    time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$", description="HH:MM; default now (IST)")
    user_id: Optional[str] = None
    profile: Optional[Literal["balanced", "green_first", "fastest", "cheapest", "comfort"]] = None
    weights: Optional[Weights] = None
    preferences: Optional[Preferences] = None
    vehicle: Optional[Vehicle] = None


class ChoiceRequest(BaseModel):
    option_id: str
    user_id: Optional[str] = None
    save_trip: bool = False
    origin_label: Optional[str] = Field(None, max_length=512)
    destination_label: Optional[str] = Field(None, max_length=512)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = Field(None, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False


class UserCreate(BaseModel):
    id: Optional[str] = Field(None, max_length=64)
    name: Optional[str] = Field(None, max_length=120)
    employee_id: Optional[str] = None
    preferences: Optional[Preferences] = None
    vehicle: Optional[Vehicle] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    employee_id: Optional[str] = Field(None, max_length=64)
    preferences: Optional[Preferences] = None
    vehicle: Optional[Vehicle] = None
    reset_learning: bool = False


class TwinScenario(BaseModel):
    metro_shift_pct: float = Field(0, ge=0, le=100)
    carpool_pct: float = Field(0, ge=0, le=100)
    shuttle_count: int = Field(0, ge=0, le=200)
    shuttle_capacity: int = Field(40, ge=8, le=60)
    ride_hailing_price_change_pct: float = Field(0, ge=-50, le=100)
    transit_fare_change_pct: float = Field(0, ge=-100, le=100)
    rain: bool = False
    office_zone: Optional[str] = None          # office preset id or name
    headcount: int = Field(2000, ge=50, le=20000)
    start_time: str = Field("09:30", pattern=r"^\d{2}:\d{2}$")
    max_carpool_occupancy: int = Field(4, ge=2, le=7)
    include_employees: bool = False


class EmissionRequest(BaseModel):
    distance_km: float = Field(..., gt=0, le=200)
    mode: Literal["car", "two_wheeler", "auto", "cab", "bus", "metro", "carpool", "walk"]
    occupancy: float = Field(1, ge=1, le=8)
    vehicle: Optional[Vehicle] = None


class TripSegmentIn(BaseModel):
    mode: str = Field(max_length=24)
    label: Optional[str] = Field(default=None, max_length=160)
    color: Optional[str] = Field(default=None, max_length=16)
    positions: list[tuple[float, float]] = Field(default_factory=list, max_length=3000)


class TripIn(BaseModel):
    origin: str = Field(min_length=1, max_length=512)
    destination: str = Field(min_length=1, max_length=512)
    origin_lat: float = Field(ge=-90, le=90)
    origin_lng: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lng: float = Field(ge=-180, le=180)
    mode: str = Field(min_length=1, max_length=128)
    distance_km: float = Field(ge=0)
    time_minutes: int = Field(ge=0)
    cost: Optional[float] = Field(default=None, ge=0)
    co2_kg: float = Field(ge=0)
    segments: list[TripSegmentIn] = Field(default_factory=list, max_length=20)


class GoogleLogin(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)


class CarpoolProfileIn(BaseModel):
    available: bool = True
    role: Literal["driver", "rider", "either"] = "either"
    seats: int = Field(1, ge=1, le=6)
    phone: Optional[str] = Field(None, pattern=r"^\+?[0-9 ()-]{7,20}$")
    share_phone: bool = False
    note: Optional[str] = Field(None, max_length=280)
    save_commute_from_last_trip: bool = False


class TripSpec(BaseModel):
    """A specific planned trip (from the Dashboard) to carpool on."""
    olat: float = Field(ge=12.6, le=13.45)
    olon: float = Field(ge=76.95, le=78.0)
    dlat: float = Field(ge=12.6, le=13.45)
    dlon: float = Field(ge=76.95, le=78.0)
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    olabel: Optional[str] = Field(None, max_length=200)
    dlabel: Optional[str] = Field(None, max_length=200)


class CarpoolRequestIn(BaseModel):
    to_ref: str = Field(min_length=8, max_length=64)
    message: Optional[str] = Field(None, max_length=500)
    trip: Optional[TripSpec] = None


class CarpoolRespond(BaseModel):
    accept: bool
