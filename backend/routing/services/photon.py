"""Photon (Komoot) geocoding client, keyless public server.

Docs: https://github.com/komoot/photon#search-api  (`q`, `limit`, `lang`; GeoJSON FeatureCollection,
feature `properties`: name, street, housenumber, city, state, country, countrycode, type).
"""

from __future__ import annotations

import hashlib

import httpx
from django.conf import settings
from django.core.cache import cache

from .errors import UpstreamError

USER_AGENT = "spotter-weather-truck-routing/1.0 (assessment demo)"
COUNTRIES = {"US", "CA", "MX"}
CACHE_TTL_S = 3600
PLACE_TYPES = {"country", "state", "county", "city"}  # features that are themselves a place


US_STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def search_url() -> str:
    return settings.PHOTON_URL.rstrip("/") + "/api/"


def _label(props: dict) -> str:
    name = props.get("name")
    if props.get("type") in PLACE_TYPES:
        parts = [name]
    else:
        street = props.get("street")
        if street and props.get("housenumber") and not name:
            street = f"{props['housenumber']} {street}"
        parts = [name, street, props.get("city")]
    state = props.get("state")
    if (props.get("countrycode") or "").upper() == "US":
        state = US_STATES.get(state, state)
    parts += [state, props.get("country")]
    out: list[str] = []
    for p in parts:
        if p and (not out or out[-1] != p):
            out.append(p)
    return ", ".join(out)


def geocode(q: str) -> list[dict]:
    key = "photon:" + hashlib.sha1(q.strip().lower().encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = httpx.get(
            search_url(),
            params={"q": q, "limit": 8, "lang": "en"},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise UpstreamError(f"Photon returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise UpstreamError(f"Photon request failed: {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise UpstreamError("Photon returned invalid JSON") from exc

    results = []
    seen: set[str] = set()
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if (props.get("countrycode") or "").upper() not in COUNTRIES or len(coords) < 2:
            continue
        label = _label(props)
        if label and label not in seen:  # Photon returns near-duplicate rows (e.g. two "Dallas, TX")
            seen.add(label)
            results.append({"label": label, "lon": coords[0], "lat": coords[1]})
    results = results[:5]
    cache.set(key, results, CACHE_TTL_S)
    return results
