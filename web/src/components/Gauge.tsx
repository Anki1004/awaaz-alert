import type { Level } from '../api'

// Radial urgency gauge, 0..100. Colour follows the level, not the raw number, so thresholds read the same everywhere.
export function Gauge({ value, level, label = 'URGENCY' }: { value: number; level: Level; label?: string }) {
  const r = 54
  const c = 2 * Math.PI * r
  const arc = c * 0.75 // 270° sweep
  const filled = arc * Math.min(1, Math.max(0, value / 100))
  const color = level === 'critical' ? 'var(--color-red)' : level === 'high' ? '#ff9f43' : level === 'medium' ? 'var(--color-amber)' : 'var(--color-green)'
  return (
    <div className="relative flex flex-col items-center">
      <svg width="160" height="150" viewBox="0 0 140 130" className="drop-shadow-[0_0_18px_rgba(0,0,0,.6)]">
        <g transform="rotate(135 70 70)">
          <circle cx="70" cy="70" r={r} fill="none" stroke="#1d2833" strokeWidth="12" strokeDasharray={`${arc} ${c}`} strokeLinecap="round" />
          <circle cx="70" cy="70" r={r} fill="none" stroke={color} strokeWidth="12" strokeDasharray={`${filled} ${c}`} strokeLinecap="round"
            style={{ transition: 'stroke-dasharray .5s ease, stroke .3s' }} />
        </g>
        {[0, 35, 60, 80].map((t) => {
          const a = (135 + 270 * (t / 100)) * (Math.PI / 180)
          const x = 70 + Math.cos(a) * (r + 12), y = 70 + Math.sin(a) * (r + 12)
          return <circle key={t} cx={x} cy={y} r="1.6" fill="#3a4a5c" />
        })}
        <text x="70" y="66" textAnchor="middle" className="mono" fill={color} fontSize="34" fontWeight="600">{value}</text>
        <text x="70" y="84" textAnchor="middle" fill="#8b9bb0" fontSize="9" letterSpacing="2">{label}</text>
      </svg>
      <div className={`mono -mt-3 text-[11px] uppercase tracking-[.2em] lvl-${level}`}>{level}</div>
    </div>
  )
}
