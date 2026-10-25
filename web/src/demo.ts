// Hosted "recorded demo" mode (build with VITE_STATIC_DEMO=1). There is no GPU server behind the static site, so the
// dashboard replays outputs that the real pipeline produced on an RTX 4060 (web/public/demo/<id>.json, captured from
// /ws/replay and /analyze), in step with the call audio. Live microphone and uploads need the local server.
import type { Overall, WindowResult, WsEvent } from './api'

export const STATIC_DEMO = import.meta.env.VITE_STATIC_DEMO === '1'
export const REPO_URL = 'https://github.com/Anki1004/awaaz-alert'

interface Recording {
  id: string
  file: string
  replay: WsEvent[]
  analyze: { duration: number; windows: WindowResult[]; overall: Overall }
}

const cache: Record<string, Promise<Recording>> = {}
export function loadRecording(id: string): Promise<Recording> {
  if (!cache[id]) cache[id] = fetch(`/demo/${encodeURIComponent(id)}.json`).then((r) => {
    if (!r.ok) throw new Error(`recording ${id} missing`)
    return r.json() as Promise<Recording>
  })
  return cache[id]
}

/** A WebSocket look-alike that plays the recorded call and emits each analysis window when the audio reaches it. */
export class RecordedReplay {
  onmessage: ((m: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  readyState = 0
  private audio: HTMLAudioElement | null = null
  private timer: number | null = null
  private closed = false

  constructor(id: string, file: string, speed = 1) {
    loadRecording(id).then((rec) => {
      if (this.closed) return
      const events = rec.replay
      const windows = events.filter((e): e is Extract<WsEvent, { type: 'window' }> => e.type === 'window')
      const done = events.find((e) => e.type === 'done')
      const hello = events.find((e) => e.type === 'hello')
      if (hello) this.emit(hello)
      this.readyState = 1
      const audio = new Audio(`/demo/${encodeURIComponent(file)}`)
      audio.playbackRate = speed
      this.audio = audio
      const start = performance.now()
      let playing = false
      audio.play().then(() => { playing = true }).catch(() => { /* autoplay blocked: fall back to the clock */ })
      let next = 0
      this.timer = window.setInterval(() => {
        // Audio time when it plays, wall clock otherwise; a window is "heard" once its last sample has played.
        const t = playing && !audio.paused ? audio.currentTime : ((performance.now() - start) / 1000) * speed
        while (next < windows.length && windows[next].data.t_end <= t + 0.05) this.emit(windows[next++])
        if (next >= windows.length && (!playing || audio.ended || t >= audio.duration - 0.05)) {
          if (done) this.emit(done)
          this.close()
        }
      }, 100)
    }).catch(() => { if (!this.closed) this.onerror?.() })
  }

  private emit(ev: WsEvent) { this.onmessage?.({ data: JSON.stringify(ev) }) }
  send() { /* nothing to send in a recording */ }
  close() {
    if (this.closed) return
    this.closed = true
    this.readyState = 3
    if (this.timer !== null) clearInterval(this.timer)
    this.audio?.pause()
    this.onclose?.()
  }
}
