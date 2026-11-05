import { useEffect, useRef, useState } from 'react'
import PlaceInput from './PlaceInput'
import { roundUpToNextHour, toLocalInputValue } from '../lib/format'
import { parsePrefill } from '../lib/urlParams'
import type { PlanRequest, Place } from '../lib/types'

const PRESETS = [20000, 35000, 45000]
const INTERVALS: PlanRequest['interval_mi'][] = [10, 25, 50]

interface Props {
  loading: boolean
  fieldError?: { field?: string; message: string } | null
  onSubmit: (req: PlanRequest) => void
}

export default function TripForm({ loading, fieldError, onSubmit }: Props) {
  const [prefill] = useState(() => parsePrefill(window.location.search))
  const [origin, setOrigin] = useState<Place | null>(prefill.origin ?? null)
  const [destination, setDestination] = useState<Place | null>(prefill.destination ?? null)
  const [departure, setDeparture] = useState(() => toLocalInputValue(prefill.departure ?? roundUpToNextHour()))
  const [load, setLoad] = useState(prefill.load ?? 38000)
  const [interval, setIntervalMi] = useState<PlanRequest['interval_mi']>(prefill.interval ?? 25)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const [{ minDeparture, maxDeparture }] = useState(() => ({
    minDeparture: toLocalInputValue(new Date(Date.now() - 3600_000)),
    maxDeparture: toLocalInputValue(new Date(Date.now() + 7 * 24 * 3600_000)),
  }))

  const errFor = (f: string) => errors[f] ?? (fieldError?.field === f ? fieldError.message : undefined)

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault()
    const errs: Record<string, string> = {}
    if (!origin) errs.origin = 'Pick an origin from the suggestions.'
    if (!destination) errs.destination = 'Pick a destination from the suggestions.'
    if (origin && destination && Math.abs(origin.lat - destination.lat) < 0.01 && Math.abs(origin.lon - destination.lon) < 0.01)
      errs.destination = 'Origin and destination are the same place; pick two different locations.'
    const dep = new Date(departure)
    if (Number.isNaN(dep.getTime())) errs.departure = 'Enter a departure time.'
    else if (dep.getTime() > Date.now() + 7 * 24 * 3600_000) errs.departure = 'Forecast only covers the next 7 days.'
    else if (dep.getTime() < Date.now() - 3600_000) errs.departure = 'Departure cannot be in the past.'
    if (!(load >= 0 && load <= 80000)) errs.load_lb = 'Load must be between 0 and 80,000 lb.'
    setErrors(errs)
    if (Object.keys(errs).length || !origin || !destination) return
    onSubmit({ origin, destination, departure: dep.toISOString(), load_lb: load, interval_mi: interval })
  }

  // ?go=1 plans once on load (ref guard: StrictMode runs effects twice in dev).
  const autoPlanned = useRef(false)
  useEffect(() => {
    if (!prefill.autoPlan || autoPlanned.current) return
    autoPlanned.current = true
    submit()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const inputCls = (f: string) =>
    `w-full rounded-lg border bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-slate-400 ${errFor(f) ? 'border-red-400' : 'border-slate-300'}`
  const labelCls = 'mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500'

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <PlaceInput label="Origin" value={origin} onChange={setOrigin} error={errFor('origin')} placeholder="e.g. Chicago" />
      <PlaceInput label="Destination" value={destination} onChange={setDestination} error={errFor('destination')} placeholder="e.g. Denver" />

      <div>
        <label htmlFor="dep" className={labelCls}>Departure (local time)</label>
        <input id="dep" type="datetime-local" value={departure} min={minDeparture} max={maxDeparture}
          onChange={(e) => setDeparture(e.target.value)} className={inputCls('departure')} aria-invalid={!!errFor('departure')} />
        {errFor('departure') && <p role="alert" className="mt-1 text-xs text-red-600">{errFor('departure')}</p>}
      </div>

      <div>
        <label htmlFor="load" className={labelCls}>Load weight (lb)</label>
        <input id="load" type="number" inputMode="numeric" min={0} max={80000} step={500} value={load}
          onChange={(e) => setLoad(Number(e.target.value))} className={inputCls('load_lb')} aria-invalid={!!errFor('load_lb')} />
        <div className="mt-2 flex gap-2">
          {PRESETS.map((p) => (
            <button key={p} type="button" onClick={() => setLoad(p)}
              className={`rounded-full border px-3 py-1 text-xs ${load === p ? 'border-slate-800 bg-slate-800 text-white' : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'}`}>
              {p / 1000}k
            </button>
          ))}
        </div>
        {errFor('load_lb') && <p role="alert" className="mt-1 text-xs text-red-600">{errFor('load_lb')}</p>}
      </div>

      <div>
        <span className={labelCls} id="interval-label">Weather sample interval</span>
        <div role="radiogroup" aria-labelledby="interval-label" className="grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1">
          {INTERVALS.map((i) => (
            <button key={i} type="button" role="radio" aria-checked={interval === i} onClick={() => setIntervalMi(i)}
              className={`rounded-md py-1.5 text-sm ${interval === i ? 'bg-white font-semibold shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}>
              {i} mi
            </button>
          ))}
        </div>
        {errFor('interval_mi') && <p role="alert" className="mt-1 text-xs text-red-600">{errFor('interval_mi')}</p>}
      </div>

      <button type="submit" disabled={loading}
        className="w-full rounded-lg bg-slate-900 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60">
        {loading ? 'Planning routes...' : 'Plan routes'}
      </button>
    </form>
  )
}
