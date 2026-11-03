"""Encoded-polyline decoding shared by the routing engines (Valhalla and OSRM use precision 6)."""

from __future__ import annotations


def decode_polyline6(encoded: str) -> list[list[float]]:
    """Decode an encoded polyline (precision 6, lat/lon order) into [[lon, lat], ...]."""
    coords: list[list[float]] = []
    index = lat = lon = 0
    n = len(encoded)
    while index < n:
        for axis in (0, 1):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coords.append([lon / 1e6, lat / 1e6])
    return coords
