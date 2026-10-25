import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, wsUrl, type Health, type Overall, type Sample, type WindowResult, type WsEvent } from './api'
import { startMic, type MicHandle } from './audio'
import { StripChart } from './components/StripChart'
import { Needle, Vu } from './components/Meter'
import { Transcript } from './components/Transcript'
import { Scope } from './components/Scope'
import { RecordedReplay, REPO_URL, STATIC_DEMO } from './demo'

type Mode = 'idle' | 'live' | 'replay' | 'file'
interface CallRow { id: string; title: string; kind: string; overall: Overall | null; windows: WindowResult[]; duration?: number; running?: boolean }
const EMPTY: Overall = { urgency: 0, level: 'low', signature: null, explain: ['Nothing on the line yet.'] }

const EMO = [['fearful', 'Fear', 'var(--color-stamp)'], ['sad', 'Sadness', 'var(--color-carbon)'], ['angry', 'Anger', 'var(--color-ink)'], ['surprised', 'Surprise', '#8d6bd9'], ['neutral', 'Neutral', '#6b7489'], ['happy', 'Happy', 'var(--color-ok)']] as const
const CUES = [['impersonation', 'Impersonation', 'var(--color-ink)'], ['threat', 'Threat', 'var(--color-stamp)'], ['payment', 'Payment ask', 'var(--color-carbon)'], ['urgency', 'Urgency', '#9aa3b5'], ['secrecy', 'Secrecy', '#9aa3b5'], ['victim_loss', 'Victim loss', 'var(--color-ok)']] as const

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [samples, setSamples] = useState<Sample[]>([])
  const [mode, setMode] = useState<Mode>('idle')
  const [windows, setWindows] = useState<WindowResult[]>([])
  const [overall, setOverall] = useState<Overall>(EMPTY)
  const [selected, setSelected] = useState<number | null>(null)
  const [redact, setRedact] = useState(true)
  const [queue, setQueue] = useState<CallRow[]>([])
  const [activeId, setActiveId] = useState('live')
  const [err, setErr] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const micRef = useRef<MicHandle | null>(null)
  const [, tick] = useState(0)

  useEffect(() => { const poll = () => api.health().then(setHealth).catch(() => setHealth(null)); poll(); const t = setInterval(poll, 4000); return () => clearInterval(t) }, [])
  useEffect(() => { api.samples().then(setSamples).catch(() => setSamples([])) }, [])
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 150); return () => clearInterval(t) }, [])

  const current = useMemo(() => (selected !== null ? windows[selected] : windows[windows.length - 1]) ?? null, [windows, selected])

  const upsert = useCallback((row: CallRow) => setQueue((q) => [...q.filter((r) => r.id !== row.id), row].sort((a, b) => (b.overall?.urgency ?? -1) - (a.overall?.urgency ?? -1))), [])
  const stopAll = useCallback(() => { wsRef.current?.close(); wsRef.current = null; micRef.current?.stop(); micRef.current = null; setMode('idle') }, [])
  const resetView = () => { setWindows([]); setOverall(EMPTY); setSelected(null); setErr(null) }

  const onEvent = (id: string, title: string, kind: string) => (ev: WsEvent) => {
    if (ev.type === 'window') { setWindows((w) => { const next = [...w, ev.data]; upsert({ id, title, kind, overall: ev.overall, windows: next, running: true }); return next }); setOverall(ev.overall) }
    else if (ev.type === 'done') { setOverall(ev.overall); setQueue((q) => q.map((r) => (r.id === id ? { ...r, overall: ev.overall, running: false } : r))); setMode('idle') }
    else if (ev.type === 'error') setErr(ev.message)
  }

  const startLive = async () => {
    if (STATIC_DEMO) { setErr(`Live microphone analysis runs on the local GPU server (faster-whisper + emotion2vec+), not on this hosted page. Clone ${REPO_URL} to try it live.`); return }
    stopAll(); resetView(); setActiveId('live')
    try {
      const ws = new WebSocket(wsUrl('/ws/live')); wsRef.current = ws
      ws.onmessage = (m) => onEvent('live', 'Line 1 · live', 'live')(JSON.parse(m.data))
      ws.onclose = () => { micRef.current?.stop(); micRef.current = null; setMode((mo) => (mo === 'live' ? 'idle' : mo)) }
      await new Promise<void>((res, rej) => { ws.onopen = () => res(); ws.onerror = () => rej(new Error('Could not reach the analysis server.')) })
      micRef.current = await startMic((pcm) => { if (ws.readyState === 1) ws.send(pcm) })
      upsert({ id: 'live', title: 'Line 1 · live', kind: 'live', overall: null, windows: [], running: true }); setMode('live')
    } catch (e) { setErr((e as Error).message); stopAll() }
  }
  const endLive = () => { wsRef.current?.send(JSON.stringify({ cmd: 'flush' })); setTimeout(stopAll, 400); setQueue((q) => q.map((r) => (r.id === 'live' ? { ...r, running: false } : r))) }
  const replay = (s: Sample, speed = 1) => {
    stopAll(); resetView(); setActiveId(s.id)
    const ws = STATIC_DEMO
      ? (new RecordedReplay(s.id, s.file, speed) as unknown as WebSocket)
      : new WebSocket(wsUrl(`/ws/replay?sample=${encodeURIComponent(s.file)}&speed=${speed}`))
    wsRef.current = ws
    ws.onmessage = (m) => onEvent(s.id, s.title, s.kind)(JSON.parse(m.data))
    ws.onerror = () => setErr('Replay connection failed.')
    upsert({ id: s.id, title: s.title, kind: s.kind, overall: null, windows: [], running: true }); setMode('replay')
  }
  const scoreAll = async () => {
    for (const s of samples) {
      upsert({ id: s.id, title: s.title, kind: s.kind, overall: null, windows: [], running: true })
      const res = await api.analyzeSample(s)
      if ('error' in res) { setErr(res.error); continue }
      upsert({ id: s.id, title: s.title, kind: s.kind, overall: res.overall, windows: res.windows, duration: res.duration, running: false })
    }
  }
  const onFile = async (f: File | null) => {
    if (!f) return
    stopAll(); resetView(); setActiveId(f.name); setMode('file')
    upsert({ id: f.name, title: f.name, kind: 'upload', overall: null, windows: [], running: true })
    const res = await api.analyze(f)
    if ('error' in res) { setErr(res.error); setMode('idle'); return }
    setWindows(res.windows); setOverall(res.overall); setMode('idle')
    upsert({ id: f.name, title: f.name, kind: 'upload', overall: res.overall, windows: res.windows, duration: res.duration, running: false })
  }
  const openRow = (r: CallRow) => { if (r.running && r.id === activeId) return; stopAll(); setActiveId(r.id); setWindows(r.windows); setOverall(r.overall ?? EMPTY); setSelected(null) }

  const ready = !!health?.ready
  const explain = current && selected !== null ? current.explain : overall.explain
  const fraud = current?.fraud

  return (
    <div className="h-full flex flex-col console">
      {/* console header */}
      <header className="flex items-end justify-between px-5 pt-4 pb-3 border-b border-[var(--color-bezel)]">
        <div className="flex items-end gap-4">
          <div className="wordmark">Awaaz<em>Alert</em></div>
          <div className="hindi text-[20px] leading-none text-[var(--color-text-dim)] pb-[2px]">आवाज़ · १९३०</div>
          <div className="label pb-[3px] hidden md:block">call register for cybercrime helpline lines</div>
        </div>
        <div className="flex items-center gap-4 data text-[11px] text-[var(--color-text-dim)]">
          <span className="flex items-center gap-2"><i className={`inline-block w-2 h-2 rounded-full ${ready ? 'bg-[var(--color-ok)]' : health ? 'bg-[#d9a441]' : 'bg-[var(--color-bezel)]'}`} />{ready ? `ready · ${health?.device}` : health ? 'loading models…' : 'server offline'}</span>
          <span className="hidden lg:inline">{health?.whisper ?? '—'} · {health?.emotion ?? '—'}</span>
        </div>
      </header>
      <div className="px-5 py-[6px] text-[12px] text-[var(--color-text-dim)] border-b border-[var(--color-bezel)] bg-[var(--color-console-2)]">
        <span className="label mr-2 text-[var(--color-text)]">Indicative only</span> Scores order the queue; they are not evidence of anyone's intent, honesty or guilt. Audio is analysed in memory and never stored.
      </div>
      {STATIC_DEMO && (
        <div className="px-5 py-[6px] text-[12px] border-b border-[var(--color-bezel)] bg-[#2a2410] text-[#f0d79a]">
          <span className="label mr-2 !text-[#f0d79a]">Recorded demo</span> Every score here was produced by the real pipeline on an RTX 4060 and is replayed in step with the call audio — press ▶ on a sample line. Live mic and uploads need the GPU server: <a className="underline" href={REPO_URL} target="_blank" rel="noreferrer">run it from GitHub</a> · <a className="underline" href="/AwaazAlert-demo-90s.mp4" target="_blank" rel="noreferrer">watch the 90-second video</a>.
        </div>
      )}

      <main className="flex-1 min-h-0 grid grid-cols-12 gap-3 p-3">
        {/* patch panel */}
        <aside className="col-span-12 lg:col-span-2 bezel flex flex-col min-h-0">
          <div className="bezel-h"><span className="label">Lines</span><span className="data text-[11px] text-[var(--color-text-dim)]">{queue.length}</span></div>
          <div className="flex-1 overflow-y-auto">
            {queue.length === 0 && <div className="p-3 text-[12px] text-[var(--color-text-mute)]">No lines open. Start a live call or replay a sample.</div>}
            {queue.map((r) => (
              <button key={r.id} onClick={() => openRow(r)} className={`jack ${r.running ? 'live' : ''} ${activeId === r.id ? 'active' : ''}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="title text-[13px] truncate" style={{ fontVariationSettings: '"wdth" 90, "wght" 600' }}>{r.title}</span>
                  <span className={`data text-[12px] lvl-${r.overall?.level ?? 'low'}`}>{r.overall ? r.overall.urgency : r.running ? '…' : '—'}</span>
                </div>
                <div className="text-[11px] text-[var(--color-text-dim)] truncate mt-[1px]">{r.overall?.signature ?? r.kind}</div>
              </button>
            ))}
          </div>
          <div className="border-t border-[var(--color-bezel)] p-2 space-y-1.5">
            <div className="label px-1 pt-1">Sample lines</div>
            {samples.map((s) => (
              <div key={s.id} className="flex gap-1">
                <button className="btn flex-1 text-left truncate normal-case tracking-normal" style={{ textTransform: 'none', fontVariationSettings: '"wdth" 90, "wght" 500' }} disabled={!ready} onClick={() => replay(s)} title={s.note}>▶ {s.title}</button>
                <button className="btn data" disabled={!ready} onClick={() => replay(s, 3)} title="Replay at 3× speed">3×</button>
              </div>
            ))}
            <button className="btn w-full" disabled={!ready || !samples.length} onClick={scoreAll}>Score all samples</button>
          </div>
        </aside>

        {/* register */}
        <section className="col-span-12 lg:col-span-10 flex flex-col gap-3 min-h-0">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-3">
              <span className="label">{mode === 'live' ? 'Line 1 · live' : mode === 'replay' ? 'Replay' : mode === 'file' ? 'Analysing recording' : 'Standby'}</span>
              {current && <span className="data text-[11px] text-[var(--color-text-mute)]">window {current.t_start}–{current.t_end}s · {current.latency_ms} ms · {current.language ?? '–'}</span>}
            </div>
            <div className="flex items-center gap-2">
              {mode !== 'live' ? <button className="btn ink" disabled={!ready} onClick={startLive}>● Start live call</button> : <button className="btn stop" onClick={endLive}>■ End call</button>}
              <label className="btn cursor-pointer">Upload recording<input type="file" accept="audio/*,video/*" className="hidden" onChange={(e) => onFile(e.target.files?.[0] ?? null)} /></label>
              <label className="toggle ml-2"><input type="checkbox" checked={redact} onChange={(e) => setRedact(e.target.checked)} />Redact personal details {redact ? '(on)' : '(off)'}</label>
            </div>
          </div>

          {/* the strip */}
          <StripChart windows={windows} selected={selected} onSelect={setSelected} signature={overall.signature} live={mode === 'live' || mode === 'replay'} />

          <div className="grid grid-cols-12 gap-3 flex-1 min-h-0">
            {/* transcript lane */}
            <div className="col-span-12 xl:col-span-7 bezel flex flex-col min-h-[240px]">
              <div className="bezel-h"><span className="label">Transcript · whisper hi/en</span>{selected !== null && <button className="label !text-[var(--color-carbon)]" onClick={() => setSelected(null)}>follow the pen</button>}</div>
              <div className="flex-1 min-h-0 body-hi"><Transcript windows={windows} selected={selected} redact={redact} /></div>
            </div>

            {/* instrument cluster */}
            <div className="col-span-12 xl:col-span-5 flex flex-col gap-3 min-h-0">
              <div className="bezel p-3">
                <div className="flex items-start gap-3">
                  <div className="shrink-0"><Needle value={selected !== null && current ? current.urgency : overall.urgency} level={selected !== null && current ? current.level : overall.level} size={190} caption={selected !== null ? 'window' : 'triage priority'} /></div>
                  <div className="min-w-0 flex-1">
                    <div className="label mb-1.5">Why this line lit up</div>
                    <ul className="space-y-1 text-[13px] leading-snug">{explain.map((e, i) => <li key={i} className="flex gap-2"><span className="text-[var(--color-ink)]">—</span><span>{e}</span></li>)}</ul>
                    {mode === 'live' && <div className="mt-2"><Scope wave={micRef.current?.wave ?? null} active level={overall.level} /></div>}
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 flex-1 min-h-0">
                <div className="bezel p-3 space-y-2">
                  <div className="flex justify-between"><span className="label">Voice</span><span className="data text-[11px] text-[var(--color-text-dim)]">distress {current ? Math.round(current.distress * 100) : 0}</span></div>
                  {EMO.map(([k, l, c]) => <Vu key={k} label={l} value={current?.emotion[k] ?? 0} color={c} />)}
                  <div className="pt-1 grid grid-cols-3 gap-1 data text-[10px] text-[var(--color-text-dim)]">
                    <div><div className="label !text-[9px]">pitch</div>{(current?.prosody.f0_mean ?? 0).toFixed(0)} Hz</div>
                    <div><div className="label !text-[9px]">pitch σ</div>{(current?.prosody.f0_std ?? 0).toFixed(1)}</div>
                    <div><div className="label !text-[9px]">vs baseline</div>{Math.round((current?.prosody.arousal ?? 0) * 100)}</div>
                  </div>
                </div>
                <div className="bezel p-3 space-y-2">
                  <div className="flex justify-between"><span className="label">Script cues</span><span className="data text-[11px] text-[var(--color-text-dim)]">{fraud ? Math.round(fraud.score * 100) : 0}</span></div>
                  {CUES.map(([k, l, c]) => <Vu key={k} label={l} value={fraud?.categories[k] ?? 0} color={c} />)}
                  <div className="pt-1 flex flex-wrap gap-1">{Array.from(new Set((fraud?.matches ?? []).map((m) => m.term.toLowerCase()))).slice(0, 10).map((t) => <span key={t} className="data text-[10px] px-1.5 py-[2px] rounded-[2px] bg-[#0c1020] border border-[var(--color-bezel)] body-hi">{t}</span>)}</div>
                </div>
              </div>
              {err && <div className="bezel p-2 text-[12px] text-[#ffb3a4]">{err}</div>}
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
