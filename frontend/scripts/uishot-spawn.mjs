/**
 * uishot-spawn.mjs — Capturas para el manual de usuario
 * "Estadísticas de mecánica de spawn de oasis".
 *
 * Solo localhost:5173. NUNCA Travian ni sitios externos.
 * Reutiliza la misma arquitectura de uishot.mjs.
 *
 * Uso:
 *   node scripts/uishot-spawn.mjs <directorio-salida>
 */
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const BASE_URL = 'http://localhost:5173'
const OUT_DIR = process.argv[2] || '/tmp/spawn-caps'

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

// Asegurar localStorage limpio para forzar SpawnMechanicsPanel abierto en 1ª visita
// (spawn_panel_open no existe → primera visita → abierto)
await page.evaluateOnNewDocument(() => {
  localStorage.clear()
  // Forzar idioma español y tema claro
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
  // ── 1. Navegar a /reportes-oasis ─────────────────────────────────────────────
  console.log('Navegando a /reportes-oasis...')
  await page.goto(`${BASE_URL}/reportes-oasis`, { waitUntil: 'networkidle2', timeout: 20000 })
  await wait(800)

  // ── 2. Hacer click en la pestaña Estadísticas ────────────────────────────────
  console.log('Buscando pestaña Estadísticas...')
  await page.waitForSelector('#tab-stats', { timeout: 10000 })
  await page.click('#tab-stats')
  await wait(2000) // Esperar carga de datos (EP-SPAWN + global)

  // CAPTURA 1: Vista general — SpawnMechanics abierto (1ª visita localStorage vacío)
  // Hacer scroll al principio para ver todo desde arriba
  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(300)
  await shot('spawn-01-vista-general', 'Vista general de la pestaña Estadísticas con panel Leyenda expandido')

  // ── 3. Captura 2: Panel Leyenda / Mecánica de spawn expandido, scroll para ver tablas ───
  // Hacer scroll para ver el interior del SpawnMechanicsPanel completo
  await page.evaluate(() => {
    // Buscar el panel de mecánica (primer card después del tabpanel)
    const panel = document.querySelector('[aria-expanded]')
    if (panel) panel.scrollIntoView({ behavior: 'instant', block: 'start' })
  })
  await wait(300)
  await shot('spawn-02-leyenda-mecanica', 'Panel de Leyenda / Mecánica de spawn expandido con tablas de timers y sets')

  // ── 4. Si el panel está cerrado (2ª visita localStorage), abrirlo ─────────────
  // Comprobar si está abierto
  const spawnPanelOpen = await page.evaluate(() => {
    const btn = document.querySelector('[aria-expanded]')
    return btn ? btn.getAttribute('aria-expanded') === 'true' : false
  })
  if (!spawnPanelOpen) {
    console.log('SpawnMechanicsPanel cerrado, abriendo...')
    await page.click('[aria-expanded]')
    await wait(500)
    await shot('spawn-02-leyenda-mecanica', 'Panel de Leyenda expandido (reabierto)')
  }

  // ── 5. Captura 3: Selector de intervalo (timer=10 activo por defecto) ────────
  // Hacer scroll hasta el OasisCombatPlannerPanel (selector de intervalo)
  await page.evaluate(() => {
    // El selector de intervalo tiene botones con "10 min" aria-pressed=true
    const btns = document.querySelectorAll('[role="tabpanel"] button')
    for (const b of btns) {
      if (b.textContent.includes('min') && b.getAttribute('aria-pressed') === 'true') {
        b.scrollIntoView({ behavior: 'instant', block: 'center' })
        return
      }
    }
    // fallback: scroll al 60% de la página
    window.scrollTo(0, document.body.scrollHeight * 0.35)
  })
  await wait(400)
  await shot('spawn-03-selector-intervalo', 'Selector de intervalo con 10 min activo (por defecto)')

  // ── 6. Captura 4: Cambiar intervalo a 6 min ──────────────────────────────────
  // Buscar botón "6 min" y hacer click
  const timer6Btn = await page.evaluateHandle(() => {
    const btns = document.querySelectorAll('[role="tabpanel"] button')
    for (const b of btns) {
      if (b.textContent.trim() === '6 min') return b
    }
    return null
  })
  if (timer6Btn.asElement()) {
    await timer6Btn.asElement().click()
    await wait(2000) // Esperar recarga de datos con timer=6
    await page.evaluate(() => window.scrollTo(0, window.pageYOffset))
    await shot('spawn-04-intervalo-6min', 'Peor combinación con intervalo 6 min (respawn más frecuente)')
  } else {
    console.warn('WARN: No se encontró botón 6 min')
  }

  // ── 7. Volver a timer=10 para capturas de jerarquía ─────────────────────────
  const timer10Btn = await page.evaluateHandle(() => {
    const btns = document.querySelectorAll('[role="tabpanel"] button')
    for (const b of btns) {
      if (b.textContent.trim() === '10 min') return b
    }
    return null
  })
  if (timer10Btn.asElement()) {
    await timer10Btn.asElement().click()
    await wait(2000)
  }

  // ── 8. Captura 5: Jerarquía Jugador → Aldea → Oasis con GonnaDie ─────────────
  // Scroll hasta la sección de jugadores (debajo del selector)
  await page.evaluate(() => {
    // Buscar primer botón con aria-expanded en la zona del planner (PlayerOasisSection)
    const sections = document.querySelectorAll('[role="tabpanel"] section')
    if (sections.length > 0) {
      sections[0].scrollIntoView({ behavior: 'instant', block: 'start' })
    }
  })
  await wait(400)
  await shot('spawn-05-jerarquia-jugador', 'Jerarquía Jugador → Aldea → Oasis con GonnaDie expandido')

  // ── 9. Captura 6: Oasis con sus filas Media y Peor ───────────────────────────
  // Hacer scroll para ver un bloque de oasis completo con sus chips
  await page.evaluate(() => {
    // Buscar filas de chips (Media / Peor) — buscar texto "Media" o "Peor"
    const allSpans = document.querySelectorAll('[role="tabpanel"] span')
    for (const span of allSpans) {
      if (span.textContent.trim() === 'Media' || span.textContent.trim() === 'Peor') {
        span.closest('[style]')?.scrollIntoView({ behavior: 'instant', block: 'center' })
        return
      }
    }
    window.scrollTo(0, window.pageYOffset + 200)
  })
  await wait(400)
  await shot('spawn-06-media-peor', 'Filas Media y Peor por oasis con chips de animales')

  // ── 10. Captura 7: Un oasis con cooldown (estado rojo) ───────────────────────
  // Buscar un elemento con "cooldown" visible
  await page.evaluate(() => {
    const allElements = document.querySelectorAll('[role="tabpanel"] *')
    for (const el of allElements) {
      if (el.textContent.trim().toLowerCase() === 'cooldown' && el.children.length === 0) {
        el.scrollIntoView({ behavior: 'instant', block: 'center' })
        return
      }
    }
  })
  await wait(400)
  await shot('spawn-07-estado-cooldown', 'Oasis en estado cooldown (punto rojo) tras ser atacado')

  // ── 11. Captura 8: Anomalía visible ──────────────────────────────────────────
  // Buscar "anom." en la UI
  await page.evaluate(() => {
    const allElements = document.querySelectorAll('[role="tabpanel"] *')
    for (const el of allElements) {
      if (el.textContent.trim() === 'anom.' && el.children.length === 0) {
        el.scrollIntoView({ behavior: 'instant', block: 'center' })
        return
      }
    }
  })
  await wait(400)
  await shot('spawn-08-anomalia', 'Badge "anom." en un animal con comportamiento anómalo')

  // ── 12. Scroll para ver CrazyMouse y SharpHorseman ──────────────────────────
  await page.evaluate(() => {
    // Buscar el nombre "CrazyMouse" en cualquier elemento
    const walker = document.createTreeWalker(
      document.querySelector('[role="tabpanel"]') || document.body,
      NodeFilter.SHOW_TEXT
    )
    let node
    while ((node = walker.nextNode())) {
      if (node.textContent.includes('CrazyMouse') || node.textContent.includes('SharpHorseman')) {
        node.parentElement?.scrollIntoView({ behavior: 'instant', block: 'center' })
        return
      }
    }
    // fallback: scroll al final
    window.scrollTo(0, document.body.scrollHeight)
  })
  await wait(400)
  await shot('spawn-09-otros-jugadores', 'CrazyMouse y SharpHorseman como jugadores separados')

  // ── 13. Captura modo oscuro ───────────────────────────────────────────────────
  // Cambiar a modo oscuro
  await page.evaluate(() => {
    document.documentElement.dataset.theme = 'dark'
    localStorage.setItem('theme', 'dark')
    window.scrollTo(0, 0)
  })
  await wait(300)
  await shot('spawn-10-modo-oscuro', 'Vista general en modo oscuro')

  // Volver a modo claro
  await page.evaluate(() => {
    document.documentElement.dataset.theme = 'light'
    localStorage.setItem('theme', 'light')
  })

  // ── 14. Captura final: Panel GlobalOasisStatsPanel ───────────────────────────
  await page.evaluate(() => {
    // Scroll hacia la sección de estadísticas globales (después del separador)
    const separators = document.querySelectorAll('[role="tabpanel"] hr')
    if (separators.length > 0) {
      separators[0].scrollIntoView({ behavior: 'instant', block: 'start' })
    }
  })
  await wait(400)
  await shot('spawn-11-global-stats', 'Panel de estadísticas globales de oasis')

  console.log('\nTodas las capturas completadas en:', OUT_DIR)
} catch (e) {
  console.error('ERROR:', e.message)
  // Captura de emergencia para diagnóstico
  await page.screenshot({ path: path.join(OUT_DIR, 'error-state.png') }).catch(() => {})
  process.exitCode = 1
} finally {
  await browser.close()
}
