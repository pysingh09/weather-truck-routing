import type { RiskLevel, Weather } from './types'

/** Lower bounds (inclusive) of levels 1..4 for each metric, mirroring docs/API_CONTRACT.md. */
export const WIND_BOUNDS = [25, 35, 45, 55]
export const RAIN_BOUNDS = [0.1, 0.25, 0.5, 1.0001]
export const SNOW_BOUNDS = [0.5, 1.0, 2.0, 3.0001]

export function levelFor(value: number, bounds: number[]): RiskLevel {
  let l = 0
  for (const b of bounds) if (value >= b) l++
  return l as RiskLevel
}

export function windLevelWithLoad(windMph: number, loadLb: number): RiskLevel {
  if (windMph >= 55) return 4
  if (windMph >= 45 && loadLb > 30000) return 4
  if (windMph >= 35 && windMph < 45 && loadLb > 40000) return 3
  return levelFor(windMph, WIND_BOUNDS)
}

export function checkpointLevel(w: Weather, loadLb: number): RiskLevel {
  return Math.max(
    windLevelWithLoad(w.wind_mph, loadLb),
    levelFor(w.rain_in_hr, RAIN_BOUNDS),
    levelFor(w.snow_in_hr, SNOW_BOUNDS),
  ) as RiskLevel
}

/** Continuous 0-4 risk (pure weather, no load) used for the mock heatmap. */
export function continuousLevel(value: number, bounds: number[]): number {
  const pts = [0, ...bounds]
  if (value <= 0) return 0
  for (let i = 1; i < pts.length; i++) {
    if (value < pts[i]) return i - 1 + (value - pts[i - 1]) / (pts[i] - pts[i - 1])
  }
  return 4
}
