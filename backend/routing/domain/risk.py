"""Weather risk classification. Pure functions, no Django / HTTP.

Levels: 0 Low, 1 Moderate, 2 High, 3 Severe, 4 No Travel.
Lower bounds are inclusive (wind 25 mph is Moderate). Upper edges of the
rain / snow "High-ish" bands are inclusive (rain 1.00 in/hr is still Severe).
"""

from __future__ import annotations

from dataclasses import dataclass

LEVEL_NAMES = ["Low", "Moderate", "High", "Severe", "No Travel"]


def wind_level(mph: float) -> int:
    if mph < 25:
        return 0
    if mph < 35:
        return 1
    if mph < 45:
        return 2
    if mph < 55:
        return 3
    return 4


def rain_level(in_hr: float) -> int:
    if in_hr < 0.10:
        return 0
    if in_hr < 0.25:
        return 1
    if in_hr < 0.50:
        return 2
    if in_hr <= 1.00:
        return 3
    return 4


def snow_level(in_hr: float) -> int:
    if in_hr < 0.5:
        return 0
    if in_hr < 1.0:
        return 1
    if in_hr < 2.0:
        return 2
    if in_hr <= 3.0:
        return 3
    return 4


def wind_level_with_load(mph: float, load_lb: float) -> int:
    """Wind level after applying the load rules."""
    level = wind_level(mph)
    if 45 <= mph < 55 and load_lb > 30_000:
        level = 4
    elif 35 <= mph < 45 and load_lb > 40_000:
        level = max(level, 3)
    return level


@dataclass(frozen=True)
class Risk:
    level: int
    wind: int  # wind level AFTER the load rule
    rain: int
    snow: int
    driver: str  # wind | rain | snow | load
    note: str


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Risk:
    raw_wind = wind_level(wind_mph)
    wind = wind_level_with_load(wind_mph, load_lb)
    rain = rain_level(rain_in_hr)
    snow = snow_level(snow_in_hr)
    level = max(wind, rain, snow)

    if wind == level and wind > raw_wind:
        driver = "load"
    elif wind == level:
        driver = "wind"
    elif rain == level:
        driver = "rain"
    else:
        driver = "snow"

    if driver == "load":
        detail = f"wind {wind_mph:.0f} mph × {load_lb:,.0f} lb"
    elif driver == "wind":
        detail = f"wind {wind_mph:.0f} mph"
    elif driver == "rain":
        detail = f"rain {rain_in_hr:.2f} in/hr"
    else:
        detail = f"snow {snow_in_hr:.2f} in/hr"
    return Risk(level, wind, rain, snow, driver, f"{LEVEL_NAMES[level]} — {detail}")


def weather_only_level(wind_mph: float, rain_in_hr: float, snow_in_hr: float) -> int:
    """Pure-weather level (no load) used by the heatmap."""
    return max(wind_level(wind_mph), rain_level(rain_in_hr), snow_level(snow_in_hr))
