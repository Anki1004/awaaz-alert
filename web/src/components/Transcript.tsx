import type { WindowResult } from '../api'

// Transcript with fraud cues highlighted by category. Redacted by default (PII never shown unless the operator opts in).
function Highlighted({ text, matches }: { text: string; matches: WindowResult['fraud']['matches'] }) {
  if (!matches.length) return <>{text}</>
  const sorted = [...matches].sort((a, b) => a.start - b.start)
  const out: React.ReactNode[] = []
  let cur = 0
  sorted.forEach((m, i) => {
    if (m.start < cur) return
    out.push(text.slice(cur, m.start))
    out.push(<mark key={i} className={`cue ${m.category}`} title={m.category}>{text.slice(m.start, m.end)}</mark>)
    cur = m.end
  })
  out.push(text.slice(cur))
  return <>{out}</>
}

export function Transcript({ windows, selected, redact }: { windows: WindowResult[]; selected: number | null; redact: boolean }) {
  if (!windows.length) return <div className="p-4 text-[13px] text-[var(--color-text-mute)]">Words appear here as the pen moves.</div>
  return (
    <div className="p-3 space-y-2 overflow-y-auto h-full">
      {windows.map((w, i) => {
        const text = redact ? w.transcript_redacted : w.transcript
        // offsets in matches refer to the raw transcript; when redacted, lengths may shift, so highlight only in raw mode
        return (
          <div key={i} className={`flex gap-3 px-2 py-1 border-l-2 ${selected === i ? 'border-[var(--color-carbon)] bg-[var(--color-console-3)]' : 'border-transparent'}`}>
            <span className="data text-[11px] text-[var(--color-text-mute)] w-10 shrink-0 pt-[4px]">{Math.floor(w.t_start)}s</span>
            <span className={`data text-[10px] w-8 shrink-0 pt-[4px] lvl-${w.level}`}>{w.urgency}</span>
            <p className="tline text-[15px] leading-[1.7] flex-1">
              {text ? (redact ? text : <Highlighted text={text} matches={w.fraud.matches} />) : <span className="text-[var(--color-text-mute)] italic">— no speech —</span>}
            </p>
          </div>
        )
      })}
    </div>
  )
}
