import { describe, expect, it } from 'vitest'
import { clampLevel, riskColor, riskLabel } from './risk-colors'

describe('risk helpers', () => {
  it('maps levels to contract colors and labels', () => {
    expect(riskColor(0)).toBe('#22c55e')
    expect(riskColor(3)).toBe('#dc2626')
    expect(riskColor(4)).toBe('#7e22ce')
    expect(riskLabel(1)).toBe('Moderate')
    expect(riskLabel(4)).toBe('No Travel')
  })
  it('clamps and rounds out-of-range floats', () => {
    expect(clampLevel(-1)).toBe(0)
    expect(clampLevel(9)).toBe(4)
    expect(clampLevel(2.4)).toBe(2)
  })
})
