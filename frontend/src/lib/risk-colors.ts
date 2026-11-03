import type { RiskLevel } from './types'

export const RISK_COLORS: Record<RiskLevel, string> = {
  0: '#22c55e',
  1: '#eab308',
  2: '#f97316',
  3: '#dc2626',
  4: '#7e22ce',
}
export const RISK_LABELS: Record<RiskLevel, string> = {
  0: 'Low',
  1: 'Moderate',
  2: 'High',
  3: 'Severe',
  4: 'No Travel',
}
export const RISK_LEVELS: RiskLevel[] = [0, 1, 2, 3, 4]

export function clampLevel(n: number): RiskLevel {
  return Math.min(4, Math.max(0, Math.round(n))) as RiskLevel
}
export function riskColor(level: number): string {
  return RISK_COLORS[clampLevel(level)]
}
export function riskLabel(level: number): string {
  return RISK_LABELS[clampLevel(level)]
}
/** MapLibre `match` expression on a numeric property. */
export function riskMatchExpression(prop = 'level') {
  return [
    'match', ['get', prop],
    0, RISK_COLORS[0], 1, RISK_COLORS[1], 2, RISK_COLORS[2], 3, RISK_COLORS[3], 4, RISK_COLORS[4],
    '#94a3b8',
  ] as unknown as import('maplibre-gl').ExpressionSpecification
}
