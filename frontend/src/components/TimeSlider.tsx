import { hourLabel } from '../lib/format'
import { MAX_HOUR, setPlaying, setTime, useTime } from '../lib/timeStore'

/** Only this small component re-renders while scrubbing/playing; map layers react via the store. */
export default function TimeSlider({ startIso, loading }: { startIso: string; loading: boolean }) {
  const { hour, playing, visible } = useTime()
  return (
    <div className="w-full max-w-xl rounded-xl bg-white/95 p-3 shadow-lg backdrop-blur">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Weather risk heatmap</span>
        {loading ? (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">loading weather field…</span>
        ) : (
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-600">
            <input type="checkbox" checked={visible} onChange={(e) => setTime({ visible: e.target.checked })} />
            Show
          </label>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button type="button" disabled={loading} onClick={() => setPlaying(!playing)} aria-label={playing ? 'Pause' : 'Play'}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white disabled:opacity-40">
          {playing ? (
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><rect x="1" y="1" width="3.5" height="10" /><rect x="7.5" y="1" width="3.5" height="10" /></svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><path d="M2 1l9 5-9 5z" /></svg>
          )}
        </button>
        <input type="range" min={0} max={MAX_HOUR} step={0.25} value={hour} disabled={loading} aria-label="Forecast hour"
          onChange={(e) => { setPlaying(false); setTime({ hour: Number(e.target.value) }) }} className="h-2 w-full accent-slate-900" />
      </div>
      <div className="mt-1 text-center text-sm font-medium tabular-nums text-slate-800">{hourLabel(startIso, Math.floor(hour))}</div>
    </div>
  )
}
