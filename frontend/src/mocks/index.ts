import geometries from './geometries.json'
import { checkpointLevel, continuousLevel, RAIN_BOUNDS, SNOW_BOUNDS, WIND_BOUNDS } from '../lib/risk'
import { riskLabel } from '../lib/risk-colors'
import type {
  Checkpoint, GeocodeResponse, HeatmapRequest, HeatmapResponse, LineStringGeometry, Place,
  PlanRequest, PlanResponse, Position, RiskLevel, Route, Segment, Weather,
} from '../lib/types'

const R = 3958.8
const rad = (d: number) => (d * Math.PI) / 180
function hav(a: Position, b: Position): number {
  const dLat = rad(b[1] - a[1])
  const dLon = rad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

const PLACES: Place[] = [
  { label: 'Chicago, IL, United States', lon: -87.63, lat: 41.88 },
  { label: 'Denver, CO, United States', lon: -104.99, lat: 39.74 },
  { label: 'Dallas, TX, United States', lon: -96.8, lat: 32.78 },
  { label: 'Des Moines, IA, United States', lon: -93.62, lat: 41.59 },
  { label: 'Omaha, NE, United States', lon: -95.94, lat: 41.26 },
  { label: 'Kansas City, MO, United States', lon: -94.58, lat: 39.1 },
  { label: 'Cheyenne, WY, United States', lon: -104.82, lat: 41.14 },
  { label: 'Atlanta, GA, United States', lon: -84.39, lat: 33.75 },
]

export function mockGeocode(q: string): GeocodeResponse {
  const s = q.trim().toLowerCase()
  if (s.length < 3) return { results: [] }
  return { results: PLACES.filter((p) => p.label.toLowerCase().includes(s)).slice(0, 5) }
}

/** Synthetic storm sweeping west->east (period 48h) over the plains, colder (snow) to the west. */
export function mockWeather(lon: number, lat: number, tMs: number): Weather {
  const phase = (tMs / 3600_000) % 48
  const cx = -112 + 0.9 * phase
  const d2 = ((lon - cx) / 2.6) ** 2 + ((lat - 41.2) / 1.5) ** 2
  const g = Math.exp(-d2 / 2)
  const base = 9 + 6 * Math.sin(lon / 3 + phase / 5)
  const wind = Math.max(0, base + 50 * g)
  const gust = wind * 1.4
  const cold = lon < -99
  return {
    wind_mph: +wind.toFixed(1),
    gust_mph: +gust.toFixed(1),
    rain_in_hr: cold ? 0 : +(0.9 * g ** 1.3).toFixed(2),
    snow_in_hr: cold ? +(3.4 * g ** 1.4).toFixed(2) : 0,
  }
}

interface Walker { cum: number[]; coords: Position[]; total: number }
function makeWalker(coords: Position[]): Walker {
  const cum = [0]
  for (let i = 1; i < coords.length; i++) cum.push(cum[i - 1] + hav(coords[i - 1], coords[i]))
  return { cum, coords, total: cum[cum.length - 1] }
}
function pointAt(w: Walker, mile: number): Position {
  const m = Math.min(Math.max(mile, 0), w.total)
  let i = 1
  while (i < w.cum.length - 1 && w.cum[i] < m) i++
  const span = w.cum[i] - w.cum[i - 1] || 1
  const f = (m - w.cum[i - 1]) / span
  const a = w.coords[i - 1]
  const b = w.coords[i]
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]
}
function slice(w: Walker, m0: number, m1: number): Position[] {
  const out: Position[] = [pointAt(w, m0)]
  for (let i = 0; i < w.coords.length; i++) if (w.cum[i] > m0 && w.cum[i] < m1) out.push(w.coords[i])
  out.push(pointAt(w, m1))
  return out
}

const SPEED: Record<string, number> = { r0: 57, r1: 59, r2: 55 }
const LABELS: Record<string, string> = { r0: 'Route A', r1: 'Route B', r2: 'Route C' }
const geoms = geometries as unknown as Record<string, Position[]>

function buildRoute(id: string, req: PlanRequest): Route {
  const coords = geoms[id]
  const w = makeWalker(coords)
  const depMs = Date.parse(req.departure)
  const speed = SPEED[id]
  const miles: number[] = []
  for (let m = 0; m < w.total; m += req.interval_mi) miles.push(m)
  miles.push(w.total)

  const checkpoints: Checkpoint[] = miles.map((mile, idx) => {
    const [lon, lat] = pointAt(w, mile)
    const etaMs = depMs + (mile / speed) * 3600_000
    const weather = mockWeather(lon, lat, etaMs)
    const level = checkpointLevel(weather, req.load_lb)
    const wl = checkpointLevel({ ...weather, rain_in_hr: 0, snow_in_hr: 0 }, req.load_lb)
    const rl = checkpointLevel({ wind_mph: 0, gust_mph: 0, rain_in_hr: weather.rain_in_hr, snow_in_hr: 0 }, 0)
    const sl = checkpointLevel({ wind_mph: 0, gust_mph: 0, rain_in_hr: 0, snow_in_hr: weather.snow_in_hr }, 0)
    const plainWind = checkpointLevel({ ...weather, rain_in_hr: 0, snow_in_hr: 0 }, 0)
    const driver: Checkpoint['driver'] =
      level === 0 ? 'wind'
        : wl === level && wl > plainWind ? 'load'
          : wl === level ? 'wind' : rl === level ? 'rain' : 'snow'
    const note = level === 0
      ? `Low - wind ${Math.round(weather.wind_mph)} mph`
      : `${riskLabel(level)} - ${driver === 'load' ? `wind ${Math.round(weather.wind_mph)} mph with ${req.load_lb.toLocaleString()} lb load`
        : driver === 'wind' ? `wind ${Math.round(weather.wind_mph)} mph (gusts ${Math.round(weather.gust_mph)})`
          : driver === 'rain' ? `rain ${weather.rain_in_hr.toFixed(2)} in/hr` : `snow ${weather.snow_in_hr.toFixed(2)} in/hr`}`
    return {
      idx, mile: +mile.toFixed(1), lon: +lon.toFixed(4), lat: +lat.toFixed(4),
      eta: new Date(etaMs).toISOString(), weather, level,
      levels: { wind: wl, rain: rl, snow: sl }, driver, note,
    }
  })

  const segments: Segment[] = []
  const byLevel: Record<string, number> = { '0': 0, '1': 0, '2': 0, '3': 0, '4': 0 }
  for (let i = 1; i < checkpoints.length; i++) {
    const a = checkpoints[i - 1]
    const b = checkpoints[i]
    const level = Math.max(a.level, b.level) as RiskLevel
    const mi = b.mile - a.mile
    byLevel[String(level)] += mi
    segments.push({ from_idx: i - 1, to_idx: i, level, miles: +mi.toFixed(1), coordinates: slice(w, a.mile, b.mile) })
  }
  for (const k of Object.keys(byLevel)) byLevel[k] = +byLevel[k].toFixed(1)
  const total = w.total
  const avg = Object.entries(byLevel).reduce((s, [k, v]) => s + Number(k) * v, 0) / total
  const maxLevel = Math.max(...checkpoints.map((c) => c.level)) as RiskLevel
  const durationS = Math.round((total / speed) * 3600)

  return {
    id, engine: 'valhalla-truck', rank: 0, label: LABELS[id],
    distance_mi: +total.toFixed(1), duration_s: durationS,
    arrival: new Date(depMs + durationS * 1000).toISOString(),
    geometry: { type: 'LineString', coordinates: coords },
    summary: {
      miles_by_level: byLevel, severe_mi: byLevel['3'], high_mi: byLevel['2'], no_travel_mi: byLevel['4'],
      avg_risk: +avg.toFixed(2), max_level: maxLevel, has_no_travel: byLevel['4'] > 0,
    },
    reason: '', checkpoints, segments,
  }
}

export function mockPlan(req: PlanRequest): PlanResponse {
  if (req.load_lb < 0 || req.load_lb > 80000) throw Object.assign(new Error('load_lb must be in 0-80000'), { field: 'load_lb' })
  const routes = ['r0', 'r1', 'r2'].map((id) => buildRoute(id, req))
  const key = (r: Route) => [Number(r.summary.has_no_travel), r.summary.severe_mi, r.summary.high_mi, r.summary.avg_risk, r.duration_s]
  routes.sort((a, b) => {
    const ka = key(a), kb = key(b)
    for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] - kb[i]
    return 0
  })
  routes.forEach((r, i) => { r.rank = i + 1 })
  const best = routes[0]
  routes.forEach((r) => {
    if (r === best) {
      const next = routes[1]
      r.reason = r.summary.has_no_travel
        ? 'Least bad option, but every route crosses No Travel conditions.'
        : `Recommended: ${Math.round(r.summary.severe_mi)} severe mi, fewest high-risk miles (${Math.round(r.summary.high_mi)} mi vs ${Math.round(next.summary.high_mi)} mi).`
    } else {
      const d = r.summary.severe_mi - best.summary.severe_mi
      r.reason = r.summary.has_no_travel
        ? `Ranked lower: ${Math.round(r.summary.no_travel_mi)} mi of No Travel conditions.`
        : d > 0 ? `Ranked lower: ${Math.round(d)} more severe miles than ${best.label}.`
          : `Ranked lower: ${Math.round(r.summary.high_mi - best.summary.high_mi)} more high-risk miles than ${best.label}.`
    }
  })
  return { recommended_route_id: best.id, all_no_travel: routes.every((r) => r.summary.has_no_travel), routes }
}

export function mockHeatmap(req: HeatmapRequest): HeatmapResponse {
  const startMs = Date.parse(req.departure)
  const cell = new Map<string, Position>()
  const perp = [-40, -20, 0, 20, 40]
  for (const g of req.route_geometries as LineStringGeometry[]) {
    const w = makeWalker(g.coordinates)
    for (let m = 0; m <= w.total; m += 30) {
      const [x, y] = pointAt(w, m)
      const [x2, y2] = pointAt(w, m + 5)
      const dx = (x2 - x) * Math.cos(rad(y)), dy = y2 - y
      const n = Math.hypot(dx, dy) || 1
      for (const o of perp) {
        const deg = o / 69
        const px = x + (-dy / n) * deg / Math.cos(rad(y))
        const py = y + (dx / n) * deg
        const key = `${Math.round(px / 0.45)}:${Math.round(py / 0.45)}`
        if (!cell.has(key)) cell.set(key, [px, py])
      }
    }
  }
  const points = [...cell.values()].map(([lon, lat]) => ({
    lon: +lon.toFixed(3), lat: +lat.toFixed(3),
    risk: Array.from({ length: 49 }, (_, h) => {
      const wx = mockWeather(lon, lat, startMs + h * 3600_000)
      return +Math.max(
        continuousLevel(wx.wind_mph, WIND_BOUNDS), continuousLevel(wx.rain_in_hr, RAIN_BOUNDS), continuousLevel(wx.snow_in_hr, SNOW_BOUNDS),
      ).toFixed(2)
    }),
  }))
  return { start: req.departure, hours: 49, points }
}
