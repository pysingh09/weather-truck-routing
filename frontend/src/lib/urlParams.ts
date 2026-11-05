import type { Place, PlanRequest } from './types'

// Shareable form state in the query string, e.g.
//   ?o=32.7767,-96.797,Dallas, TX&d=33.749,-84.388,Atlanta, GA&dep=+18h&load=20000&mi=25&go=1
// o/d = "lat,lon,label"; dep = datetime-local value ("2026-11-06T08:00") or "+Nh" from now;
// go=1 plans immediately on load.
export interface FormPrefill {
  origin?: Place
  destination?: Place
  departure?: Date
  load?: number
  interval?: PlanRequest['interval_mi']
  autoPlan: boolean
}

function parsePlace(raw: string | null): Place | undefined {
  if (!raw) return undefined
  const [lat, lon, ...rest] = raw.split(',')
  const place = { lat: Number(lat), lon: Number(lon), label: rest.join(',').trim() }
  if (!Number.isFinite(place.lat) || !Number.isFinite(place.lon) || Math.abs(place.lat) > 90 || Math.abs(place.lon) > 180) return undefined
  return { ...place, label: place.label || `${place.lat.toFixed(3)}, ${place.lon.toFixed(3)}` }
}

function parseDeparture(raw: string | null, now: number): Date | undefined {
  if (!raw) return undefined
  // A literal "+" in a query string decodes to a space, so the sign is optional.
  const rel = /^\+?(\d{1,3})h$/.exec(raw.trim())
  const d = rel ? new Date(now + Number(rel[1]) * 3600_000) : new Date(raw)
  if (Number.isNaN(d.getTime())) return undefined
  if (rel) d.setMinutes(0, 0, 0)
  return d
}

export function parsePrefill(search: string, now = Date.now()): FormPrefill {
  const q = new URLSearchParams(search)
  const load = q.get('load') === null ? NaN : Number(q.get('load'))
  const mi = Number(q.get('mi'))
  return {
    origin: parsePlace(q.get('o')),
    destination: parsePlace(q.get('d')),
    departure: parseDeparture(q.get('dep'), now),
    load: Number.isFinite(load) && load >= 0 && load <= 80000 ? load : undefined,
    interval: mi === 10 || mi === 25 || mi === 50 ? mi : undefined,
    autoPlan: q.get('go') === '1',
  }
}

const placeParam = (p: Place) => `${p.lat.toFixed(4)},${p.lon.toFixed(4)},${p.label}`

export function toSearch(req: PlanRequest): string {
  const q = new URLSearchParams({
    o: placeParam(req.origin),
    d: placeParam(req.destination),
    dep: req.departure,
    load: String(req.load_lb),
    mi: String(req.interval_mi),
  })
  return `?${q.toString()}`
}
