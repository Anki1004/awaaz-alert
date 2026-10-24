# web

React + Vite + Tailwind v4 operator dashboard. `npm run dev` proxies `/api` and `/ws` to the FastAPI server on :8765.

- `src/App.tsx` — call queue, live view (gauge, scope, explanation, timeline), transcript with redaction, signal panels
- `src/audio.ts` — mic → 16 kHz int16 PCM frames over WebSocket
- `src/components/` — Gauge, Timeline, Transcript, EmotionBars, Scope
- `e2e.mjs` — Playwright check against the running server (`node e2e.mjs`)
