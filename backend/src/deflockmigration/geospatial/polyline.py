"""Google encoded polyline with 6 decimal digits (Valhalla's native shape encoding)."""

from __future__ import annotations


def decode_polyline6(encoded: str, precision: float = 1e6) -> list[tuple[float, float]]:
    """Return a list of (lat, lon) tuples."""
    index, lat, lon, coords = 0, 0, 0, []
    length = len(encoded)
    while index < length:
        for which in (0, 1):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if which == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / precision, lon / precision))
    return coords


def encode_polyline6(coords: list[tuple[float, float]], precision: float = 1e6) -> str:
    """Encode (lat, lon) tuples."""
    out: list[str] = []
    prev_lat = prev_lon = 0
    for lat, lon in coords:
        ilat, ilon = round(lat * precision), round(lon * precision)
        for value, prev in ((ilat, prev_lat), (ilon, prev_lon)):
            delta = value - prev
            delta = ~(delta << 1) if delta < 0 else (delta << 1)
            while delta >= 0x20:
                out.append(chr((0x20 | (delta & 0x1F)) + 63))
                delta >>= 5
            out.append(chr(delta + 63))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)


def to_geojson_linestring(coords: list[tuple[float, float]]) -> dict:
    return {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in coords]}
