/**
 * uishot-oasis-reports.mjs — Capturas para el manual de usuario
 * "Reportes de ataques a oasis" (pestaña Historial, Ingest e Historial).
 *
 * Solo localhost:5173. NUNCA Travian ni sitios externos.
 *
 * Uso:
 *   node scripts/uishot-oasis-reports.mjs <directorio-salida>
 */
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const BASE_URL = 'http://localhost:5173'
const OUT_DIR = process.argv[2] || '/tmp/oasis-reports-caps'

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true })

const W = 1440
const H = 900

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-first-run', '--no-default-browser-check', '--hide-scrollbars'],
  defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
})

const page = await browser.newPage()
await page.emulateMediaFeatures([
  { name: 'prefers-reduced-motion', value: 'no-preference' },
])

await page.evaluateOnNewDocument(() => {
  localStorage.setItem('lang', 'es')
  localStorage.setItem('theme', 'light')
})

async function shot(name, description) {
  const outPath = path.join(OUT_DIR, name + '.png')
  await page.screenshot({ path: outPath, fullPage: false })
  console.log(`OK ${name}: ${description}`)
  return outPath
}

async function wait(ms) {
  await new Promise((r) => setTimeout(r, ms))
}

try {
  // ── Navegar a /reportes-oasis ──────────────────────────────────────────────
  console.log('Navegando a /reportes-oasis...')
  await page.goto(`${BASE_URL}/reportes-oasis`, { waitUntil: 'networkidle2', timeout: 20000 })
  await wait(1500)

  // CAPTURA 1: Vista general — pestaña Historial activa por defecto
  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(300)
  await shot('ar-01-vista-historial', 'Vista general de la página Reportes de Oasis — pestaña Historial')

  // ── Click en pestaña Historial (puede ya estar activa) ─────────────────────
  const historyTab = await page.$('#tab-history')
  if (historyTab) {
    await historyTab.click()
    await wait(1500)
  }

  // CAPTURA 2: Tabla del historial con datos
  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(300)
  await shot('ar-02-tabla-historial', 'Tabla del historial de ataques con columnas de fecha, coords, tropas y botín')

  // ── Abrir el primer reporte del historial para ver el drawer ──────────────
  const firstRow = await page.$('[data-testid="history-row"], tbody tr, [role="row"]')
  if (firstRow) {
    await firstRow.click()
    await wait(1200)
    await shot('ar-03-detalle-reporte', 'Drawer de detalle de un reporte de ataque (tropas, animales, botín)')
    // Cerrar drawer
    const closeBtn = await page.$('[aria-label="Cerrar"], [data-dismiss], button[title="Cerrar"]')
    if (closeBtn) { await closeBtn.click(); await wait(500) }
    else { await page.keyboard.press('Escape'); await wait(500) }
  }

  // ── Captura filtros de historial ────────────────────────────────────────────
  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(300)
  await shot('ar-04-filtros-historial', 'Filtros del historial: búsqueda por coordenadas y rango de fechas')

  // ── Click en pestaña Estadísticas ──────────────────────────────────────────
  const statsTab = await page.$('#tab-stats')
  if (statsTab) {
    await statsTab.click()
    await wait(2500)
  }

  // CAPTURA 5: Balance de operaciones (primera sección de Estadísticas)
  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(400)
  await shot('ar-05-balance-stats', 'Pestaña Estadísticas: Balance de operaciones (Perdido vs Robado) con neto')

  // CAPTURA 6: Scroll hasta GlobalOasisStatsPanel
  await page.evaluate(() => {
    const separator = document.querySelector('[role="tabpanel"] hr')
    if (separator) separator.scrollIntoView({ behavior: 'instant', block: 'start' })
    else window.scrollTo(0, window.pageYOffset + 400)
  })
  await wait(500)
  await shot('ar-06-global-stats', 'Panel de estadísticas globales: aparición de animales por especie con % global')

  // CAPTURA 7: Lista de oasis (OasisList) — scroll abajo desde global stats
  await page.evaluate(() => {
    window.scrollTo(0, window.pageYOffset + 400)
  })
  await wait(500)
  await shot('ar-07-lista-oasis', 'Lista de oasis: cada oasis con total de ataques, último ataque y botín acumulado')

  // ── Click en un oasis de la lista para ver sus stats ────────────────────────
  const oasisItem = await page.$('[data-testid="oasis-item"], [role="button"][data-x], button[data-coords]')
  if (!oasisItem) {
    // Buscar el primer enlace/botón con coords en la lista
    const oasisLinks = await page.$$('[role="tabpanel"] button')
    // Buscar un botón que contenga coordenadas (patrón X|Y o (X,Y))
    for (const btn of oasisLinks) {
      const txt = await btn.evaluate(el => el.textContent)
      if (txt && /[(-]\d+\|\d+/.test(txt)) {
        await btn.click()
        await wait(2000)
        break
      }
    }
  } else {
    await oasisItem.click()
    await wait(2000)
  }

  // CAPTURA 8: Panel de stats por oasis
  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(400)
  await shot('ar-08-stats-oasis', 'Panel de estadísticas de un oasis individual: aparición, balance y regeneración')

  // ── Volver a la lista de oasis ────────────────────────────────────────────
  await page.keyboard.press('Escape')
  await wait(500)

  // ── Click en pestaña Ingest ──────────────────────────────────────────────
  const ingestTab = await page.$('#tab-ingest')
  if (ingestTab) {
    await ingestTab.click()
    await wait(1000)
    await page.evaluate(() => window.scrollTo(0, 0))
    await wait(300)
    await shot('ar-09-ingest-vacio', 'Pestaña Ingest: formulario para pegar reportes de Travian (vacío)')
  }

  // ── Click en pestaña Cadencia ───────────────────────────────────────────
  const cadenciaTab = await page.$('#tab-cadencia, [data-tab="cadencia"]')
  if (cadenciaTab) {
    await cadenciaTab.click()
    await wait(2000)
    await page.evaluate(() => window.scrollTo(0, 0))
    await wait(400)
    await shot('ar-10-cadencia', 'Pestaña Cadencia: distribución temporal de animales por intervalo de farmeo')
  }

  console.log('\nTodas las capturas completadas en:', OUT_DIR)
} catch (e) {
  console.error('ERROR:', e.message)
  console.error(e.stack)
  await page.screenshot({ path: path.join(OUT_DIR, 'error-state.png') }).catch(() => {})
  process.exitCode = 1
} finally {
  await browser.close()
}
