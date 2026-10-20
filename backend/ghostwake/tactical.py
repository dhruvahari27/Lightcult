"""Tactical Intercept Calculator for Coast Guard / Maritime Enforcement.

Calculates time, heading, and rendezvous coordinates for patrol vessels
intercepting moving or dark targets before they cross boundary lines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from ghostwake.geo import (
    KM_PER_NM,
    bearing,
    destination,
    distance_to_polyline_km,
    haversine_km,
    side_of_polyline,
)
from ghostwake.zones import IMBL, INDIAN_SIDE_REF

# Strategic Indian Coast Guard (ICGS) and Naval stations in the Palk Bay / Gulf of Mannar region.
PATROL_BASES: dict[str, dict[str, object]] = {
    "ICGS Mandapam": {
        "lat": 9.278,
        "lon": 79.125,
        "description": "Forward Operating Base, Palk Bay & Gulf of Mannar",
        "asset": "Fast Interceptor Craft (FIC)",
        "default_speed_knots": 32.0,
    },
    "ICGS Thoothukudi": {
        "lat": 8.755,
        "lon": 78.195,
        "description": "Coast Guard District Headquarters No. 16, Gulf of Mannar",
        "asset": "Offshore Patrol Vessel (OPV)",
        "default_speed_knots": 26.0,
    },
    "ICGS Karaikal": {
        "lat": 10.925,
        "lon": 79.838,
        "description": "Coast Guard Station, Coromandel Coast / North Palk Strait",
        "asset": "Fast Patrol Vessel (FPV)",
        "default_speed_knots": 30.0,
    },
    "ICGS Vizhinjam": {
        "lat": 8.370,
        "lon": 76.980,
        "description": "Coast Guard Station, Southern tip & Wadge Bank",
        "asset": "Fast Interceptor Boat (IB)",
        "default_speed_knots": 35.0,
    },
    "Pamban Naval Detachment": {
        "lat": 9.278,
        "lon": 79.218,
        "description": "Pamban Pass surveillance post",
        "asset": "Immediate Support Vessel (ISV)",
        "default_speed_knots": 28.0,
    },
}


@dataclass
class InterceptResult:
    possible: bool
    patrol_base: str
    patrol_base_lat: float
    patrol_base_lon: float
    patrol_speed_knots: float
    target_lat: float
    target_lon: float
    target_speed_knots: float
    target_heading_deg: float
    time_minutes: float | None = None
    intercept_lat: float | None = None
    intercept_lon: float | None = None
    patrol_bearing_deg: float | None = None
    distance_km: float | None = None
    distance_nm: float | None = None
    imbl_status: Literal["indian_waters", "near_imbl", "crossed_imbl"] | None = None
    imbl_distance_km: float | None = None
    tactical_summary: str = ""


def _to_local_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Equirectangular projection around (lat0, lon0) in kilometers."""
    earth_radius_km = 6371.0088
    x = math.radians(lon - lon0) * math.cos(math.radians(lat0)) * earth_radius_km
    y = math.radians(lat - lat0) * earth_radius_km
    return x, y


def _from_local_xy(x: float, y: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Inverse equirectangular projection to (lat, lon)."""
    earth_radius_km = 6371.0088
    lat = lat0 + math.degrees(y / earth_radius_km)
    lon = lon0 + math.degrees(x / (earth_radius_km * math.cos(math.radians(lat0))))
    return lat, lon


def calculate_intercept(
    target_lat: float,
    target_lon: float,
    target_speed_knots: float = 0.0,
    target_heading_deg: float = 0.0,
    patrol_base_name: str = "ICGS Mandapam",
    custom_patrol_lat: float | None = None,
    custom_patrol_lon: float | None = None,
    patrol_speed_knots: float = 30.0,
) -> InterceptResult:
    """Calculate the optimal rendezvous coordinates, time, and heading for a patrol vessel to intercept a target."""
    if custom_patrol_lat is not None and custom_patrol_lon is not None:
        p_lat, p_lon = custom_patrol_lat, custom_patrol_lon
        base_name = patrol_base_name or "Custom Launch Point"
    elif patrol_base_name in PATROL_BASES:
        base_data = PATROL_BASES[patrol_base_name]
        p_lat = float(base_data["lat"])
        p_lon = float(base_data["lon"])
        base_name = patrol_base_name
    else:
        # Default fallback
        base_name = "ICGS Mandapam"
        base_data = PATROL_BASES[base_name]
        p_lat = float(base_data["lat"])
        p_lon = float(base_data["lon"])

    # Convert speeds to km/h
    v_target_kmh = max(0.0, target_speed_knots) * KM_PER_NM
    v_patrol_kmh = max(1.0, patrol_speed_knots) * KM_PER_NM

    # Origin at target position (0, 0)
    tx0, ty0 = 0.0, 0.0
    px0, py0 = _to_local_xy(p_lat, p_lon, target_lat, target_lon)

    # Initial distance from patrol to target
    d_initial = math.hypot(tx0 - px0, ty0 - py0)

    # Target velocity vector (heading is degrees clockwise from North / +Y axis)
    th_rad = math.radians(target_heading_deg % 360)
    v_tx = v_target_kmh * math.sin(th_rad)
    v_ty = v_target_kmh * math.cos(th_rad)

    # Relative position vector from patrol to target
    dx = tx0 - px0
    dy = ty0 - py0

    # Quadratic equation for intercept time t (hours):
    # (dx + v_tx * t)^2 + (dy + v_ty * t)^2 = (v_patrol_kmh * t)^2
    # Expanding gives: A * t^2 + B * t + C = 0
    a = (v_tx**2 + v_ty**2) - (v_patrol_kmh**2)
    b = 2.0 * (dx * v_tx + dy * v_ty)
    c = dx**2 + dy**2

    time_hours: float | None = None

    if abs(a) < 1e-6:
        # v_target == v_patrol
        if b < 0:
            time_hours = -c / b
    else:
        discriminant = b**2 - 4.0 * a * c
        if discriminant >= 0:
            sqrt_disc = math.sqrt(discriminant)
            t1 = (-b - sqrt_disc) / (2.0 * a)
            t2 = (-b + sqrt_disc) / (2.0 * a)
            valid_times = [t for t in (t1, t2) if t > 0]
            if valid_times:
                time_hours = min(valid_times)

    # If stationary target or no moving intercept found within reasonable tolerance
    if time_hours is None:
        if v_target_kmh < 1.0:
            time_hours = d_initial / v_patrol_kmh
        else:
            return InterceptResult(
                possible=False,
                patrol_base=base_name,
                patrol_base_lat=p_lat,
                patrol_base_lon=p_lon,
                patrol_speed_knots=patrol_speed_knots,
                target_lat=target_lat,
                target_lon=target_lon,
                target_speed_knots=target_speed_knots,
                target_heading_deg=target_heading_deg,
                tactical_summary=(
                    f"Intercept impossible from {base_name} at {patrol_speed_knots:.1f} kn. "
                    f"Target is moving too fast ({target_speed_knots:.1f} kn, heading {target_heading_deg:.0f}°) "
                    f"away from the patrol vector."
                ),
            )

    time_minutes = time_hours * 60.0

    # Compute rendezvous position in local coordinates, then project back to lat/lon
    rendezvous_x = tx0 + v_tx * time_hours
    rendezvous_y = ty0 + v_ty * time_hours
    r_lat, r_lon = _from_local_xy(rendezvous_x, rendezvous_y, target_lat, target_lon)

    # Calculate patrol bearing and travel distance
    p_bearing = bearing(p_lat, p_lon, r_lat, r_lon)
    dist_km = haversine_km(p_lat, p_lon, r_lat, r_lon)
    dist_nm = dist_km / KM_PER_NM

    # Check position relative to IMBL
    imbl_dist = distance_to_polyline_km(r_lat, r_lon, IMBL)
    ref_side = side_of_polyline(INDIAN_SIDE_REF[0], INDIAN_SIDE_REF[1], IMBL)
    r_side = side_of_polyline(r_lat, r_lon, IMBL)

    if r_side != ref_side:
        imbl_status: Literal["indian_waters", "near_imbl", "crossed_imbl"] = "crossed_imbl"
        status_text = f"CRITICAL: Intercept occurs {imbl_dist:.1f} km across the IMBL in Sri Lankan waters!"
    elif imbl_dist <= 5.0:
        imbl_status = "near_imbl"
        status_text = f"CAUTION: Intercept is within {imbl_dist:.1f} km of the IMBL."
    else:
        imbl_status = "indian_waters"
        status_text = f"FEASIBLE: Intercept is securely inside Indian waters ({imbl_dist:.1f} km from IMBL)."

    summary = (
        f"{status_text} "
        f"{base_name} asset at {patrol_speed_knots:.0f} kn can intercept in "
        f"{time_minutes:.1f} minutes ({dist_nm:.1f} NM, heading {p_bearing:.0f}°). "
        f"Rendezvous coordinates: {r_lat:.4f}° N, {r_lon:.4f}° E."
    )

    return InterceptResult(
        possible=True,
        patrol_base=base_name,
        patrol_base_lat=round(p_lat, 4),
        patrol_base_lon=round(p_lon, 4),
        patrol_speed_knots=round(patrol_speed_knots, 1),
        target_lat=round(target_lat, 4),
        target_lon=round(target_lon, 4),
        target_speed_knots=round(target_speed_knots, 1),
        target_heading_deg=round(target_heading_deg, 1),
        time_minutes=round(time_minutes, 1),
        intercept_lat=round(r_lat, 4),
        intercept_lon=round(r_lon, 4),
        patrol_bearing_deg=round(p_bearing, 1),
        distance_km=round(dist_km, 2),
        distance_nm=round(dist_nm, 2),
        imbl_status=imbl_status,
        imbl_distance_km=round(imbl_dist, 2),
        tactical_summary=summary,
    )
