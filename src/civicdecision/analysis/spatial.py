"""Dependency-light spatial calculations with explicit units."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_MEAN_RADIUS_KM = 6371.0088


def haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance in kilometres between two WGS84 coordinates."""

    latitude_delta = radians(latitude_b - latitude_a)
    longitude_delta = radians(longitude_b - longitude_a)
    latitude_a_rad = radians(latitude_a)
    latitude_b_rad = radians(latitude_b)
    haversine = sin(latitude_delta / 2) ** 2 + (
        cos(latitude_a_rad) * cos(latitude_b_rad) * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_MEAN_RADIUS_KM * asin(sqrt(haversine))
