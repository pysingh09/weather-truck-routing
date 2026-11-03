# API contract (backend ⇄ frontend) — source of truth

Base URL: `${VITE_API_URL}` (dev: `http://localhost:8000`). JSON only. Times are ISO-8601 UTC (`2026-11-04T14:00:00Z`). Distances are in **miles**, durations in **seconds**, coordinates are `[lon, lat]` (GeoJSON order).

Risk levels are ints: `0 Low · 1 Moderate · 2 High · 3 Severe · 4 No Travel`.
Colors (frontend `risk-colors.ts`): 0 `#22c55e`, 1 `#eab308`, 2 `#f97316`, 3 `#dc2626`, 4 `#7e22ce`.

## GET /api/geocode?q=<text>
Proxies HERE Autosuggest/Geocode so the key stays on the server.
```json
{ "results": [ { "label": "Chicago, IL, United States", "lon": -87.63, "lat": 41.88 } ] }
```
Returns at most 5 results, de-duplicated by `label`; US states are abbreviated (`Dallas, TX, United States`). If `q` has fewer than 3 characters, returns `{"results": []}`.

## POST /api/plan
Request:
```json
{
  "origin":      { "label": "Chicago, IL", "lon": -87.63, "lat": 41.88 },
  "destination": { "label": "Denver, CO",  "lon": -104.99, "lat": 39.74 },
  "departure": "2026-11-04T14:00:00Z",
  "load_lb": 38000,
  "interval_mi": 25
}
```
Validation errors return 400 `{"error": "...", "field": "..."}`:
- `interval_mi` must be one of 10, 25, 50.
- `load_lb` must be in 0–80000.
- `departure` must be between now−1 h and now+7 d.
- `origin` and `destination` must differ (within ~1 km), else 400 with `field: "destination"`.

Upstream failures return 502 `{"error": "..."}` (e.g. Open-Meteo 429 is retried twice, then reported as a rate-limit message).

Response 200:
```json
{
  "recommended_route_id": "r1",
  "all_no_travel": false,
  "routes": [
    {
      "id": "r0",
      "engine": "valhalla-truck",
      "rank": 2,
      "label": "Route A",
      "distance_mi": 1003.4,
      "duration_s": 54000,
      "arrival": "2026-11-05T05:00:00Z",
      "geometry": { "type": "LineString", "coordinates": [[-87.63, 41.88], "..."] },
      "summary": {
        "miles_by_level": { "0": 900.1, "1": 80.0, "2": 23.3, "3": 0, "4": 0 },
        "severe_mi": 0, "high_mi": 23.3, "no_travel_mi": 0,
        "avg_risk": 0.18,
        "max_level": 2,
        "has_no_travel": false
      },
      "reason": "Recommended: 0 severe mi, fewest high-risk miles (23 mi vs 61 mi).",
      "checkpoints": [
        {
          "idx": 0, "mile": 0.0, "lon": -87.63, "lat": 41.88,
          "eta": "2026-11-04T14:00:00Z",
          "weather": { "wind_mph": 18.2, "gust_mph": 27.0, "rain_in_hr": 0.0, "snow_in_hr": 0.0 },
          "level": 0,
          "levels": { "wind": 0, "rain": 0, "snow": 0 },
          "driver": "wind",
          "note": "Low — wind 18 mph"
        }
      ],
      "segments": [
        { "from_idx": 0, "to_idx": 1, "level": 0, "miles": 25.0,
          "coordinates": [[-87.63, 41.88], "..."] }
      ]
    }
  ]
}
```
- Routes come back sorted by `rank` (1 = recommended). `reason` explains why the route sits where it does.
- `engine` says how a route was computed: `"valhalla-truck"` (truck-profile routing) or `"osrm-car-truckspeed"` (car-profile routing with segment speeds capped at 62 mph, used for trips beyond the public Valhalla limit or as a fallback/fill; truck restrictions are not applied). Routes in one response may mix engines.
- `segments[*].coordinates` are slices of `geometry` between consecutive checkpoints, used to color the line by risk.
- `driver` is the condition that set the final level: `"wind" | "rain" | "snow" | "load"` (`"load"` when a load rule escalated it).

## POST /api/heatmap
Request: `{ "departure": "...", "route_geometries": [ <LineString>, ... ] }`. The frontend sends the geometries it got back from /api/plan.

Response 200:
```json
{
  "start": "2026-11-04T14:00:00Z",
  "hours": 49,
  "points": [ { "lon": -88.1, "lat": 41.7, "risk": [0,0,1,1,2, "... 49 values, one per hour h0..h48 from departure"] } ]
}
```
`risk[h]` is a float 0–4 computed with the same risk rules **without** load (pure weather), so a slider position maps to a field.

## Domain rules (backend must implement exactly; see brief)
Wind mph: `<25`→0, `25–<35`→1, `35–<45`→2, `45–<55`→3, `≥55`→4.
Rain in/hr: `<0.10`→0, `0.10–<0.25`→1, `0.25–<0.50`→2, `0.50–1.00`→3, `>1.00`→4.
Snow in/hr: `<0.5`→0, `0.5–<1.0`→1, `1.0–<2.0`→2, `2.0–3.0`→3, `>3.0`→4.
Wind uses sustained `wind_speed_10m`; gusts are shown but not scored (documented assumption).
Load rules on wind: `≥55` → 4 for any load. `45–<55` and load `>30000` → 4. `35–<45` and load `>40000` → 3.
Checkpoint level = max(wind after load rule, rain, snow).
Segment level = max(level of its two endpoint checkpoints). Segment miles count toward `miles_by_level`.
`avg_risk` = Σ(segment level × miles) / total miles.
Ranking sort key ascending: `(has_no_travel, severe_mi, high_mi, avg_risk, duration_s)`. Severe mi counts level 3 only, and No Travel is handled by the first key.
