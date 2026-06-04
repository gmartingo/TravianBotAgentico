/**
 * uishot-spawn2.mjs — Capturas complementarias para el manual de spawn.
 * Correcciones: leyenda expandida, selector sin dropdown, GonnaDie, 3 jugadores.
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

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-first-run', '--no-default-browser-check', '--hide-scrollbars'],
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 1 },
})

const page = await browser.newPage()
await page.emulateMediaFeatures([
  { name: 'prefers-reduced-motion', value: 'no-preference' },
])

// localStorage: primera visita (sin spawn_panel_open → panel abierto), idioma ES, tema claro
await page.evaluateOnNewDocument(() => {
  localStorage.clear()
  localStorage.setItem('lang', 'es')
  localStorage.setItem('theme', 'light')
  // NO seteamos spawn_panel_open → primera visita → panel abierto automáticamente
})

async function shot(name, desc) {
  const p = path.join(OUT_DIR, name + '.png')
  await page.screenshot({ path: p })
  console.log(`OK ${name}: ${desc}`)
}

async function wait(ms) { await new Promise(r => setTimeout(r, ms)) }

try {
  // ── Navegar a reportes-oasis ──────────────────────────────────────────────────
  await page.goto(`${BASE_URL}/reportes-oasis`, { waitUntil: 'networkidle2', timeout: 20000 })
  await wait(600)

  // ── Click en pestaña Estadísticas ────────────────────────────────────────────
  await page.waitForSelector('#tab-stats', { timeout: 8000 })
  await page.click('#tab-stats')
  await wait(2500) // Esperar carga de EP-SPAWN y global

  // ── CAPTURA A: Vista general con Leyenda expandida (1ª visita → auto-expand) ──
  // En primera visita, spawn_panel_open no existe → el panel se abre solo.
  // Verificamos y tomamos la captura desde el top.
  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(400)

  // Verificar que el panel de mecánica está abierto
  const panelOpen = await page.evaluate(() => {
    // El botón de la leyenda tiene un aria-expanded
    // Necesitamos distinguirlo del botón de idioma.
    // El botón de la leyenda tiene aria-controls que empieza por "spawn-body-"
    const allBtns = document.querySelectorAll('button[aria-expanded]')
    for (const btn of allBtns) {
      const controls = btn.getAttribute('aria-controls') || ''
      if (controls.startsWith('spawn-body-')) {
        return btn.getAttribute('aria-expanded') === 'true'
      }
    }
    return null
  })
  console.log('Panel mecánica abierto:', panelOpen)

  if (!panelOpen) {
    // Abrir específicamente el panel de mecánica (no el de idioma)
    await page.evaluate(() => {
      const allBtns = document.querySelectorAll('button[aria-expanded]')
      for (const btn of allBtns) {
        const controls = btn.getAttribute('aria-controls') || ''
        if (controls.startsWith('spawn-body-')) {
          btn.click()
          return
        }
      }
    })
    await wait(500)
  }

  await shot('spawn-A-vista-general', 'Vista general pestaña Estadísticas con Leyenda expandida')

  // ── CAPTURA B: Panel Leyenda con tablas de timers y sets ─────────────────────
  // Scroll para ver el contenido interior del panel expandido
  await page.evaluate(() => {
    const allBtns = document.querySelectorAll('button[aria-expanded]')
    for (const btn of allBtns) {
      const controls = btn.getAttribute('aria-controls') || ''
      if (controls.startsWith('spawn-body-')) {
        btn.scrollIntoView({ behavior: 'instant', block: 'start' })
        return
      }
    }
  })
  await wait(300)
  await shot('spawn-B-leyenda-expandida', 'Panel Leyenda expandido mostrando tabla de timers y sets por tipo de oasis')

  // ── CAPTURA C: Scroll para ver toda la leyenda (sets completos) ───────────────
  await page.evaluate(() => {
    // Scroll 200px más para ver la tabla de sets
    window.scrollBy(0, 200)
  })
  await wait(300)
  await shot('spawn-C-leyenda-sets', 'Tabla de sets por tipo de oasis dentro del panel Leyenda')

  // ── CAPTURA D: Selector de intervalo limpio (sin dropdowns) ──────────────────
  // Scroll al planificador
  await page.evaluate(() => {
    // Buscar el h2/h3 del Planificador de combate
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    let node
    while ((node = walker.nextNode())) {
      if (node.textContent.trim() === 'Planificador de combate por oasis') {
        node.parentElement.scrollIntoView({ behavior: 'instant', block: 'start' })
        return
      }
    }
    // fallback
    window.scrollTo(0, 600)
  })
  await wait(400)
  await shot('spawn-D-planificador-selector', 'Planificador de combate con selector de intervalo (10 min activo por defecto)')

  // ── CAPTURA E: Scroll para ver GonnaDie en la jerarquía ──────────────────────
  // GonnaDie es el segundo jugador (CrazyMouse está primero en A-Z)
  // Necesitamos hacer scroll hacia abajo para ver GonnaDie
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    let node
    while ((node = walker.nextNode())) {
      if (node.textContent.trim() === 'GonnaDie') {
        node.parentElement.scrollIntoView({ behavior: 'instant', block: 'start' })
        return
      }
    }
  })
  await wait(400)
  await shot('spawn-E-gonnadie-jerarquia', 'Jugador GonnaDie con aldeas 00-05 expandidas en la jerarquía')

  // ── CAPTURA F: Scroll más abajo para ver los 3 jugadores simultáneamente ──────
  // Buscamos el inicio del Planificador y mostramos lo suficiente para ver los headers de los 3
  await page.evaluate(() => {
    // Scroll para que se vea CrazyMouse, GonnaDie y SharpHorseman en pantalla
    // Primero buscar SharpHorseman
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    let node
    while ((node = walker.nextNode())) {
      if (node.textContent.trim() === 'SharpHorseman') {
        node.parentElement.scrollIntoView({ behavior: 'instant', block: 'center' })
        return
      }
    }
  })
  await wait(400)
  await shot('spawn-F-tres-jugadores', 'Los tres jugadores (CrazyMouse, GonnaDie, SharpHorseman) como cuentas separadas')

  // ── CAPTURA G: Oasis repoblando (spawn_status = respawning) si hay alguno ─────
  // Primero necesitamos saber si el estado "Repoblando" aparece en los datos actuales
  // (en las capturas anteriores solo vimos Cooldown; puede que repoblando no esté visible ahora)
  const hasRespawning = await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    let node
    while ((node = walker.nextNode())) {
      if (node.textContent.trim().toLowerCase() === 'repoblando') {
        node.parentElement.scrollIntoView({ behavior: 'instant', block: 'center' })
        return true
      }
    }
    return false
  })
  if (hasRespawning) {
    await wait(300)
    await shot('spawn-G-repoblando', 'Oasis en estado Repoblando (punto verde)')
  } else {
    console.log('INFO: No hay oasis con estado Repoblando en los datos actuales')
  }

  console.log('\nCapturas complementarias completadas en:', OUT_DIR)
} catch (e) {
  console.error('ERROR:', e.message)
  await page.screenshot({ path: path.join(OUT_DIR, 'error2.png') }).catch(() => {})
  process.exitCode = 1
} finally {
  await browser.close()
}
