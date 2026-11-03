import { describe, expect, it } from 'vitest'
import { heatWeightExpression } from './geojson'

describe('heatWeightExpression', () => {
  it('uses a plain property lookup on whole hours', () => {
    expect(heatWeightExpression(5)).toEqual(['/', ['get', 'h5'], 4])
  })
  it('blends neighbouring hours when fractional and clamps at max', () => {
    expect(JSON.stringify(heatWeightExpression(5.5))).toContain('"h6"')
    expect(heatWeightExpression(48)).toEqual(['/', ['get', 'h48'], 4])
  })
})
