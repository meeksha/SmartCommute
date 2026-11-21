from uuid import uuid4


def build_journey(
    mode,
    duration_minutes,
    legs=None,
    walking_distance_m=None,
    distance_km=None,
    fare=None,
    emissions=None,
    transfers=None,
    data_sources=None,
    limitations=None,
    raw_details=None,
):
    """
    Convert a transport option into a common journey representation.

    Missing measurements remain None. Original planner output is
    preserved in raw_details.
    """

    if not mode:
        raise ValueError("Journey mode is required.")

    if duration_minutes is None or float(duration_minutes) < 0:
        raise ValueError("A valid journey duration is required.")

    if walking_distance_m is not None and walking_distance_m < 0:
        raise ValueError("Walking distance cannot be negative.")

    if distance_km is not None and distance_km < 0:
        raise ValueError("Journey distance cannot be negative.")

    if transfers is not None and transfers < 0:
        raise ValueError("Transfers cannot be negative.")

    return {
        "journey_id": str(uuid4()),
        "mode": mode,
        "legs": legs or [],
        "duration_minutes": round(float(duration_minutes), 1),
        "walking_distance_m": walking_distance_m,
        "distance_km": distance_km,
        "fare": fare,
        "emissions": emissions,
        "transfers": transfers,
        "data_sources": data_sources or [],
        "limitations": limitations or [],
        "raw_details": raw_details or {},
    }


def validate_journey(journey):
    """Check that a journey follows the common schema."""

    required_fields = [
        "journey_id",
        "mode",
        "legs",
        "duration_minutes",
        "walking_distance_m",
        "distance_km",
        "fare",
        "emissions",
        "transfers",
        "data_sources",
        "limitations",
        "raw_details",
    ]

    missing = [
        field for field in required_fields
        if field not in journey
    ]

    if missing:
        return {
            "status": "invalid",
            "missing_fields": missing,
        }

    if not isinstance(journey["legs"], list):
        return {
            "status": "invalid",
            "message": "Legs must be a list.",
        }

    return {
        "status": "success",
        "message": "Journey schema is valid.",
    }
