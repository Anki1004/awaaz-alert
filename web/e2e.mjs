// Browser check of the dashboard against the real server. Needs both running:
//   server: python server/main.py      dashboard: npm run dev
//   node e2e.mjs            (uses the repo's playwright; set PW_CHROME to a chromium exe if browsers aren't installed)
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(process.env.PW_REQUIRE_FROM || path.join(here, 'package.json'))
const { chromium } = require('playwright')
const shots = path.join(here, 'shots'); mkdirSync(shots, { recursive: true })
const URL = process.env.APP_URL || 'http://127.0.0.1:5173'

let pass = 0, fail = 0
const ok = (n, c, extra = '') => { c ? pass++ : fail++; console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${c ? '' : '  <-- ' + extra}`) }

const browser = await chromium.launch(process.env.PW_CHROME ? { executablePath: process.env.PW_CHROME } : {})
const errors = []
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' })
const page = await ctx.newPage()
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()) })

try {
  await page.goto(URL)
  await page.getByText(/^ready · /).waitFor({ timeout: 120000 })
  ok('server reports models ready', true)
  await page.screenshot({ path: path.join(shots, '01-standby.png') })

  // replay the digital-arrest sample at 3x
  const row = page.getByRole('button', { name: /▶ Digital arrest/ })
  await row.waitFor()
  await page.getByRole('button', { name: '3×' }).first().click()
  await page.getByText(/^Replay$/).first().waitFor()
  // wait until at least 4 windows are on the timeline and the gauge is non-zero
  await page.waitForFunction(() => {
    const t = document.querySelector('[data-testid="urgency-value"]')
    return t && Number(t.textContent) > 0
  }, null, { timeout: 90000 })
  await page.waitForTimeout(12000)
  const gauge = Number(await page.getByTestId('urgency-value').textContent())
  ok('urgency gauge rises on the digital-arrest replay', gauge >= 35, `gauge=${gauge}`)
  const why = await page.getByText('Why this line lit up').locator('..').textContent()
  ok('"Why this score" names fraud cues or a script pattern', /fraud cues|Script pattern|impersonation|threat/i.test(why || ''), (why || '').slice(0, 160))
  const transcript = await page.locator('p.tline').allTextContents()
  ok('transcript is streaming', transcript.join(' ').trim().length > 20, transcript.join(' ').slice(0, 100))
  const marksRedacted = await page.locator('mark.cue').count()
  ok('redaction ON hides highlighted raw text (no marks)', marksRedacted === 0, `marks=${marksRedacted}`)
  await page.getByLabel(/Redact personal details/).click()
  await page.waitForTimeout(500)
  const marks = await page.locator('mark.cue').count()
  ok('redaction OFF shows highlighted fraud cues', marks > 0, `marks=${marks}`)
  await page.screenshot({ path: path.join(shots, '02-replay-digital-arrest.png'), fullPage: true })

  // queue has the call with a non-zero score
  const q = await page.locator('.jack .data').first().textContent()
  ok('queue shows the call with its urgency', /\d+|…/.test(q || ''), q || '')

  // wait for replay to finish (done -> standby)
  await page.getByText('Standby').waitFor({ timeout: 120000 })
  ok('replay completes and returns to standby', true)

  // control sample should score low
  await page.getByRole('button', { name: '3×' }).nth(3).click()
  await page.getByText('Standby').waitFor({ timeout: 120000 })
  const low = Number(await page.getByTestId('urgency-value').textContent())
  ok('normal-query control stays low (<35)', low < 35, `gauge=${low}`)

  // queue ordering: digital arrest above normal query
  const titles = await page.locator('.jack .title').allTextContents()
  const iDA = titles.findIndex((t) => /Digital arrest/.test(t)), iNQ = titles.findIndex((t) => /Routine/.test(t))
  ok('queue sorts the scam call above the routine call', iDA !== -1 && iNQ !== -1 && iDA < iNQ, titles.join(' | '))
  await page.screenshot({ path: path.join(shots, '03-queue.png'), fullPage: true })

  // mobile layout sanity
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(500)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ok('no horizontal overflow at 390px', overflow <= 0, `overflow=${overflow}`)
  await page.screenshot({ path: path.join(shots, '04-mobile.png'), fullPage: true })
} catch (e) {
  fail++; console.log('FAIL  (exception)', e.message)
} finally {
  const real = errors.filter((e) => !/favicon|DevTools|ScriptProcessorNode/.test(e))
  ok('no page errors / console errors', real.length === 0, real.slice(0, 3).join(' | '))
  await browser.close()
  console.log(`\n${pass} passed, ${fail} failed  (screenshots in ${shots})`)
  process.exit(fail ? 1 : 0)
}
