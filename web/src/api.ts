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

export const api = {
  health: () => fetch('/api/health').then((r) => r.json() as Promise<Health>),
  samples: () => fetch('/api/samples').then((r) => r.json() as Promise<Sample[]>),
  analyze: async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch('/api/analyze', { method: 'POST', body: fd })
    return r.json() as Promise<{ duration: number; windows: WindowResult[]; overall: Overall } | { error: string }>
  },
}

export type WsEvent =
  | { type: 'hello'; window_s: number; duration?: number }
  | { type: 'window'; data: WindowResult; overall: Overall }
  | { type: 'done'; overall: Overall }
  | { type: 'reset' }
  | { type: 'error'; message: string }

export function wsUrl(path: string) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}
