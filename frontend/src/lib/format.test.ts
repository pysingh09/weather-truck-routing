import { describe, expect, it } from 'vitest'
import { formatDuration, hourLabel, roundUpToNextHour } from './format'

describe('hourLabel', () => {
  it('formats +Xh with local weekday and time', () => {
    const start = new Date(2026, 10, 3, 14, 0).toISOString() // Tue 3 Nov 2026 14:00 local
    expect(hourLabel(start, 0)).toBe('+0h · Tue 14:00')
    expect(hourLabel(start, 10)).toBe('+10h · Wed 00:00')
    expect(hourLabel(start, 48)).toBe('+48h · Thu 14:00')
  })
})
describe('formatDuration', () => {
  it('formats h:mm', () => {
    expect(formatDuration(54000)).toBe('15:00')
    expect(formatDuration(3660)).toBe('1:01')
  })
})
describe('roundUpToNextHour', () => {
  it('always rounds strictly up', () => {
    const d = roundUpToNextHour(new Date(2026, 10, 3, 14, 20))
    expect([d.getHours(), d.getMinutes()]).toEqual([15, 0])
    expect(roundUpToNextHour(new Date(2026, 10, 3, 14, 0)).getHours()).toBe(15)
  })
})
