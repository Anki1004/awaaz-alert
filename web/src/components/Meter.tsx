import type { Level } from '../api'

/** Needle meter (VU-style). 0..100 across a 100° sweep. Big one for urgency, small ones for signals. */
export function Needle({ value, level, size = 220, caption }: { value: number; level?: Level; size?: number; caption: string }) {
  const w = size, h = size * 0.80
  const cx = w / 2, cy = h * 0.70, r = w * 0.42
  const a0 = -140, a1 = -40 // degrees
  const ang = a0 + (a1 - a0) * Math.min(1, Math.max(0, value / 100))
  const pt = (deg: number, rad: number) => [cx + Math.cos((deg * Math.PI) / 180) * rad, cy + Math.sin((deg * Math.PI) / 180) * rad]
  const [nx, ny] = pt(ang, r * 0.92)
  const arc = (from: number, to: number, rad: number) => { const [x1, y1] = pt(from, rad); const [x2, y2] = pt(to, rad); return `M ${x1} ${y1} A ${rad} ${rad} 0 0 1 ${x2} ${y2}` }
  const ticks = [0, 20, 35, 50, 60, 80, 100]
  const color = level === 'critical' ? '#ff7b7b' : level === 'high' ? 'var(--color-ink)' : level === 'medium' ? '#d9a441' : 'var(--color-ok)'
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="block">
      {/* zones on the dial */}
      <path d={arc(a0, a0 + 100 * 0.35, r)} stroke="rgba(63,157,110,.35)" strokeWidth="6" fill="none" />
      <path d={arc(a0 + 100 * 0.35, a0 + 100 * 0.6, r)} stroke="rgba(217,164,65,.4)" strokeWidth="6" fill="none" />
      <path d={arc(a0 + 100 * 0.6, a0 + 100 * 0.8, r)} stroke="rgba(226,73,47,.5)" strokeWidth="6" fill="none" />
      <path d={arc(a0 + 100 * 0.8, a1, r)} stroke="rgba(179,38,30,.75)" strokeWidth="6" fill="none" />
      {ticks.map((t) => { const [x1, y1] = pt(a0 + t, r - 6); const [x2, y2] = pt(a0 + t, r - 12); const [tx, ty] = pt(a0 + t, r - 22); return (
        <g key={t}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--color-text-dim)" strokeWidth="1.2" />
          <text x={tx} y={ty + 3} textAnchor="middle" fontSize={size * 0.045} fill="var(--color-text-mute)" fontFamily="var(--font-data)">{t}</text></g>) })}
      {/* needle */}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={color} strokeWidth="2.2" strokeLinecap="round" style={{ transition: 'all .55s cubic-bezier(.3,1.2,.4,1)' }} />
      <circle cx={cx} cy={cy} r={size * 0.03} fill="var(--color-bezel)" stroke={color} strokeWidth="1.5" />
      <text data-testid="urgency-value" x={cx} y={cy + size * 0.17} textAnchor="middle" fontSize={size * 0.17} fontWeight="600" fill={color} fontFamily="var(--font-data)" style={{ transition: 'fill .3s' }}>{value}</text>
      <text x={cx} y={cy + size * 0.235} textAnchor="middle" fontSize={size * 0.045} letterSpacing="2" fill="var(--color-text-dim)" fontFamily="var(--font-ui)">{caption.toUpperCase()}</text>
    </svg>
  )
}

/** Horizontal VU bar with a needle-like marker; used for the emotion and fraud signal rows. */
export function Vu({ label, value, color = 'var(--color-ink)' }: { label: string; value: number; color?: string }) {
  const v = Math.max(0, Math.min(100, Math.round(value * 100)))
  return (
    <div className="flex items-center gap-2">
      <span className="label !tracking-[.06em] w-[88px] shrink-0 normal-case" style={{ textTransform: 'none', fontVariationSettings: '"wdth" 80, "wght" 500', fontSize: 12 }}>{label}</span>
      <div className="relative flex-1 h-[10px] rounded-[2px] bg-[#0c1020] border border-[var(--color-bezel)]">
        <div className="absolute inset-y-[2px] left-[2px] rounded-[1px]" style={{ width: `calc(${v}% - 3px)`, background: color, opacity: .55, transition: 'width .45s' }} />
        <div className="absolute top-[-2px] bottom-[-2px] w-[2px]" style={{ left: `calc(${v}% - 1px)`, background: color, transition: 'left .45s' }} />
      </div>
      <span className="data w-7 text-right text-[11px] text-[var(--color-text-dim)]">{v}</span>
    </div>
  )
}
