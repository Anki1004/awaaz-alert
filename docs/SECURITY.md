# AwaazAlert security and data handling

Status: **engineering controls implemented and unit-tested; no independent security audit has been done.** A government
deployment needs one (see "Before go-live"). Nothing here is legal advice; check the legal parts with your data
protection / legal officer.

## 1. What data exists, where, for how long

| data | where it lives | retention | notes |
|---|---|---|---|
| call audio | server RAM only | last ~9 s (rolling context), then overwritten | never written to disk by this code; check the host for swap / core dumps / session recorders in your SBC |
| transcript | server RAM for the session; browser memory of the console | until the session ends | operators without reveal permission only ever receive the **redacted** text (server-side) |
| audit log `data/audit.jsonl` | disk | you set it (ship to WORM storage) | who, what, when, aggregate numbers. **No audio, no transcript, no caller identity** |
| feedback `data/feedback.db` | disk | you set it | operator verdicts + numbers (+ redacted line only if `AWAAZ_STORE_TEXT=1`) |
| API keys | environment of the server process | rotate on a schedule | compared by SHA-256 digest, constant time |

Zero retention of call content is a design property, not a switch: there is no code path that stores audio or
transcripts. `tests/test_audit.py::test_audit_never_carries_call_content_fields` guards the audit trail against
someone adding content later.

## 2. Controls implemented

| threat | control | where / test |
|---|---|---|
| unauthenticated access | Bearer API key on every HTTP and WebSocket route except `/health` and `/ready`; production refuses to start without keys | `security.py`, `config.validate()`; `test_api.py` |
| key in URLs / logs | WebSocket keys travel as subprotocol `bearer.<key>`, never as a query string | `security.ws_operator` |
| weak keys | production rejects keys under 24 characters | `config.validate()` |
| brute force / abuse | per-operator rate limit (HTTP), upload size cap, WebSocket frame cap, idle timeout | `security.RateLimiter`, `main.py` |
| resource exhaustion | admission control (`AWAAZ_MAX_SESSIONS`, close code 1013 when full), 20 s audio backlog cap with an explicit "lag" event | `main._admit`, `_stream` |
| cross-origin abuse | CORS restricted to `AWAAZ_ORIGINS`; startup fails on `*` in production | `config.validate()` |
| raw PII on the wire | server-side redaction: operators without reveal permission receive redacted transcripts, cue terms and explanations only | `main.scrub_message`; `test_server_side_redaction_*` |
| insider misuse / repudiation | every session, upload and feedback is attributed to an operator id in a hash-chained audit log | `audit.py`; `test_audit.py` |
| information leakage via API | OpenAPI/docs, demo samples and replay are disabled in production | `main.py` |
| container hardening | non-root user, read-only root filesystem, no capabilities, `no-new-privileges` | `Dockerfile`, `docker-compose.yml` (untested build) |
| transport security | TLS terminates at the reverse proxy (`deploy/nginx.conf`, HSTS, CSP, `Cache-Control: no-store`) | untested template |

## 3. Known gaps (read before trusting this with real calls)

1. **No independent audit or penetration test.**
2. **Redaction is regex-based on ASR text.** It masks digit sequences that look like phone, Aadhaar, card and OTP numbers.
   It will miss digits spoken as words ("nau aath saat ..."), misheard digits, names and addresses. Treat redacted text
   as "reduced risk", not "anonymous".
3. **Raw text exists in server RAM** and is reachable by anyone with root on the host or a debugger on the process.
4. **Static API keys.** No SSO, no rotation tooling, no per-key expiry. Prefer fronting the service with your institution's
   SSO proxy that injects the header, and keep keys out of browsers (the console's key box is a fallback for pilots).
5. **The audit hash chain detects edits, it does not prevent them.** Someone with write access to the file can rewrite it
   consistently. Ship lines to an append-only external store and anchor the latest hash where the service account
   cannot write (`audit.py` docstring).
6. **Models and Python dependencies are version-pinned but not hash-pinned.** Mirror them internally and verify checksums
   for an air-gapped install.
7. **No mutual TLS** between the telephony gateway and the server. Put them on an isolated network segment and terminate
   TLS on the proxy; add mTLS if your SBC supports it.
8. **One speaker channel per stream, no diarisation**: a stream that mixes caller and operator will be scored as one voice.
9. **Rate limits and admission state are per-process** (in memory). A multi-replica deployment needs a shared limiter.

## 4. Data-protection considerations (to confirm with your legal officer)

* The deploying agency is the data fiduciary under the Digital Personal Data Protection Act, 2023; call content here is
  personal data, and callers include victims (sometimes minors). Confirm the lawful basis, notice at call start ("calls
  are analysed by software to prioritise help"), purpose limitation (triage only), and the rules in force for
  government processing.
* The service is designed to run **on-premises or in an empanelled government cloud**: it makes no outbound calls after the
  models are cached (set `HF_HUB_OFFLINE=1`). Check data-localisation requirements for your cloud.
* A pilot on real calls needs a written authority, a data-protection impact assessment, a named responsible officer, and
  an incident process (including CERT-In reporting timelines). `docs/PILOT.md` lists the evidence to collect.

## 5. Before go-live

- [ ] Third-party security assessment by a CERT-In empanelled auditor; fix findings.
- [ ] Audit log shipped to append-only storage; latest-hash anchoring agreed.
- [ ] SSO in front, keys out of browsers, key rotation procedure written.
- [ ] Redaction recall measured on **real** ASR output from your calls, with the miss rate recorded.
- [ ] Host hardening: encrypted disk, swap disabled or encrypted, core dumps off, no session recording on the SBC fork.
- [ ] Load test on the production GPU (`server/bench_capacity.py`) and `AWAAZ_MAX_SESSIONS` set from it.
- [ ] Runbook: who is paged when `/ready` fails, when audit writes fail (`awaaz_audit_write_failures_total`), when sessions are rejected as busy.
