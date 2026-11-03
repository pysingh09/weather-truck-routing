import type {
  ApiErrorBody, GeocodeResponse, HeatmapRequest, HeatmapResponse, PlanRequest, PlanResponse,
} from './types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

/** Fire-and-forget: wakes a sleeping free-tier backend while the user fills in the form. */
export function warmUpBackend(): void {
  if (USE_MOCKS) return
  fetch(`${BASE}/api/health`).catch(() => {})
}

export class ApiError extends Error {
  field?: string
  status: number
  constructor(message: string, status: number, field?: string) {
    super(message)
    this.status = status
    this.field = field
  }
}

async function request<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      signal,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError('Cannot reach the server. Is the backend running?', 0)
  }
  if (!res.ok) {
    let body: Partial<ApiErrorBody> = {}
    try { body = await res.json() } catch { /* non-JSON error */ }
    throw new ApiError(body.error ?? `Request failed (${res.status})`, res.status, body.field)
  }
  return res.json() as Promise<T>
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

export async function geocode(q: string, signal?: AbortSignal): Promise<GeocodeResponse> {
  if (USE_MOCKS) {
    const { mockGeocode } = await import('../mocks')
    await delay(150)
    return mockGeocode(q)
  }
  return request(`/api/geocode?q=${encodeURIComponent(q)}`, undefined, signal)
}

export async function planTrip(body: PlanRequest): Promise<PlanResponse> {
  if (USE_MOCKS) {
    const { mockPlan } = await import('../mocks')
    await delay(900)
    return mockPlan(body)
  }
  return request('/api/plan', { method: 'POST', body: JSON.stringify(body) })
}

export async function fetchHeatmap(body: HeatmapRequest): Promise<HeatmapResponse> {
  if (USE_MOCKS) {
    const { mockHeatmap } = await import('../mocks')
    await delay(1400)
    return mockHeatmap(body)
  }
  return request('/api/heatmap', { method: 'POST', body: JSON.stringify(body) })
}
