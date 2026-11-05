import { describe, expect, it } from 'vitest'
import { parsePrefill, toSearch } from './urlParams'

describe('parsePrefill', () => {
  it('reads places, load, interval and auto-plan', () => {
    const p = parsePrefill('?o=32.7767,-96.797,Dallas, TX&d=33.749,-84.388,Atlanta, GA&load=20000&mi=10&go=1')
    expect(p.origin).toEqual({ lat: 32.7767, lon: -96.797, label: 'Dallas, TX' })
    expect(p.destination?.label).toBe('Atlanta, GA')
    expect(p.load).toBe(20000)
    expect(p.interval).toBe(10)
    expect(p.autoPlan).toBe(true)
  })

  it('resolves relative departure to the top of the local hour', () => {
    const now = Date.UTC(2026, 10, 5, 9, 41)
    for (const q of ['?dep=+18h', '?dep=18h', '?dep=%2B18h']) {
      const d = parsePrefill(q, now).departure!
      expect([d.getMinutes(), d.getSeconds()]).toEqual([0, 0])
      const hoursAhead = (d.getTime() - now) / 3600_000
      expect(hoursAhead).toBeGreaterThan(17)
      expect(hoursAhead).toBeLessThanOrEqual(18)
    }
  })

  it('ignores invalid values', () => {
    const p = parsePrefill('?o=abc&d=95,0,X&load=-5&mi=30&dep=nope')
    expect(p).toEqual({ origin: undefined, destination: undefined, departure: undefined, load: undefined, interval: undefined, autoPlan: false })
  })

  it('round-trips a plan request', () => {
    const search = toSearch({
      origin: { lat: 32.7767, lon: -96.797, label: 'Dallas, TX' },
      destination: { lat: 33.749, lon: -84.388, label: 'Atlanta, GA' },
      departure: '2026-11-06T14:00:00.000Z', load_lb: 45000, interval_mi: 50,
    })
    const p = parsePrefill(search)
    expect(p.origin?.label).toBe('Dallas, TX')
    expect(p.departure?.toISOString()).toBe('2026-11-06T14:00:00.000Z')
    expect([p.load, p.interval]).toEqual([45000, 50])
  })
})
