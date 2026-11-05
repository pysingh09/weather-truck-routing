import { lazy, Suspense, useCallback, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import TripForm from './components/TripForm'
import RouteCards, { RouteCardsSkeleton } from './components/RouteCards'
import TimeSlider from './components/TimeSlider'
import Legend from './components/Legend'
import Toast from './components/Toast'
import { ApiError, fetchHeatmap, planTrip } from './lib/api'
import { setPlaying, setTime } from './lib/timeStore'
import { toSearch } from './lib/urlParams'
import type { PlanRequest, PlanResponse } from './lib/types'

// MapLibre (~1 MB) loads as a separate chunk so the form and shell paint first.
const MapView = lazy(() => import('./components/MapView'))

interface Planned { req: PlanRequest; plan: PlanResponse }

export default function App() {
  const [planned, setPlanned] = useState<Planned | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [toast, setToast] = useState<string | null>(null)
  const [fieldError, setFieldError] = useState<{ field?: string; message: string } | null>(null)
  const [sheetOpen, setSheetOpen] = useState(true)

  const mutation = useMutation({
    mutationFn: planTrip,
    onMutate: () => { setToast(null); setFieldError(null) },
    onSuccess: (plan, req) => {
      setPlanned({ req, plan })
      setSelectedId(plan.recommended_route_id)
      setPlaying(false)
      setTime({ hour: 0 })
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400 && e.field) setFieldError({ field: e.field.split('.')[0], message: e.message }) // backend sends dotted paths, e.g. "origin.lat"
      else setToast(e instanceof Error ? e.message : 'Something went wrong.')
    },
  })

  // Separate query so routes render before the weather field arrives.
  const heat = useQuery({
    queryKey: ['heatmap', planned?.req.departure, planned?.plan.routes.map((r) => r.id + r.distance_mi).join()],
    queryFn: () => fetchHeatmap({ departure: planned!.req.departure, route_geometries: planned!.plan.routes.map((r) => r.geometry) }),
    enabled: !!planned,
  })

  const closeToast = useCallback(() => setToast(null), [])
  const plan = planned?.plan ?? null
  const onSubmit = (req: PlanRequest) => {
    mutation.mutate(req)
    setSheetOpen(true)
    // Keep the trip in the URL so it can be shared or reloaded (?go=1 to auto-plan).
    window.history.replaceState(null, '', toSearch(req))
  }

  return (
    <div className="relative h-dvh overflow-hidden md:flex">
      <div className="absolute inset-0 md:relative md:flex-1">
        <Suspense fallback={<div className="flex h-full items-center justify-center bg-slate-100 text-sm text-slate-400">Loading map…</div>}>
        <MapView plan={plan} selectedId={selectedId} onSelect={setSelectedId} heatmap={heat.data} startIso={planned?.req.departure ?? new Date().toISOString()} />
        </Suspense>
        <div className="pointer-events-none absolute inset-x-0 top-3 flex flex-col items-center gap-2 px-3 md:top-auto md:bottom-6">
          {plan && (
            <div className="pointer-events-auto w-full max-w-xl">
              <TimeSlider startIso={planned!.req.departure} loading={heat.isPending} />
            </div>
          )}
        </div>
        <div className="pointer-events-none absolute left-3 top-[96px] md:top-3">
          {plan && <Legend />}
        </div>
        <div className="pointer-events-none absolute inset-x-0 top-3 z-20 flex justify-center px-3 md:top-4">
          {toast && <Toast message={toast} onClose={closeToast} />}
        </div>
        {heat.isError && plan && (
          <div className="absolute right-3 top-3 hidden rounded bg-amber-100 px-2 py-1 text-xs text-amber-900 md:block">Weather heatmap unavailable</div>
        )}
      </div>

      <aside
        className={`absolute inset-x-0 bottom-0 z-10 flex flex-col rounded-t-2xl bg-slate-50 shadow-[0_-8px_24px_rgb(15_23_42/0.18)] transition-[max-height] duration-300 md:static md:order-first md:max-h-none md:w-[400px] md:shrink-0 md:rounded-none md:shadow-none md:border-r md:border-slate-200 ${sheetOpen ? 'max-h-[52dvh]' : 'max-h-[52px]'}`}
      >
        <button className="flex w-full items-center justify-center py-2 md:hidden" onClick={() => setSheetOpen((o) => !o)} aria-label={sheetOpen ? 'Collapse panel' : 'Expand panel'} aria-expanded={sheetOpen}>
          <span className="h-1.5 w-10 rounded-full bg-slate-300" />
        </button>
        <div className="flex-1 space-y-5 overflow-y-auto px-4 pb-6 md:pt-5">
          <header>
            <h1 className="text-lg font-bold tracking-tight text-slate-900">Weather-Aware Routing</h1>
            <p className="text-xs text-slate-500">Compare truck routes by forecast risk at your ETA.</p>
          </header>
          <TripForm loading={mutation.isPending} fieldError={fieldError} onSubmit={onSubmit} />
          {mutation.isPending && <RouteCardsSkeleton />}
          {!mutation.isPending && plan && <RouteCards plan={plan} selectedId={selectedId} onSelect={setSelectedId} />}
          {!mutation.isPending && !plan && (
            <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
              Pick an origin and destination to compare three truck routes, scored by forecast wind, rain and snow at the time you will actually be there.
            </p>
          )}
        </div>
      </aside>
    </div>
  )
}
