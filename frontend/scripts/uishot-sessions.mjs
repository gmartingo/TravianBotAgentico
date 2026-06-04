/**
 * uishot-sessions.mjs — Capturas para el manual de usuario "Sesión Humana".
 *
 * Solo localhost:5173. NUNCA Travian ni sitios externos.
 * Reutiliza la misma arquitectura de uishot-spawn.mjs.
 *
 * Uso:
 *   node scripts/uishot-sessions.mjs <directorio-salida>
 *
 * Prerequisito: app corriendo en http://localhost:5173 con world_id=2 disponible.
 * Ruta real en la app: /mundos/:worldId (no /worlds/:worldId)
 */
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const BASE_URL = 'http://localhost:5173'
const WORLD_ID = 2
const ASSETS_DIR = path.resolve(
  path.dirname(new URL(import.meta.url).pathname),
  '../../documentacion/manual-usuario/assets'
)
const OUT_DIR = process.argv[2] || ASSETS_DIR

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true })

const W = 1440
const H = 900

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-first-run', '--no-default-browser-check', '--hide-scrollbars'],
})

const page = await browser.newPage()
await page.setViewport({ width: W, height: H })

// ── Helpers ────────────────────────────────────────────────────────────────────

const wait = ms => new Promise(r => setTimeout(r, ms))

async function shot(name, desc) {
  const filename = path.join(OUT_DIR, `${name}.png`)
  await page.screenshot({ path: filename })
  console.log(`  [CAPTURA] ${name}.png — ${desc}`)
}

// ── Navegación al mundo ────────────────────────────────────────────────────────

console.log('=== uishot-sessions.mjs ===')
console.log(`Salida: ${OUT_DIR}`)

// Cargar la app en la página del mundo (ruta real: /mundos/:worldId)
await page.goto(`${BASE_URL}/mundos/${WORLD_ID}`, { waitUntil: 'networkidle2', timeout: 20000 })
await wait(2000)

// Hacer clic en el ítem "Sesión" del sidebar del mundo
console.log('Buscando ítem "Sesión" en el sidebar...')

// Buscar por texto visible
let sessionClicked = false
const allEls = await page.$$('a, button, [role="tab"], [role="menuitem"], li')
for (const el of allEls) {
  const txt = await el.evaluate(e => e.textContent?.trim() ?? '')
  if (/^Sesi[oó]n$/.test(txt)) {
    await el.click()
    sessionClicked = true
    console.log(`  Clic en "Sesión"`)
    break
  }
}
if (!sessionClicked) {
  console.log('  No se encontró "Sesión" por texto exacto, buscando parcial...')
  for (const el of allEls) {
    const txt = await el.evaluate(e => e.textContent?.trim() ?? '')
    if (/Sesi[oó]n/i.test(txt) && txt.length < 15) {
      await el.click()
      sessionClicked = true
      console.log(`  Clic parcial en "${txt}"`)
      break
    }
  }
}
if (!sessionClicked) {
  console.log('  WARN: No se encontró el ítem Sesión en el sidebar. Capturando la vista actual.')
}

await wait(3000) // esperar carga del API (GET /worlds/2/session + /timeline)

// ── CAPTURA 1: Vista general del tab Sesión ─────────────────────────────────────
await page.evaluate(() => window.scrollTo(0, 0))
await wait(400)
await shot('session-01-vista-general', 'Tab Sesión — Panel de estado, botones de override y calendario semanal')

// ── CAPTURA 2: Panel de estado (viewport pequeño para enfocar arriba) ──────────
console.log('\nCapturando panel de estado...')
await page.setViewport({ width: 900, height: 480 })
await wait(400)
await shot('session-02-panel-estado', 'Panel de estado — modo activo, bloque horario, countdown y jitter')
await page.setViewport({ width: W, height: H })
await wait(300)

// ── CAPTURA 3: Clic en Lunes (primer día) → barra de timeline ─────────────────
console.log('\nHaciendo clic en el primer día para mostrar la barra de timeline...')
try {
  await page.waitForSelector('[role="tablist"]', { timeout: 5000 })
  const tabs = await page.$$('[role="tablist"] [role="tab"]')
  if (tabs.length > 0) {
    await tabs[0].click()
    console.log(`  Clic en primer día (${tabs.length} tabs encontrados)`)
  } else {
    const dayBtns = await page.$$('[role="tablist"] button')
    if (dayBtns.length > 0) { await dayBtns[0].click(); console.log('  Clic en primer botón tablist') }
  }
} catch {
  console.log('  No se encontró el tablist')
}
await wait(1500)
await page.evaluate(() => window.scrollTo(0, 0))
await wait(300)
await shot('session-03-selector-dias', 'Selector de días — Lunes seleccionado con barra de timeline 24h')

// ── CAPTURA 4: Editor de bloques (scroll hasta él) ─────────────────────────────
console.log('\nHaciendo scroll hasta el editor de bloques...')
await page.evaluate(() => {
  const tables = document.querySelectorAll('table')
  if (tables.length) tables[0].scrollIntoView({ behavior: 'instant', block: 'center' })
})
await wait(800)
await shot('session-04-editor-bloques', 'Editor de bloques — tabla Desde/Hasta/Modo, botón añadir y cobertura')

// ── CAPTURA 5: Barra de timeline + leyenda ─────────────────────────────────────
console.log('\nCapturando barra de timeline...')
await page.evaluate(() => window.scrollTo(0, 0))
await wait(400)
await page.setViewport({ width: 1280, height: 700 })
await wait(300)
await shot('session-05-timeline-bar', 'Barra de timeline 24h — segmentos proporcionales por modo con leyenda')
await page.setViewport({ width: W, height: H })

// ── CAPTURA 6: Modo oscuro ─────────────────────────────────────────────────────
console.log('\nActivando modo oscuro...')
let darkToggled = false
try {
  const allBtns = await page.$$('button, [role="button"]')
  for (const btn of allBtns) {
    const lbl = await btn.evaluate(e =>
      (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent || '').toLowerCase()
    )
    if (/theme|tema|dark|oscuro|moon|night/.test(lbl)) {
      await btn.click()
      darkToggled = true
      console.log(`  Toggle tema activado`)
      break
    }
  }
} catch { /* continúa */ }

if (!darkToggled) {
  await page.evaluate(() => {
    localStorage.setItem('theme', 'dark')
    document.documentElement.setAttribute('data-theme', 'dark')
    document.documentElement.classList.add('dark')
    // Forzar repaint
    document.body.style.display = 'none'
    document.body.style.display = ''
  })
  await wait(300)
}

await wait(800)
await page.evaluate(() => window.scrollTo(0, 0))
await wait(400)
await shot('session-06-modo-oscuro', 'Tab Sesión en modo oscuro')

// ── Fin ─────────────────────────────────────────────────────────────────────────
await browser.close()
console.log('\n=== Capturas completadas ===')
console.log(`Archivos en: ${OUT_DIR}`)
