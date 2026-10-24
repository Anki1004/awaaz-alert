import { useEffect, useRef } from 'react'
import type { WindowResult } from '../api'

/**
 * The signature element: a chart-recorder paper strip. Time runs left→right (one 3 s window = 60 px),
 * urgency is a pen trace (0 at the bottom rule, 100 at the top), fraud cues are inked ticks under the
 * trace, and the moment a scam script is named a stamp lands on the paper. Click a window to inspect it.
 */
const PX_PER_WINDOW = 60
const H = 150
const PAD_TOP = 18
const PAD_BOTTOM = 34

export function StripChart({ windows, selected, onSelect, signature, live }: {
  windows: WindowResult[]; selected: number | null; onSelect: (i: number | null) => void; signature: string | null; live: boolean
}) {
  const scroller = useRef<HTMLDivElement>(null)
  const n = Math.max(windows.length, 14)
  const W = n * PX_PER_WINDOW + 40
  const y = (u: number) => PAD_TOP + (1 - u / 100) * (H - PAD_TOP - PAD_BOTTOM)
  const x = (i: number) => 20 + i * PX_PER_WINDOW + PX_PER_WINDOW / 2

  useEffect(() => {
    if (live && scroller.current && selected === null) scroller.current.scrollLeft = scroller.current.scrollWidth
  }, [windows.length, live, selected])

  const path = windows.map((w, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(w.urgency)}`).join(' ')
  const firstSig = windows.findIndex((w) => w.fraud.signature)

  return (
    <div className="paper relative overflow-hidden rounded-[4px]">
      {/* sprocket holes, like real chart paper */}
      <div className="absolute inset-y-0 left-0 w-[10px] flex flex-col justify-around pointer-events-none">
        {Array.from({ length: 6 }).map((_, i) => <span key={i} className="block w-[6px] h-[6px] rounded-full bg-[var(--color-console)] ml-[2px]" />)}
      </div>
      <div ref={scroller} className="overflow-x-auto overflow-y-hidden ml-[10px]" style={{ scrollbarWidth: 'thin' }}>
        <svg width={W} height={H} className="block">
          {/* level rules: 35 / 60 / 80 thresholds, labelled on the paper */}
          {[35, 60, 80].map((t) => (
            <g key={t}>
              <line x1="0" x2={W} y1={y(t)} y2={y(t)} stroke="rgba(42,36,25,.22)" strokeDasharray="2 4" />
              <text x={W - 6} y={y(t) - 3} textAnchor="end" fontSize="9" fill="rgba(42,36,25,.5)" fontFamily="var(--font-data)">{t}</text>
            </g>
          ))}
          <line x1="0" x2={W} y1={y(0)} y2={y(0)} stroke="rgba(42,36,25,.5)" />
          {/* time ruler */}
          {Array.from({ length: n }).map((_, i) => (
            <g key={i}>
              <line x1={20 + i * PX_PER_WINDOW} x2={20 + i * PX_PER_WINDOW} y1={y(0)} y2={y(0) + 5} stroke="rgba(42,36,25,.5)" />
              {i % 2 === 0 && <text x={20 + i * PX_PER_WINDOW + 2} y={H - 20} fontSize="9" fill="rgba(42,36,25,.55)" fontFamily="var(--font-data)">{i * 3}s</text>}
            </g>
          ))}
          {/* cue ticks: one ink mark per fraud match in the window, stacked */}
          {windows.map((w, i) => w.fraud.matches.slice(0, 5).map((m, k) => (
            <rect key={`${i}-${k}`} x={x(i) - 10 + k * 5} y={H - 14} width="3" height="8" rx="1"
              fill={m.category === 'threat' ? 'var(--color-stamp)' : m.category === 'payment' ? 'var(--color-carbon)' : m.category === 'victim_loss' ? '#2f7a53' : 'var(--color-ink-dark)'} opacity=".9">
              <title>{m.category}: {m.term}</title>
            </rect>
          )))}
          {/* pen trace, with a soft ink bleed under it */}
          {windows.length > 1 && <path d={path} fill="none" stroke="rgba(226,73,47,.25)" strokeWidth="6" strokeLinejoin="round" strokeLinecap="round" />}
          {windows.length > 0 && <path d={windows.length === 1 ? `M ${x(0) - 8} ${y(windows[0].urgency)} L ${x(0) + 8} ${y(windows[0].urgency)}` : path} fill="none" stroke="var(--color-ink-dark)" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" style={{ transition: 'd .4s' }} />}
          {/* per-window hit targets + markers */}
          {windows.map((w, i) => (
            <g key={i} onClick={() => onSelect(selected === i ? null : i)} style={{ cursor: 'pointer' }}>
              <rect x={20 + i * PX_PER_WINDOW} y="0" width={PX_PER_WINDOW} height={H} fill={selected === i ? 'rgba(43,91,215,.12)' : 'transparent'} />
              <circle cx={x(i)} cy={y(w.urgency)} r={selected === i ? 4.5 : 3} fill={w.level === 'critical' ? 'var(--color-stamp)' : w.level === 'high' ? 'var(--color-ink-dark)' : w.level === 'medium' ? '#9a6b12' : '#2f7a53'} stroke="var(--color-paper)" strokeWidth="1.5" />
              {(selected === i || (live && i === windows.length - 1)) && (
                <text x={x(i)} y={y(w.urgency) - 9} textAnchor="middle" fontSize="11" fontWeight="600" fill="var(--color-on-paper)" fontFamily="var(--font-data)">{w.urgency}</text>
              )}
            </g>
          ))}
          {/* pen head at the live edge */}
          {live && windows.length > 0 && <line x1={x(windows.length - 1) + PX_PER_WINDOW / 2} x2={x(windows.length - 1) + PX_PER_WINDOW / 2} y1="0" y2={H} stroke="rgba(43,91,215,.55)" strokeWidth="1" />}
        </svg>
      </div>
      {signature && firstSig >= 0 && (
        <div className="absolute top-3 right-4 pointer-events-none"><span className="stamp">{signature}</span></div>
      )}
      {windows.length === 0 && (
        <div className="absolute inset-0 grid place-items-center pointer-events-none">
          <span className="label">paper is blank — start a call, replay a sample or upload a recording</span>
        </div>
      )}
    </div>
  )
}
