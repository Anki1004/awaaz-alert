// Types mirror server/pipeline.py WindowResult + summarize().
export type Level = 'low' | 'medium' | 'high' | 'critical'

export interface Fraud {
  score: number
  categories: Record<string, number>
  matches: { category: string; term: string; start: number; end: number }[]
  signature: string | null
}

export interface WindowResult {
  t_start: number
  t_end: number
  emotion: Record<string, number>
  prosody: { f0_mean: number; f0_std: number; rms_mean: number; rms_peak: number; voiced_ratio: number; arousal: number }
  transcript: string
  transcript_redacted: string
  language: string | null
  fraud: Fraud
  distress: number
  urgency: number
  level: Level
  explain: string[]
  latency_ms: number
}

export interface Overall {
  urgency: number
  level: Level
  signature: string | null
  explain: string[]
  transcript?: string
  transcript_redacted?: string
  avg_latency_ms?: number
}

export interface Sample { id: string; file: string; title: string; kind: string; note: string }

export interface Health { ready: boolean; device?: string; whisper?: string; emotion?: string }

// The operator key lives in sessionStorage only (gone when the tab closes) and is sent as a Bearer header /
// WebSocket subprotocol. In production put the console behind your SSO proxy and let it inject the header instead.
const KEY = 'awaaz-operator-key'
export const getKey = () => { try { return sessionStorage.getItem(KEY) ?? '' } catch { return '' } }
export const setKey = (k: string) => { try { k ? sessionStorage.setItem(KEY, k) : sessionStorage.removeItem(KEY) } catch { /* private mode */ } }
const authH = (): Record<string, string> => (getKey() ? { Authorization: `Bearer ${getKey()}` } : {})

export type Verdict = 'agree' | 'too_high' | 'too_low' | 'missed_scam' | 'false_alarm'

async function failure(r: Response): Promise<{ error: string }> {
  const j = await r.json().catch(() => ({} as { detail?: string }))
  if (r.status === 401) return { error: 'Operator key missing or rejected: enter a valid key (top right).' }
  if (r.status === 429) return { error: 'Too many requests: wait a moment.' }
  if (r.status === 413) return { error: 'Recording is larger than this server accepts.' }
  return { error: (j as { detail?: string }).detail ?? `Server error (${r.status}).` }
}

export const api = {
  health: () => fetch('/api/health').then((r) => r.json() as Promise<Health>),
  samples: () => fetch('/api/samples').then((r) => (r.ok ? (r.json() as Promise<Sample[]>) : [])),
  analyze: async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch('/api/analyze', { method: 'POST', body: fd, headers: authH() })
    if (!r.ok) return failure(r)
    return r.json() as Promise<{ duration: number; windows: WindowResult[]; overall: Overall } | { error: string }>
  },
  feedback: async (body: { verdict: Verdict; scope?: 'window' | 'call'; session_id?: string | null; line_id?: string | null; urgency?: number; level?: string; signature?: string | null; language?: string | null }) => {
    const r = await fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authH() }, body: JSON.stringify(body) })
    return r.ok ? { ok: true as const } : failure(r)
  },
}

export type WsEvent =
  | { type: 'hello'; window_s: number; duration?: number; session?: string }
  | { type: 'lag'; dropped_s: number }
  | { type: 'window'; data: WindowResult; overall: Overall }
  | { type: 'done'; overall: Overall }
  | { type: 'reset' }
  | { type: 'error'; message: string }

export function wsUrl(path: string) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}

export function openWs(path: string) {
  const k = getKey()
  return k ? new WebSocket(wsUrl(path), [`bearer.${k}`]) : new WebSocket(wsUrl(path))
}

export function closeReason(code: number): string | null {
  if (code === 1008) return 'Operator key missing or rejected: enter a valid key (top right).'
  if (code === 1013) return 'All analysis slots are busy: try again in a moment, or use another console.'
  return null
}
