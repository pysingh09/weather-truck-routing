import type { PlanResponse, Route } from '../lib/types'
import { RISK_COLORS, RISK_LEVELS, riskLabel } from '../lib/risk-colors'
import { formatDuration, formatLocalTime } from '../lib/format'

function MilesBar({ route }: { route: Route }) {
  const total = route.distance_mi || 1
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-100" role="img"
      aria-label={RISK_LEVELS.map((l) => `${riskLabel(l)} ${Math.round(route.summary.miles_by_level[String(l)] ?? 0)} miles`).join(', ')}>
      {RISK_LEVELS.map((l) => {
        const mi = route.summary.miles_by_level[String(l)] ?? 0
        return mi > 0 ? <div key={l} style={{ width: `${(mi / total) * 100}%`, background: RISK_COLORS[l] }} title={`${riskLabel(l)}: ${Math.round(mi)} mi`} /> : null
      })}
    </div>
  )
}

function Card({ route, recommended, selected, onSelect }: { route: Route; recommended: boolean; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" onClick={onSelect} aria-pressed={selected}
      className={`w-full rounded-xl border bg-white p-3 text-left transition hover:shadow-md ${selected ? 'border-slate-900 ring-1 ring-slate-900' : 'border-slate-200'}`}>
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-900">{route.label}</span>
        <span className="flex items-center gap-2">
          {recommended && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">Recommended</span>}
          <span className="text-xs text-slate-400">#{route.rank}</span>
        </span>
      </div>
      <div className="mt-1.5 grid grid-cols-3 gap-2 text-sm text-slate-700">
        <div><div className="text-[11px] uppercase text-slate-400">Distance</div>{Math.round(route.distance_mi)} mi</div>
        <div><div className="text-[11px] uppercase text-slate-400">Drive</div>{formatDuration(route.duration_s)} h</div>
        <div><div className="text-[11px] uppercase text-slate-400">Arrive</div>{formatLocalTime(route.arrival)}</div>
      </div>
      <div className="mt-2 text-[11px] text-slate-400"
        title={route.engine === 'valhalla-truck'
          ? 'Routed with a truck profile (weight-aware) on Valhalla.'
          : 'Routed with a car profile (OSRM) because the trip is too long for truck routing; durations use truck-realistic speeds (62 mph cap). Truck restrictions are not applied.'}>
        {route.engine === 'valhalla-truck' ? 'Truck routing' : 'Car routing · truck speeds'}
      </div>
      <div className="mt-2.5"><MilesBar route={route} /></div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-600">
        <span>Severe <b>{Math.round(route.summary.severe_mi)}</b> mi</span>
        <span>High <b>{Math.round(route.summary.high_mi)}</b> mi</span>
        {route.summary.no_travel_mi > 0 && <span className="font-semibold text-purple-700">No Travel {Math.round(route.summary.no_travel_mi)} mi</span>}
        <span>Avg risk <b>{route.summary.avg_risk.toFixed(2)}</b></span>
      </div>
      <p className="mt-2 text-xs text-slate-500">{route.reason}</p>
    </button>
  )
}

export function RouteCardsSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading routes">
      {[0, 1, 2].map((i) => (
        <div key={i} className="space-y-2 rounded-xl border border-slate-200 bg-white p-3">
          <div className="skeleton h-4 w-1/3" />
          <div className="skeleton h-8 w-full" />
          <div className="skeleton h-2.5 w-full" />
          <div className="skeleton h-3 w-2/3" />
        </div>
      ))}
    </div>
  )
}

export default function RouteCards({ plan, selectedId, onSelect }: { plan: PlanResponse; selectedId: string; onSelect: (id: string) => void }) {
  const routes = [...plan.routes].sort((a, b) => a.rank - b.rank)
  return (
    <div className="space-y-3">
      {plan.all_no_travel && (
        <div role="alert" className="rounded-xl border border-purple-300 bg-purple-50 p-3 text-sm text-purple-900">
          <p className="font-semibold">No safe route at this departure time — consider delaying</p>
          <p className="mt-0.5 text-xs">Every route hits No Travel conditions. Use the heatmap time slider on the map to look for a calmer window.</p>
        </div>
      )}
      {routes.map((r) => (
        <Card key={r.id} route={r} recommended={r.id === plan.recommended_route_id} selected={r.id === selectedId} onSelect={() => onSelect(r.id)} />
      ))}
    </div>
  )
}
