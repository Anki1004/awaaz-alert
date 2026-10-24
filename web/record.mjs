// Silent screen recording of the dashboard for the 2-minute demo (voice-over is added afterwards).
// Needs server + dev server running.  node record.mjs  -> docs/demo-raw.webm (+ mp4 if ffmpeg is on PATH)
import { createRequire } from 'node:module'
import { mkdirSync, readdirSync, renameSync, existsSync } from 'node:fs'
import { execSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(path.join(here, 'package.json'))
const { chromium } = require('playwright')
const out = path.join(here, '..', 'docs'); mkdirSync(out, { recursive: true })
const tmp = path.join(here, 'rec-tmp'); mkdirSync(tmp, { recursive: true })
const URL = process.env.APP_URL || 'http://127.0.0.1:5173'

const browser = await chromium.launch(process.env.PW_CHROME ? { executablePath: process.env.PW_CHROME } : {})
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir: tmp, size: { width: 1440, height: 900 } }, colorScheme: 'dark' })
const page = await ctx.newPage()
const pause = (ms) => page.waitForTimeout(ms)

await page.goto(URL)
await page.getByText(/^ready · /).waitFor({ timeout: 120000 })
await pause(2500)                                            // 0:00 standby, banner visible
await page.getByRole('button', { name: /▶ Digital arrest/ }).click()   // 0:03 replay at 1x (~42 s)
await pause(34000)                                           // let the stamp land
await page.getByLabel(/Redact personal details/).click()     // show cues underline
await pause(6000)
await page.getByText('Standby').waitFor({ timeout: 90000 })
await pause(1500)
await page.getByRole('button', { name: 'Score all samples' }).click()  // queue fills
await pause(26000)
// inspect a window on the strip
const dots = page.locator('svg circle')
if (await dots.count() > 5) { await dots.nth(5).click(); await pause(4000); await page.getByText('follow the pen').click() }
await pause(2500)
await ctx.close(); await browser.close()
const webm = readdirSync(tmp).find((f) => f.endsWith('.webm'))
const dst = path.join(out, 'demo-raw.webm'); renameSync(path.join(tmp, webm), dst)
console.log('saved', dst)
try { execSync(`ffmpeg -y -loglevel error -i "${dst}" -c:v libx264 -pix_fmt yuv420p -r 30 -crf 20 "${path.join(out, 'demo-raw.mp4')}"`); console.log('mp4 ok') } catch { console.log('ffmpeg not available; webm only') }
if (existsSync(tmp)) try { execSync(process.platform === 'win32' ? `rmdir /s /q "${tmp}"` : `rm -rf "${tmp}"`) } catch {}
