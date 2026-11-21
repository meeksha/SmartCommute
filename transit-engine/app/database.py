"""Persistence: accounts/sessions, user profiles, saved trips, choices, logs.

PostgreSQL is the production database. Configure it with DATABASE_URL, e.g.
    postgresql+psycopg://postgres:postgres@localhost:5432/smartcommute
If DATABASE_URL is not set, that local default is used. SQLite still works
for tests (DATABASE_URL=sqlite:///path.db).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (JSON, Column, DateTime, Float, Integer, String, Text, create_engine,
                        ForeignKey)
from sqlalchemy.orm import declarative_base, sessionmaker

DEFAULT_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/smartcommute"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_URL)
if DATABASE_URL.startswith("postgres://"):            # Heroku-style URL
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(String(254), primary_key=True)
    name = Column(String(120))
    employee_id = Column(String(32), nullable=True)
    preferences = Column(JSON, default=dict)     # stated preferences / constraints
    vehicle = Column(JSON, nullable=True)        # own vehicle profile
    weights = Column(JSON, nullable=True)        # learned ranking weights
    choice_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class TripChoice(Base):
    __tablename__ = "trip_choices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(254), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_id = Column(String(64), index=True)
    chosen_option_id = Column(String(64))
    chosen_mode = Column(String(64))
    options = Column(JSON)          # feature vectors of everything shown
    context = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=_now)


class RecommendationLog(Base):
    __tablename__ = "recommendation_log"
    request_id = Column(String(64), primary_key=True)
    user_id = Column(String(254), nullable=True, index=True)
    request = Column(JSON)
    options = Column(JSON)          # compact option features for later choice logging
    recommended_option_id = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=_now)


class UserAccount(Base):
    """Login identity. The email doubles as the users.id of the commute profile."""
    __tablename__ = "user_accounts"
    email = Column(String(254), primary_key=True)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    # "employee" (default) or "admin" (sees company-wide pages: Digital Twin, Incentives, Shuttles, Analytics)
    role = Column(String(16), nullable=False, default="employee", server_default="employee")


ROLES = ("employee", "admin")


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash = Column(String(64), primary_key=True)
    user_email = Column(String(254), ForeignKey("user_accounts.email", ondelete="CASCADE"), index=True,
                        nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class SavedTrip(Base):
    __tablename__ = "saved_trips"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_email = Column(String(254), ForeignKey("user_accounts.email", ondelete="CASCADE"), index=True,
                        nullable=False)
    request_id = Column(String(64), nullable=True)
    option_id = Column(String(64), nullable=True)
    family = Column(String(32), nullable=True)
    origin = Column(String(512), nullable=False)
    destination = Column(String(512), nullable=False)
    origin_lat = Column(Float, nullable=False)
    origin_lng = Column(Float, nullable=False)
    destination_lat = Column(Float, nullable=False)
    destination_lng = Column(Float, nullable=False)
    mode = Column(String(128), nullable=False)
    distance_km = Column(Float, nullable=False)
    time_minutes = Column(Integer, nullable=False)
    cost = Column(Float, nullable=True)
    co2_kg = Column(Float, nullable=False)
    co2_saved_vs_drive_kg = Column(Float, nullable=True)
    money_saved_vs_drive_inr = Column(Float, nullable=True)
    segments = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)


class CarpoolRequest(Base):
    """A carpool request between two registered users. Contact details are only
    revealed to both sides once the recipient accepts."""
    __tablename__ = "carpool_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    from_email = Column(String(254), ForeignKey("user_accounts.email", ondelete="CASCADE"), index=True, nullable=False)
    to_email = Column(String(254), ForeignKey("user_accounts.email", ondelete="CASCADE"), index=True, nullable=False)
    message = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="pending")   # pending|accepted|declined|cancelled
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    responded_at = Column(DateTime(timezone=True), nullable=True)


def init_db():
    if DATABASE_URL.startswith("sqlite"):
        Path(DATABASE_URL.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _migrate()


def _migrate():
    """Add columns introduced after a database was first created (create_all doesn't alter tables)."""
    from sqlalchemy import inspect, text
    cols = {c["name"] for c in inspect(engine).get_columns("user_accounts")}
    if "role" not in cols:
        with engine.begin() as con:
            con.execute(text("ALTER TABLE user_accounts ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'employee'"))
