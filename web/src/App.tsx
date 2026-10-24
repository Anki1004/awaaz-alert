import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, wsUrl, type Health, type Overall, type Sample, type WindowResult, type WsEvent } from './api'
import { startMic, type MicHandle } from './audio'
import { Gauge } from './components/Gauge'
import { Timeline } from './components/Timeline'
import { Transcript } from './components/Transcript'
import { EmotionBars } from './components/EmotionBars'
import { Scope } from './components/Scope'

type Mode = 'idle' | 'live' | 'replay' | 'file'

interface CallRow { id: string; title: string; kind: string; overall: Overall | null; windows: WindowResult[]; duration?: number; running?: boolean }

const EMPTY_OVERALL: Overall = { urgency: 0, level: 'low', signature: null, explain: ['waiting for audio'] }

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [samples, setSamples] = useState<Sample[]>([])
  const [mode, setMode] = useState<Mode>('idle')
  const [windows, setWindows] = useState<WindowResult[]>([])
  const [overall, setOverall] = useState<Overall>(EMPTY_OVERALL)
  const [selected, setSelected] = useState<number | null>(null)
  const [redact, setRedact] = useState(true)
  const [queue, setQueue] = useState<CallRow[]>([])
  const [activeId, setActiveId] = useState<string>('live')
  const [err, setErr] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const micRef = useRef<MicHandle | null>(null)
  const [, tick] = useState(0)

  useEffect(() => {
    const poll = () => api.health().then(setHealth).catch(() => setHealth(null))
    poll(); const t = setInterval(poll, 4000); return () => clearInterval(t)
  }, [])
  useEffect(() => { api.samples().then(setSamples).catch(() => setSamples([])) }, [])
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 120); return () => clearInterval(t) }, [])

  const current = useMemo(() => (selected !== null ? windows[selected] : windows[windows.length - 1]) ?? null, [windows, selected])

  const upsertQueue = useCallback((row: CallRow) => {
    setQueue((q) => {
      const rest = q.filter((r) => r.id !== row.id)
      return [...rest, row].sort((a, b) => (b.overall?.urgency ?? -1) - (a.overall?.urgency ?? -1))
    })
  }, [])

  const stopAll = useCallback(() => {
    wsRef.current?.close(); wsRef.current = null
    micRef.current?.stop(); micRef.current = null
    setMode('idle')
  }, [])

  const resetView = () => { setWindows([]); setOverall(EMPTY_OVERALL); setSelected(null); setErr(null) }

  const handleEvent = (id: string, title: string, kind: string) => (ev: WsEvent) => {
    if (ev.type === 'window') {
      setWindows((w) => { const next = [...w, ev.data]; upsertQueue({ id, title, kind, overall: ev.overall, windows: next, running: true }); return next })
      setOverall(ev.overall)
    } else if (ev.type === 'done') {
      setOverall(ev.overall)
      setQueue((q) => q.map((r) => (r.id === id ? { ...r, overall: ev.overall, running: false } : r)))
      setMode('idle')
    } else if (ev.type === 'error') setErr(ev.message)
  }

  const startLive = async () => {
    stopAll(); resetView(); setActiveId('live')
    try {
      const ws = new WebSocket(wsUrl('/ws/live'))
      wsRef.current = ws
      ws.onmessage = (m) => handleEvent('live', 'Live call (mic)', 'live')(JSON.parse(m.data))
      ws.onclose = () => { micRef.current?.stop(); micRef.current = null; setMode((mo) => (mo === 'live' ? 'idle' : mo)) }
      await new Promise<void>((res, rej) => { ws.onopen = () => res(); ws.onerror = () => rej(new Error('ws failed')) })
      micRef.current = await startMic((pcm) => { if (ws.readyState === 1) ws.send(pcm) })
      upsertQueue({ id: 'live', title: 'Live call (mic)', kind: 'live', overall: null, windows: [], running: true })
      setMode('live')
    } catch (e) { setErr((e as Error).message); stopAll() }
  }

  const stopLive = () => {
    wsRef.current?.send(JSON.stringify({ cmd: 'flush' }))
    setTimeout(stopAll, 400)
    setQueue((q) => q.map((r) => (r.id === 'live' ? { ...r, running: false } : r)))
  }

  const replay = (s: Sample, speed = 1) => {
    stopAll(); resetView(); setActiveId(s.id)
    const ws = new WebSocket(wsUrl(`/ws/replay?sample=${encodeURIComponent(s.file)}&speed=${speed}`))
    wsRef.current = ws
    ws.onmessage = (m) => handleEvent(s.id, s.title, s.kind)(JSON.parse(m.data))
    ws.onerror = () => setErr('replay connection failed')
    upsertQueue({ id: s.id, title: s.title, kind: s.kind, overall: null, windows: [], running: true })
    setMode('replay')
  }

  const analyzeAll = async () => {
    // Batch-score every sample through /analyze to populate the priority queue (what an operator sees at a glance).
    for (const s of samples) {
      upsertQueue({ id: s.id, title: s.title, kind: s.kind, overall: null, windows: [], running: true })
      const r = await fetch(`/api/samples/${encodeURIComponent(s.file)}`).then((x) => x.blob())
      const res = await api.analyze(new File([r], s.file))
      if ('error' in res) { setErr(res.error); continue }
      upsertQueue({ id: s.id, title: s.title, kind: s.kind, overall: res.overall, windows: res.windows, duration: res.duration, running: false })
    }
  }

  const onFile = async (f: File | null) => {
    if (!f) return
    stopAll(); resetView(); setActiveId(f.name); setMode('file')
    upsertQueue({ id: f.name, title: f.name, kind: 'upload', overall: null, windows: [], running: true })
    const res = await api.analyze(f)
    if ('error' in res) { setErr(res.error); setMode('idle'); return }
    setWindows(res.windows); setOverall(res.overall); setMode('idle')
    upsertQueue({ id: f.name, title: f.name, kind: 'upload', overall: res.overall, windows: res.windows, duration: res.duration, running: false })
  }

  const openRow = (r: CallRow) => { if (r.running && r.id === activeId) return; stopAll(); setActiveId(r.id); setWindows(r.windows); setOverall(r.overall ?? EMPTY_OVERALL); setSelected(null) }

  const ready = !!health?.ready
  const micLevel = micRef.current?.level() ?? 0

  return (
    <div className="h-full flex flex-col scope">
      {/* top bar */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)] bg-[#0d1319]/80 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-md bg-[var(--color-amber)] text-[#1a1407] grid place-items-center font-bold">आ</div>
          <div>
            <div className="font-semibold tracking-tight leading-none">AwaazAlert</div>
            <div className="text-[11px] text-[var(--color-ink-dim)] mt-[3px]">Distress + fraud-script radar for 1930 helpline operators</div>
          </div>
        </div>
        <div className="flex items-center gap-5 text-[12px] text-[var(--color-ink-dim)]">
          <span className="flex items-center gap-2"><i className={`led ${ready ? 'on' : health ? 'warn' : 'off'}`} />{ready ? `models ready · ${health?.device}` : health ? 'loading models…' : 'server offline'}</span>
          <span className="hidden md:inline mono">{health?.whisper ?? '—'} · {health?.emotion ?? '—'}</span>
        </div>
      </header>

      {/* responsible-AI banner — required by the problem statement, kept visible */}
      <div className="px-5 py-1.5 text-[12px] bg-[rgba(245,181,63,.08)] border-b border-[rgba(245,181,63,.18)] text-[var(--color-amber)]">
        Indicative signal only. Scores help prioritise calls; they are not evidence of anyone's intent, honesty or guilt. Audio is analysed in memory and never stored.
      </div>

      <main className="flex-1 grid grid-cols-12 gap-3 p-3 min-h-0">
        {/* left: queue */}
        <aside className="col-span-12 lg:col-span-3 panel flex flex-col min-h-0">
          <div className="panel-h"><span>Call queue · by urgency</span><span className="mono">{queue.length}</span></div>
          <div className="flex-1 overflow-y-auto">
            {queue.length === 0 && <div className="p-4 text-[13px] text-[var(--color-ink-mute)]">No calls yet. Start the mic, replay a sample, or score all samples.</div>}
            {queue.map((r) => (
              <button key={r.id} onClick={() => openRow(r)} className={`w-full text-left px-3 py-2.5 border-b border-[var(--color-line)] hover:bg-white/[.03] ${activeId === r.id ? 'bg-white/[.05]' : ''}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium truncate">{r.title}</span>
                  <span className={`mono text-[12px] px-1.5 py-[1px] rounded bg-lvl-${r.overall?.level ?? 'low'} lvl-${r.overall?.level ?? 'low'}`}>{r.overall ? r.overall.urgency : r.running ? '…' : '—'}</span>
                </div>
                <div className="text-[11px] text-[var(--color-ink-dim)] mt-[2px] flex items-center gap-2">
                  {r.running && <i className="led rec" />}
                  <span className="truncate">{r.overall?.signature ?? r.kind}</span>
                </div>
              </button>
            ))}
          </div>
          <div className="p-3 border-t border-[var(--color-line)] space-y-2">
            <div className="text-[11px] uppercase tracking-[.14em] text-[var(--color-ink-dim)]">Demo calls</div>
            <div className="grid grid-cols-1 gap-1.5">
              {samples.map((s) => (
                <div key={s.id} className="flex items-center gap-1.5">
                  <button className="btn flex-1 text-left truncate" disabled={!ready} onClick={() => replay(s)} title={s.note}>▶ {s.title}</button>
                  <button className="btn mono text-[11px]" disabled={!ready} onClick={() => replay(s, 3)} title="replay at 3× speed">3×</button>
                </div>
              ))}
            </div>
            <button className="btn w-full" disabled={!ready || !samples.length} onClick={analyzeAll}>Score all samples → queue</button>
          </div>
        </aside>

        {/* centre: live analysis */}
        <section className="col-span-12 lg:col-span-6 flex flex-col gap-3 min-h-0">
          <div className="panel">
            <div className="panel-h">
              <span className="flex items-center gap-2"><i className={`led ${mode === 'live' ? 'rec' : mode === 'replay' ? 'warn' : 'off'}`} />{mode === 'live' ? 'live · mic' : mode === 'replay' ? 'replay' : mode === 'file' ? 'analysing file' : 'standby'}</span>
              <div className="flex items-center gap-2">
                {mode !== 'live' ? <button className="btn primary" disabled={!ready} onClick={startLive}>● Start live call</button>
                  : <button className="btn danger" onClick={stopLive}>■ End call</button>}
                <label className="btn cursor-pointer">Upload recording<input type="file" accept="audio/*,video/*" className="hidden" onChange={(e) => onFile(e.target.files?.[0] ?? null)} /></label>
              </div>
            </div>
            <div className="grid grid-cols-[180px_1fr] gap-2 p-3">
              <Gauge value={overall.urgency} level={overall.level} />
              <div className="min-w-0">
                <Scope wave={micRef.current?.wave ?? null} active={mode === 'live'} level={overall.level} />
                <div className="mt-1 flex items-center justify-between text-[11px] text-[var(--color-ink-dim)] mono">
                  <span>{mode === 'live' ? `mic level ${(micLevel * 100).toFixed(0)}` : current ? `${current.t_start}s–${current.t_end}s` : 'no window'}</span>
                  <span>{current ? `latency ${current.latency_ms} ms · ${current.language ?? '–'}` : ''}</span>
                </div>
                <div className="mt-2 rounded-md border border-[var(--color-line)] bg-[var(--color-panel-2)] p-3">
                  <div className="text-[11px] uppercase tracking-[.14em] text-[var(--color-ink-dim)] mb-1.5">Why this score</div>
                  {overall.signature && <div className={`inline-block mb-2 px-2 py-[2px] rounded text-[12px] font-medium bg-lvl-${overall.level} lvl-${overall.level}`}>Script pattern: {overall.signature}</div>}
                  <ul className="space-y-1 text-[13px]">
                    {(current && selected !== null ? current.explain : overall.explain).map((e, i) => <li key={i} className="flex gap-2"><span className="text-[var(--color-amber)]">›</span><span>{e}</span></li>)}
                  </ul>
                </div>
              </div>
            </div>
            <div className="border-t border-[var(--color-line)]">
              <div className="px-3 pt-2 flex items-center justify-between text-[11px] uppercase tracking-[.14em] text-[var(--color-ink-dim)]"><span>Urgency timeline · 3 s windows</span>{selected !== null && <button className="text-[var(--color-amber)] normal-case tracking-normal" onClick={() => setSelected(null)}>follow live</button>}</div>
              <Timeline windows={windows} selected={selected} onSelect={setSelected} />
            </div>
          </div>

          <div className="panel flex-1 flex flex-col min-h-[220px]">
            <div className="panel-h">
              <span>Transcript · whisper (hi/en)</span>
              <label className="toggle"><input type="checkbox" checked={redact} onChange={(e) => setRedact(e.target.checked)} />redact PII {redact ? '(on)' : '(off — operator override)'}</label>
            </div>
            <div className="flex-1 min-h-0"><Transcript windows={windows} selected={selected} redact={redact} /></div>
          </div>
        </section>

        {/* right: signals */}
        <aside className="col-span-12 lg:col-span-3 flex flex-col gap-3 min-h-0">
          <div className="panel">
            <div className="panel-h"><span>Acoustic emotion</span><span className="mono">{current ? `${Math.round(current.distress * 100)} distress` : ''}</span></div>
            <EmotionBars probs={current?.emotion ?? null} />
          </div>
          <div className="panel">
            <div className="panel-h"><span>Prosody</span><span className="mono">arousal {current ? Math.round(current.prosody.arousal * 100) : 0}</span></div>
            <div className="p-3 grid grid-cols-2 gap-2 text-[12px]">
              {[['pitch', `${current?.prosody.f0_mean ?? 0} Hz`], ['pitch σ', `${current?.prosody.f0_std ?? 0} Hz`], ['energy', `${current?.prosody.rms_mean ?? 0}`], ['voiced', `${Math.round((current?.prosody.voiced_ratio ?? 0) * 100)}%`]].map(([k, v]) => (
                <div key={k} className="rounded-md bg-[var(--color-panel-2)] px-2.5 py-2"><div className="text-[var(--color-ink-mute)] text-[10px] uppercase tracking-[.12em]">{k}</div><div className="mono text-[14px] mt-[2px]">{v}</div></div>
              ))}
            </div>
          </div>
          <div className="panel flex-1">
            <div className="panel-h"><span>Fraud-script cues</span><span className="mono">{current ? Math.round(current.fraud.score * 100) : 0}</span></div>
            <div className="p-3 space-y-[7px]">
              {['impersonation', 'threat', 'payment', 'urgency', 'secrecy', 'victim_loss'].map((k) => {
                const v = current?.fraud.categories[k] ?? 0
                return (
                  <div key={k} className="flex items-center gap-2 text-[12px]">
                    <span className="w-24 text-[var(--color-ink-dim)]">{k.replace('_', ' ')}</span>
                    <div className="flex-1 h-[6px] rounded bg-[#17212b] overflow-hidden"><div className="h-full rounded bg-[var(--color-amber)]" style={{ width: `${Math.round(v * 100)}%`, transition: 'width .4s' }} /></div>
                    <span className="mono w-8 text-right text-[var(--color-ink-dim)]">{Math.round(v * 100)}</span>
                  </div>
                )
              })}
              <div className="pt-2 flex flex-wrap gap-1">
                {Array.from(new Set((current?.fraud.matches ?? []).map((m) => m.term.toLowerCase()))).slice(0, 12).map((t) => <span key={t} className="mono text-[11px] px-1.5 py-[2px] rounded bg-white/[.05] border border-[var(--color-line)]">{t}</span>)}
              </div>
            </div>
          </div>
          {err && <div className="panel p-3 text-[12px] text-[var(--color-red)]">{err}</div>}
        </aside>
      </main>
    </div>
  )
}
