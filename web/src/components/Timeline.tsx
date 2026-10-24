import type { WindowResult } from '../api'

// One bar per analysed window. Height = urgency, colour = level. Click selects the window.
export function Timeline({ windows, selected, onSelect }: { windows: WindowResult[]; selected: number | null; onSelect: (i: number) => void }) {
  const cols = Math.max(20, windows.length)
  return (
    <div className="h-[92px] flex items-end gap-[3px] px-2 pb-2 pt-3 overflow-x-auto">
      {Array.from({ length: cols }).map((_, i) => {
        const w = windows[i]
        if (!w) return <div key={i} className="w-[14px] shrink-0 h-[6px] rounded-sm bg-[#17212b]" />
        const h = Math.max(6, (w.urgency / 100) * 70)
        return (
          <button key={i} onClick={() => onSelect(i)} title={`${w.t_start}s · ${w.urgency}`}
            className={`w-[14px] shrink-0 rounded-sm transition-all ${selected === i ? 'outline outline-1 outline-white/60' : ''}`}
            style={{ height: h, background: w.level === 'critical' ? 'var(--color-red)' : w.level === 'high' ? '#ff9f43' : w.level === 'medium' ? 'var(--color-amber)' : 'var(--color-green)', opacity: selected === null || selected === i ? 1 : 0.55 }} />
        )
      })}
    </div>
  )
}
