import { RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '../lib/risk-colors'

export default function Legend() {
  return (
    <div className="pointer-events-none rounded-lg bg-white/90 px-3 py-2 text-xs shadow backdrop-blur" aria-label="Risk legend">
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {RISK_LEVELS.map((l) => (
          <span key={l} className="flex items-center gap-1.5 text-slate-700">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: RISK_COLORS[l] }} />
            {RISK_LABELS[l]}
          </span>
        ))}
      </div>
    </div>
  )
}
