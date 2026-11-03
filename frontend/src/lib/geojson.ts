import type { FeatureCollection, LineString, Point } from 'geojson'
import type { HeatmapResponse, PlanResponse } from './types'

export function buildSegmentsGeoJSON(plan: PlanResponse): FeatureCollection<LineString> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((r) =>
      r.segments.map((s) => ({
        type: 'Feature' as const,
        properties: { routeId: r.id, level: s.level },
        geometry: { type: 'LineString' as const, coordinates: s.coordinates },
      })),
    ),
  }
}

export function buildCheckpointsGeoJSON(plan: PlanResponse): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((r) =>
      r.checkpoints.map((c) => ({
        type: 'Feature' as const,
        properties: { routeId: r.id, idx: c.idx, level: c.level },
        geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] },
      })),
    ),
  }
}

/** One point source; each feature carries h0..h48 so the slider only swaps a paint expression. */
export function buildHeatmapGeoJSON(h: HeatmapResponse): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: h.points.map((p) => {
      const properties: Record<string, number> = {}
      p.risk.forEach((v, i) => { properties[`h${i}`] = v })
      return { type: 'Feature' as const, properties, geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] } }
    }),
  }
}

/** heatmap-weight expression for a (possibly fractional) hour, linearly blending h{n} and h{n+1}. */
export function heatWeightExpression(hour: number, maxHour = 48) {
  const a = Math.min(maxHour, Math.max(0, Math.floor(hour)))
  const b = Math.min(maxHour, a + 1)
  const f = Math.min(1, Math.max(0, hour - a))
  if (f === 0 || a === b) return ['/', ['get', `h${a}`], 4]
  return ['/', ['+', ['*', 1 - f, ['get', `h${a}`]], ['*', f, ['get', `h${b}`]]], 4]
}
