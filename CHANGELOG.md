# Changelog

## 0.2.0 — `production` branch
- Auth (API keys), rate limits, size/frame/idle caps, admission control; production-mode config validation.
- Server-side transcript redaction with explicit reveal permission.
- Hash-chained audit log with verifier; operator feedback store + CSV export + console buttons.
- `/ws/ingest` telephony endpoint (G.711 / PCM, 8–48 kHz), `/ready`, `/metrics`.
- Language is pinned from >= 5 s of audio instead of the first window's auto-detect.
- Loss-report floor (medium) and past-tense loss lexicon; honest stress/held-out evaluation vs keyword baseline.
- Dockerfile, compose, nginx template (untested), model prefetch script.
- Tests (48), narrowband eval, capacity benchmark; SECURITY / DEPLOYMENT / PILOT / MODEL-CARD docs.

## 0.1.0 — hackathon build (`main`)
- Live distress + fraud-script triage prototype, strip-chart console, five synthetic demo calls.
