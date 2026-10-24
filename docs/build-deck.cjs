// Builds docs/AwaazAlert-VecnaVerse.pptx — the mandatory 5 slides — in the dashboard's own visual language:
// dark indigo console, a cream "paper strip" card, ink red-orange for the signal, carbon blue for operator marks.
//   node docs/build-deck.cjs      (run from repo root; pptxgenjs comes from web/node_modules)
const path = require('path')
const fs = require('fs')
const pptxgen = require(path.join(__dirname, '..', 'web', 'node_modules', 'pptxgenjs'))

const C = { console: '141A2E', console2: '1B2340', bezel: '2D3659', paper: 'EFE6D2', paper2: 'E6DBC3', ink: 'E2492F', inkDark: 'A93420', carbon: '2B5BD7', stamp: 'B3261E', text: 'E9ECF4', dim: '9AA3B5', mute: '6B7489', onPaper: '2A2419', onPaperDim: '7A6F5A', ok: '3F9D6E' }
const F = { title: 'Cambria', body: 'Calibri', data: 'Courier New' }
const shots = path.join(__dirname, '..', 'web', 'shots')
const img = (n) => path.join(shots, n)

const pres = new pptxgen()
pres.layout = 'LAYOUT_WIDE' // 13.33 x 7.5
pres.title = 'AwaazAlert — VecnaVerse 2026'

function base(slide, n, title, kicker) {
  slide.background = { color: C.console }
  // wordmark + slide index, top-left; mandatory slide title top-right in the eyebrow
  slide.addText([{ text: 'Awaaz', options: { color: C.text } }, { text: 'Alert', options: { color: C.ink, italic: true } }], { x: 0.5, y: 0.35, w: 3, h: 0.45, fontFace: F.title, fontSize: 22, margin: 0 })
  slide.addText(`${n} / 5  ·  ${kicker}`, { x: 4.2, y: 0.42, w: 8.6, h: 0.35, fontFace: F.data, fontSize: 10, color: C.dim, align: 'right', margin: 0 })
  slide.addText(title, { x: 0.5, y: 0.9, w: 12.3, h: 0.7, fontFace: F.title, fontSize: 32, color: C.text, margin: 0 })
}
const paper = (slide, x, y, w, h) => slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: C.paper }, line: { color: C.paper2, width: 0.75 } })
const bezel = (slide, x, y, w, h) => slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: C.console2 }, line: { color: C.bezel, width: 0.75 } })
const label = (slide, t, x, y, w, onPaper = false) => slide.addText(t.toUpperCase(), { x, y, w, h: 0.25, fontFace: F.body, fontSize: 9, bold: true, charSpacing: 2, color: onPaper ? C.onPaperDim : C.dim, margin: 0 })
const bullets = (slide, items, x, y, w, h, opts = {}) => slide.addText(items.map((t, i) => ({ text: t, options: { bullet: { code: '2014' }, breakLine: i < items.length - 1, paraSpaceAfter: 6 } })), { x, y, w, h, fontFace: F.body, fontSize: opts.size || 13, color: opts.color || C.text, valign: 'top', margin: 0, ...opts })

// ------------------------------------------------------------------ 1 · Problem statement and understanding
{
  const s = pres.addSlide()
  base(s, 1, 'Problem statement and understanding', 'PS2 · Real-time speech emotion analysis for cybercrime investigation')
  s.addText('Operators on the 1930 cybercrime helpline hear fear all day and cannot hear it any more.', { x: 0.5, y: 1.75, w: 6.3, h: 1.1, fontFace: F.title, fontSize: 20, color: C.text, margin: 0, valign: 'top' })
  bullets(s, [
    'One operator, many lines: a victim mid-"digital arrest", a fraudster being baited, a routine status query — all at once.',
    'PS2 asks for real-time emotional signals to prioritise calls, treated as indicative, never as evidence.',
    'Our reading: emotion alone is weak on Indian call audio — no Hindi SER benchmark exists; real call-centre accuracy is 55–65 %.',
    'What is reliable is the script. Indian scams follow fixed scripts: impersonation → threat → secrecy → payment. So we fuse voice with words.',
  ], 0.5, 2.9, 6.3, 3.6)
  // paper card with the three questions the operator actually has
  paper(s, 7.2, 1.75, 5.6, 4.9)
  label(s, 'what the operator needs, in order', 7.5, 1.95, 5, true)
  const q = [['Which line first?', 'a score that orders the queue'], ['Why that one?', 'measured cues, not a black box'], ['Which playbook?', 'the scam named: digital arrest, KYC block, task scam…'], ['Am I allowed to?', 'nothing stored, PII hidden, "indicative only" on screen']]
  q.forEach(([h, d], i) => {
    s.addText(h, { x: 7.5, y: 2.35 + i * 1.05, w: 5, h: 0.4, fontFace: F.title, fontSize: 18, color: C.onPaper, margin: 0 })
    s.addText(d, { x: 7.5, y: 2.75 + i * 1.05, w: 5, h: 0.4, fontFace: F.body, fontSize: 12.5, color: C.onPaperDim, margin: 0 })
  })
  s.addText('Team: Ankit Gupta · solo build, 24 h', { x: 0.5, y: 6.85, w: 6, h: 0.3, fontFace: F.data, fontSize: 9, color: C.mute, margin: 0 })
  s.addNotes('Frame the problem from the operator chair. Emotion is weak on Hindi audio; scripts are strong — that is the thesis.')
}

// ------------------------------------------------------------------ 2 · Technical approach
{
  const s = pres.addSlide()
  base(s, 2, 'Technical approach', 'three independent signals, one explainable score')
  // pipeline diagram drawn with shapes: audio -> 3 s window + 9 s context -> three branches -> fusion
  const box = (x, y, w, h, t, sub, fill = C.console2, col = C.text) => {
    s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: C.bezel, width: 0.75 } })
    s.addText([{ text: t, options: { bold: true, breakLine: true } }, { text: sub, options: { fontSize: 10, color: fill === C.paper ? C.onPaperDim : C.dim } }], { x: x + 0.12, y: y + 0.08, w: w - 0.24, h: h - 0.16, fontFace: F.body, fontSize: 12.5, color: col, margin: 0, valign: 'middle' })
  }
  // a LINE's box must have positive w/h; direction comes from flipH/flipV, otherwise PowerPoint refuses the file
  const arrow = (x1, y1, x2, y2) => s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.max(0.02, Math.abs(x2 - x1)), h: Math.max(0.02, Math.abs(y2 - y1)), flipH: x2 < x1, flipV: (y2 < y1) !== (x2 < x1), line: { color: C.dim, width: 1.25, endArrowType: 'triangle' } })
  box(0.5, 2.0, 2.2, 0.9, 'Call audio', '16 kHz mono · mic / telephony / file')
  box(0.5, 3.3, 2.2, 0.9, '3 s window', '+ 9 s rolling context')
  arrow(1.6, 2.9, 1.6, 3.3)
  box(3.6, 1.85, 3.3, 0.95, 'Voice · emotion2vec+', 'fear / sad / anger probabilities (FunASR)')
  box(3.6, 3.05, 3.3, 0.95, 'Prosody · librosa', 'pitch σ, energy, voicing — relative to this caller\'s own baseline')
  box(3.6, 4.25, 3.3, 0.95, 'Words · whisper large-v3-turbo', 'hi/en pinned, repetition guards → Hinglish fraud-script lexicon → named scam')
  ;[1.85, 3.05, 4.25].forEach((y) => arrow(2.7, 3.75, 3.6, y + 0.47))
  s.addShape(pres.shapes.RECTANGLE, { x: 7.8, y: 2.3, w: 2.6, h: 2.1, fill: { color: C.paper }, line: { color: C.paper2, width: 0.75 } })
  s.addText([{ text: 'urgency 0–100', options: { bold: true, breakLine: true, fontSize: 14 } }, { text: '0.40 distress\n0.20 arousal\n0.30 fraud script\n0.10 speech rate', options: { fontFace: F.data, fontSize: 10.5 } }], { x: 7.95, y: 2.4, w: 2.4, h: 1.9, fontFace: F.body, color: C.onPaper, margin: 0, valign: 'top' })
  ;[1.85, 3.05, 4.25].forEach((y) => arrow(6.9, y + 0.47, 7.8, 3.35))
  box(10.9, 2.3, 1.95, 2.1, 'Operator', 'queue by urgency · why it lit up · named script · redacted transcript', C.console2)
  arrow(10.4, 3.35, 10.9, 3.35)
  bullets(s, [
    'Call level = max(peak-weighted windows, whole-transcript script scan). A named script floors the call at medium: the pattern is actionable whatever the voice does.',
    'Every line in "why this line lit up" is generated from a measured value — pitch σ 72 Hz, cues: cbi, parcel, arrest — never a template.',
    'FastAPI + WebSocket streaming, React/Vite dashboard. Audio is processed in memory and discarded; transcripts are PII-redacted by default.',
  ], 0.5, 5.5, 12.3, 1.5, { size: 12 })
  s.addNotes('Walk the diagram left to right. Stress speaker-relative prosody and the whole-call script scan.')
}

// ------------------------------------------------------------------ 3 · Feasibility & viability
{
  const s = pres.addSlide()
  base(s, 3, 'Feasibility and viability', 'measured on the bundled calls · python server/eval.py')
  const rows = [
    [{ text: 'sample (synthetic, edge-tts)', options: { bold: true } }, { text: 'urgency', options: { bold: true } }, { text: 'level', options: { bold: true } }, { text: 'named script', options: { bold: true } }, { text: 'latency', options: { bold: true } }],
    ['Digital arrest — scammer', '64', 'high', 'Digital arrest', '0.75 s'],
    ['Victim calling after loss', '65', 'high', 'Digital arrest (as described)', '0.52 s'],
    ['Bank KYC / OTP — scammer', '54', 'medium', 'Remote-access takeover', '0.51 s'],
    ['Part-time task scam (English)', '50', 'medium', 'Task / investment scam', '0.37 s'],
    ['Routine status query — control', '16', 'low', '—', '0.50 s'],
  ]
  s.addTable(rows, { x: 0.5, y: 1.8, w: 7.6, colW: [2.7, 0.9, 0.9, 2.2, 0.9], fontFace: F.body, fontSize: 11.5, color: C.onPaper, fill: { color: C.paper }, border: { type: 'solid', color: C.paper2, pt: 0.75 }, rowH: 0.42, align: 'left', valign: 'middle' })
  s.addText('control lowest: PASS · real-time factor 0.13–0.25 on one RTX 4060 laptop GPU', { x: 0.5, y: 4.45, w: 7.6, h: 0.3, fontFace: F.data, fontSize: 10, color: C.ok, margin: 0 })
  // big stats
  const stat = (x, big, small) => { s.addText(big, { x, y: 4.95, w: 2.4, h: 0.8, fontFace: F.data, fontSize: 34, bold: true, color: C.ink, margin: 0 }); s.addText(small, { x, y: 5.75, w: 2.4, h: 0.5, fontFace: F.body, fontSize: 11, color: C.dim, margin: 0 }) }
  stat(0.5, '4×', 'scam vs control separation')
  stat(3.1, '< 1 s', 'per 3-second window')
  stat(5.7, '0 bytes', 'of audio written to disk')
  // honest limits on paper
  paper(s, 8.5, 1.8, 4.3, 4.6)
  label(s, 'honest limits', 8.75, 2.0, 4, true)
  bullets(s, [
    'Demo calls are synthetic: flat affect, distress 0.0–0.11 on every clip. They prove the pipeline and the script path, not emotion accuracy.',
    'No public Hindi SER benchmark exists; the voice branch needs consented real recordings before any accuracy claim.',
    'One speaker per stream — no diarisation yet.',
    'Whisper still mishears some Hinglish; the lexicon carries ASR variants.',
  ], 8.75, 2.4, 3.9, 3.9, { size: 11.5, color: C.onPaper })
  s.addNotes('Be upfront: the numbers prove real-time + script separation. Emotion accuracy is unproven on Hindi — say so before the judges do.')
}

// ------------------------------------------------------------------ 4 · Impact & benefit
{
  const s = pres.addSlide()
  base(s, 4, 'Impact and benefit', 'for the operator, the victim, and the cyber cell')
  s.addImage({ path: img('02-replay-digital-arrest.png'), x: 0.5, y: 1.8, w: 7.0, h: 4.375, rounding: false })
  s.addText('The register: pen trace of urgency, ink ticks for cues, the scam stamped by name.', { x: 0.5, y: 6.25, w: 7, h: 0.3, fontFace: F.body, fontSize: 10, italic: true, color: C.dim, margin: 0 })
  const rowsI = [
    ['Minutes matter', 'A victim whose money is still in transit reaches the top of the queue; bank freeze requests go out sooner.'],
    ['A named playbook', 'Digital arrest → hang up, no transfer, file NCRP. KYC block → call the bank\'s number, not the caller.'],
    ['Explainable, not oracular', 'The operator sees which cues fired and how the voice moved against its own baseline — and can disagree.'],
    ['Deployable where the data is', 'On-prem at a state cyber cell: nothing stored, PII redacted, "indicative only" on every screen.'],
  ]
  rowsI.forEach(([h, d], i) => {
    s.addShape(pres.shapes.OVAL, { x: 7.9, y: 1.85 + i * 1.1, w: 0.42, h: 0.42, fill: { color: C.ink }, line: { color: C.ink } })
    s.addText(String(i + 1), { x: 7.9, y: 1.85 + i * 1.1, w: 0.42, h: 0.42, fontFace: F.data, fontSize: 12, bold: true, color: 'FFF4EE', align: 'center', valign: 'middle', margin: 0 })
    s.addText(h, { x: 8.5, y: 1.8 + i * 1.1, w: 4.3, h: 0.35, fontFace: F.title, fontSize: 16, color: C.text, margin: 0 })
    s.addText(d, { x: 8.5, y: 2.15 + i * 1.1, w: 4.3, h: 0.7, fontFace: F.body, fontSize: 11.5, color: C.dim, margin: 0, valign: 'top' })
  })
  s.addNotes('Impact is time-to-triage and a playbook per scam. Keep the responsible-AI point explicit.')
}

// ------------------------------------------------------------------ 5 · Comparison / unique feature
{
  const s = pres.addSlide()
  base(s, 5, 'Comparison with existing platforms — our unique feature', 'what exists · what a typical SER demo does · what AwaazAlert adds')
  const col = (x, w, head, items, fill, color, dim) => {
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.8, w, h: 4.3, fill: { color: fill }, line: { color: fill === C.paper ? C.paper2 : C.bezel, width: 0.75 } })
    s.addText(head, { x: x + 0.25, y: 2.0, w: w - 0.5, h: 0.5, fontFace: F.title, fontSize: 17, color, margin: 0 })
    bullets(s, items, x + 0.25, 2.6, w - 0.5, 3.4, { size: 11.5, color: dim })
  }
  col(0.5, 3.9, 'Existing platforms', [
    'Uniphore, Cogito, Nemesysco: enterprise call-centre emotion analytics — English, black-box, no fraud-script awareness.',
    '1930 today: Goa Police AI voice assistant does complaint intake only; MHA ordered an AI upgrade (Jun 2026) — no distress or priority layer.',
    'Academic SER: English acted corpora (IEMOCAP, RAVDESS); 70–80 % lab, 55–65 % on real calls.',
  ], C.console2, C.text, C.dim)
  col(4.7, 3.9, 'Typical hackathon SER', [
    'Upload one clip → one emotion label.',
    'English benchmark voices.',
    'No transcript, no context, no queue.',
    'A sentence about privacy.',
  ], C.console2, C.text, C.dim)
  col(8.9, 3.9, 'AwaazAlert', [
    'Fusion: voice + prosody vs the caller\'s own baseline + Hinglish fraud-script detection with named patterns.',
    'Live streaming across lines, 3 s windows, priority queue, strip-chart register.',
    'Explanation built only from measured features.',
    'Redaction on by default, nothing stored, "indicative only" baked into the UI.',
  ], C.paper, C.onPaper, C.onPaper)
  s.addText('github.com/Anki1004/awaaz-alert', { x: 0.5, y: 6.9, w: 12.3, h: 0.3, fontFace: F.data, fontSize: 10, color: C.mute, margin: 0 })
  s.addNotes('Close on the unique feature: script-aware fusion with explanations, not a better emotion classifier.')
}

const out = path.join(__dirname, 'AwaazAlert-VecnaVerse.pptx')
pres.writeFile({ fileName: out }).then(() => console.log('wrote', out, fs.statSync(out).size, 'bytes'))
