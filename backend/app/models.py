"""Normalized flight state.

OpenSky returns each aircraft as a 17-element "state vector" array. We keep only
the fields the app needs and give them names, so the rest of the codebase never
deals with magic indices.

State-vector index reference (OpenSky /states/all):
    0  icao24              9  velocity (m/s)
    1  callsign           10  true_track (deg, clockwise from north)
    2  origin_country     11  vertical_rate (m/s)
    3  time_position      12  sensors
    4  last_contact       13  geo_altitude (m)
    5  longitude (deg)    14  squawk
    6  latitude (deg)     15  spi
    7  baro_altitude (m)  16  position_source
    8  on_ground
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Explicit, named indices into OpenSky's state-vector array.
IDX_ICAO24 = 0
IDX_CALLSIGN = 1
IDX_ORIGIN_COUNTRY = 2
IDX_LAST_CONTACT = 4
IDX_LONGITUDE = 5
IDX_LATITUDE = 6
IDX_ON_GROUND = 8
IDX_VELOCITY = 9
IDX_TRUE_TRACK = 10
IDX_VERTICAL_RATE = 11
IDX_GEO_ALTITUDE = 13


class FlightState(BaseModel):
    icao24: str
    callsign: str | None = None
    origin_country: str | None = None
    longitude: float
    latitude: float
    geo_altitude: float | None = None  # meters
    on_ground: bool = False
    velocity: float | None = None  # m/s
    true_track: float | None = None  # degrees, clockwise from north
    vertical_rate: float | None = None  # m/s
    last_contact: int | None = None  # unix seconds

    @classmethod
    def from_state_vector(cls, sv: list[Any]) -> "FlightState | None":
        """Build a FlightState from one OpenSky state-vector row.

        Returns None if the row lacks a usable position (can't be mapped).
        """
        lon = sv[IDX_LONGITUDE]
        lat = sv[IDX_LATITUDE]
        if lon is None or lat is None:
            return None

        callsign = sv[IDX_CALLSIGN]
        return cls(
            icao24=sv[IDX_ICAO24],
            callsign=callsign.strip() if isinstance(callsign, str) else None,
            origin_country=sv[IDX_ORIGIN_COUNTRY],
            longitude=lon,
            latitude=lat,
            geo_altitude=sv[IDX_GEO_ALTITUDE],
            on_ground=bool(sv[IDX_ON_GROUND]),
            velocity=sv[IDX_VELOCITY],
            true_track=sv[IDX_TRUE_TRACK],
            vertical_rate=sv[IDX_VERTICAL_RATE],
            last_contact=sv[IDX_LAST_CONTACT],
        )
