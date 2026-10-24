# Pilot and evaluation protocol

Purpose: find out, with real calls and independent labels, whether AwaazAlert helps a 1930 centre prioritise urgent
calls better than what it already does, **before anyone relies on it**. Everything measured so far in this repository is
synthetic (see `README.md`, "Stress test"); none of it can answer that question.

The thresholds below are **proposals** to agree with the helpline's owners and a domain expert before data collection
starts. Pre-registering them is the point: it stops the success criteria being chosen after seeing the results.

## 0. Approvals (nothing starts without these)

1. Written authority from the helpline owner for the specific use (evaluation, shadow mode, advisory mode).
2. Data-protection impact assessment and a named responsible officer; legal basis and caller notice agreed.
3. Security review of the deployment (docs/SECURITY.md "Before go-live").
4. A secure analysis room / on-premises host. Raw audio never leaves the agency's environment.

## 1. Phases

| phase | what happens | operators see AwaazAlert? | exit criterion |
|---|---|---|---|
| A. Retrospective | already-recorded calls, with permission, are scored offline (`/analyze`); 2 reviewers label them | no | labelled set of N calls, annotator agreement reached |
| B. Shadow | live calls are scored in the background for 4+ weeks; scores are logged against what the operators actually did | **no** | metrics below computed on live traffic |
| C. Advisory | priority queue shown to operators; operators give verdicts with the feedback buttons | yes (advice only, human decides) | go/no-go review |

Never skip B. Showing a ranking to operators changes their behaviour, which makes later comparison unfair.

## 2. Labels (two independent reviewers, third adjudicates)

Per call: `scam_script_present` (Y/N + type), `victim_loss_reported` (Y/N, rough amount band), `needs_immediate_pickup`
(urgency tier 0–3 defined by the centre's own SOP with worked examples), `language(s)`, `audio_quality` (good / telephone /
poor). Report **inter-annotator agreement** (Cohen's kappa; target >= 0.7 on urgency tier). If reviewers cannot agree,
the label is the problem, not the model.

## 3. Sample size

To estimate recall on urgent calls with a 95% interval of about +/-5 points at 90% recall you need roughly 140 urgent
calls; with ~10% prevalence that is ~1,400 calls, and double that if you want to report by language. Plan 3,000+ calls
for phase A. Report the confidence interval, never the bare number.

## 4. Metrics (all computed per language, per audio-quality band, and overall)

* Recall of tier-3 (immediate) calls within the top-K of the queue, K = the centre's real pickup capacity.
* **False alerts per 100 calls** (alert = level >= medium) and operator minutes wasted on them.
* Time-to-prioritisation: how much earlier tier-3 calls are picked up vs. the baseline.
* Calibration: of calls scored 60-79, what fraction are tier >= 2 by the labels? A score nobody can interpret is not a score.
* Operator agreement from the feedback buttons (`python server/export_feedback.py data/feedback.db`), by level.
* Failure review: read every missed tier-3 call. The misses decide the roadmap.

Compare three arms on the **same** calls: (1) human-only triage as practised, (2) a plain keyword alarm, (3) AwaazAlert.
The repo's stress test already shows a keyword alarm out-recalling the fused score on synthetic scams; the real-call
comparison decides whether that holds.

## 5. Proposed go / no-go (to agree beforehand)

| criterion | proposal |
|---|---|
| recall on tier-3 calls (lower CI bound) | >= 85% within the centre's pickup capacity, and not worse than the keyword alarm |
| false alerts | <= 20 per 100 calls |
| fairness | no language / audio-quality band more than 10 points below the overall recall |
| operators | >= 70% "agree" verdicts on level >= high, and no safety-critical miss left unexplained |
| capacity | sustains the centre's peak concurrent lines on the planned hardware (`bench_capacity.py`) |
| security | audit findings closed, redaction miss rate on real ASR output documented |

No-go is a valid, useful outcome: it says what to fix (data, models, languages) before trying again.

## 6. Things this build cannot do yet (so the pilot must plan around them)

* Only **Hindi/English** transcription and scam lexicon. 1930 is national; callers speak Tamil, Bengali, Marathi, Telugu and
  more. Either restrict the pilot to Hindi/English centres or build the other languages first.
* Emotion models are untested on real Hindi call audio, and the speaker baseline assumes one speaker per stream.
* Capacity on the author's laptop GPU is small (see `docs/DEPLOYMENT.md`); a centre's peak concurrency needs real hardware sizing.
* Scoring is advisory; there is no integration with case-management systems or the I4C backend.
