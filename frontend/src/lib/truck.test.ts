import { describe, expect, it } from 'vitest'
import { truckPosition } from './truck'
import type { Checkpoint } from './types'

const cp = (idx: number, lon: number, eta: string): Checkpoint => ({
  idx, mile: idx * 25, lon, lat: 40, eta,
  weather: { wind_mph: 0, gust_mph: 0, rain_in_hr: 0, snow_in_hr: 0 },
  level: 0, levels: { wind: 0, rain: 0, snow: 0 }, driver: 'wind', note: '',
})
const cps = [cp(0, -90, '2026-11-04T10:00:00Z'), cp(1, -92, '2026-11-04T12:00:00Z'), cp(2, -96, '2026-11-04T14:00:00Z')]

describe('truckPosition', () => {
  it('is null before departure and after arrival', () => {
    expect(truckPosition(cps, Date.parse('2026-11-04T09:59:00Z'))).toBeNull()
    expect(truckPosition(cps, Date.parse('2026-11-04T14:01:00Z'))).toBeNull()
  })
  it('interpolates within a leg', () => {
    expect(truckPosition(cps, Date.parse('2026-11-04T11:00:00Z'))).toEqual([-91, 40])
    expect(truckPosition(cps, Date.parse('2026-11-04T13:00:00Z'))).toEqual([-94, 40])
  })
  it('hits the endpoints exactly', () => {
    expect(truckPosition(cps, Date.parse('2026-11-04T10:00:00Z'))).toEqual([-90, 40])
    expect(truckPosition(cps, Date.parse('2026-11-04T14:00:00Z'))).toEqual([-96, 40])
  })
  it('returns null with fewer than two checkpoints', () => {
    expect(truckPosition([cps[0]], Date.parse('2026-11-04T10:00:00Z'))).toBeNull()
  })
})
