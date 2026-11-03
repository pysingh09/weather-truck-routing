const pad = (n: number) => String(n).padStart(2, '0')

export function formatDuration(seconds: number): string {
  const m = Math.round(seconds / 60)
  return `${Math.floor(m / 60)}:${pad(m % 60)}`
}

export function formatLocalTime(iso: string): string {
  return new Date(iso).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/** Label for the heatmap slider: "+6h · Tue 14:00" (local time of start + h hours). */
export function hourLabel(startIso: string, h: number): string {
  const d = new Date(new Date(startIso).getTime() + h * 3600_000)
  const day = d.toLocaleDateString('en-US', { weekday: 'short' })
  return `+${h}h · ${day} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function roundUpToNextHour(now = new Date()): Date {
  const d = new Date(now)
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return d
}

/** Date -> value for <input type="datetime-local"> in local time. */
export function toLocalInputValue(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
