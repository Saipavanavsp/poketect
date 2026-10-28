// Capture README screenshots with the locally installed Microsoft Edge (no browser download).
//   node scripts/screenshots.mjs [baseUrl]
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const base = process.argv[2] || 'http://localhost:5173/'
const only = process.argv[3]?.split(',') // optional comma-separated subset of shot names
const out = new URL('../../docs/screenshots/', import.meta.url)
mkdirSync(out, { recursive: true })

const shots = [
  ['scanner', '#/', async (page) => {
    await page.getByRole('button', { name: 'Pikachu' }).click()
    await page.getByText('Identified:').waitFor({ timeout: 60000 })
    await page.getByRole('heading', { name: 'Attacks' }).waitFor()
  }],
  ['pokemon-charizard', '#/pokemon/charizard', (page) => page.getByRole('heading', { name: 'Evolution' }).waitFor()],
  ['browse', '#/browse?type=fire', (page) => page.getByText('Charizard').first().waitFor()],
  ['trainer', '#/trainer', (page) => page.getByRole('heading', { name: /Team of/ }).waitFor()],
  ['map', '#/map?region=kanto&place=viridian-forest', (page) => page.getByText('wild Pokémon found here').waitFor()],
  ['talk', '#/talk', async (page) => {
    await page.getByRole('checkbox', { name: 'Speak replies aloud' }).uncheck().catch(() => {})
    for (const q of ['Tell me the nearest gym for a battle', 'What does Sceptile evolve from?']) {
      await page.getByRole('button', { name: q }).click()
      await page.waitForTimeout(600)
    }
  }],
]

const browser = await chromium.launch({ channel: 'msedge' })
for (const mobile of [false, true]) {
  const page = await browser.newPage(mobile ? { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 } : { viewport: { width: 1360, height: 900 } })
  page.on('pageerror', (err) => console.error('page error:', err.message))
  page.on('console', (msg) => msg.type() === 'error' && console.error('console:', msg.text()))
  for (const [name, path, ready] of shots) {
    if (mobile && !['scanner', 'trainer', 'talk'].includes(name)) continue
    if (only && !only.includes(name)) continue
    await page.goto(base + path)
    await ready(page)
    await page.waitForTimeout(800)
    await page.screenshot({ path: fileURLToPath(new URL(`${name}${mobile ? '-mobile' : ''}.png`, out)), fullPage: name !== 'map' && !mobile })
    console.log('saved', name, mobile ? '(mobile)' : '')
  }
  await page.close()
}
await browser.close()
