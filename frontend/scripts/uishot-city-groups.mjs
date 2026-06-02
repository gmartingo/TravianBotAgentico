/**
 * uishot-city-groups.mjs — Captura headless de OasisCombatPlannerPanel v2.3.
 *
 * Interceta los endpoints de la API y devuelve datos mock con origin_villages
 * para verificar la agrupación por ciudad atacante sin necesidad de backend real.
 *
 * Uso: node scripts/uishot-city-groups.mjs
 * Salida: /tmp/planner-city-light.png, /tmp/planner-city-dark.png,
 *         /tmp/planner-city-empty.png, /tmp/planner-city-error.png
 */
import puppeteer from 'puppeteer-core'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

// Usamos el servidor de preview (build producción) porque la interceptación
// de puppeteer interfiere con los módulos ESM dinámicos de Vite dev server.
const BASE = 'http://localhost:5190'

// ── Mock de datos EP-SPAWN con origin_villages ────────────────────────────────
const MOCK_SPAWN = {
  timer_min: 10,
  oasis: [
    // Aldea del Norte ataca dos oasis
    {
      coord_x_dest: -70, coord_y_dest: 73,
      inferred_type: 'cereal', confidence: 'medium',
      spawn_status: 'respawning',
      origin_villages: ['Aldea del Norte', 'Fortaleza del Sur'],
      species: [
        { animal_ordinal: 9, avg_present_per_burst: 4.5, max_present_per_burst: 7, worst_case_count: 7, is_anomaly: false },
        { animal_ordinal: 10, avg_present_per_burst: 2.0, max_present_per_burst: 3, worst_case_count: 3, is_anomaly: false },
      ],
    },
    {
      coord_x_dest: -65, coord_y_dest: 80,
      inferred_type: 'madera', confidence: 'low',
      spawn_status: 'cooldown',
      origin_villages: ['Aldea del Norte'],
      species: [
        { animal_ordinal: 6, avg_present_per_burst: 3.0, max_present_per_burst: 5, worst_case_count: 5, is_anomaly: false },
        { animal_ordinal: 7, avg_present_per_burst: 1.5, max_present_per_burst: 2, worst_case_count: 2, is_anomaly: false },
        { animal_ordinal: 4, avg_present_per_burst: 8.0, max_present_per_burst: 12, worst_case_count: null, is_anomaly: true },
      ],
    },
    // Fortaleza del Sur ataca este oasis (ya aparece también bajo Aldea del Norte arriba)
    {
      coord_x_dest: -55, coord_y_dest: 60,
      inferred_type: 'hierro', confidence: 'medium',
      spawn_status: 'unknown',
      origin_villages: ['Fortaleza del Sur'],
      species: [
        { animal_ordinal: 5, avg_present_per_burst: 6.0, max_present_per_burst: 9, worst_case_count: 9, is_anomaly: false },
      ],
    },
    // Oasis sin ciudad conocida → "Desconocido"
    {
      coord_x_dest: 10, coord_y_dest: -20,
      inferred_type: null, confidence: null,
      spawn_status: 'unknown',
      origin_villages: ['Desconocido'],
      species: [],
    },
  ],
}

// Mock EP-SPAWN vacío (para estado vacío)
const MOCK_SPAWN_EMPTY = { timer_min: 10, oasis: [] }

// ── Mock de otros endpoints que StatsTab necesita ─────────────────────────────
const MOCK_GLOBAL = {
  total_oasis: 4, total_attacks: 38,
  // Campos requeridos por GlobalOasisStatsPanel (ver docs/api/API.md)
  animal_appearances: [],
  animal_regen_rates: [],
}
const MOCK_BALANCE = { balance: 0, total_loot: 0, total_losses: 0, raids: [] }
const MOCK_OASIS_LIST = { oasis: [], total: 0 }

function setupInterception(page, mockSpawn, errorSpawn = false) {
  page.removeAllListeners('request')
  page.on('request', (req) => {
    const url = req.url()
    // Dejar pasar recursos estáticos (JS, CSS, HTML, imágenes, sourcemaps)
    // Solo interceptar llamadas a la API (/api/* en el preview server)
    const isApiCall = url.includes('/api/') || url.includes('localhost:8000')
    if (!isApiCall) {
      req.continue()
      return
    }
    // Routing de mocks por endpoint
    if (url.includes('/attack-reports/stats/oasis/spawn-composition')) {
      if (errorSpawn) {
        req.respond({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Error interno del servidor' }) })
      } else {
        req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(mockSpawn) })
      }
    } else if (url.includes('/attack-reports/stats/global')) {
      req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_GLOBAL) })
    } else if (url.includes('/attack-reports/balance')) {
      req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_BALANCE) })
    } else if (url.includes('/attack-reports/oasis')) {
      req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_OASIS_LIST) })
    } else if (url.includes('/attack-reports')) {
      req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
    } else {
      // Cualquier otra llamada a la API (accounts, sessions, etc.)
      req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ accounts: [], worlds: [] }) })
    }
  })
}

// navigateToStats ya no se usa como función separada; la lógica está en capture()

async function capture(page, outPath, mockSpawn, errorSpawn = false) {
  // Activar interceptación ANTES de goto para interceptar todas las llamadas
  // a /api/* (el preview server no tiene proxy, las requests van a :5190/api/*)
  await page.setRequestInterception(true)
  setupInterception(page, mockSpawn, errorSpawn)

  await page.goto(`${BASE}/reportes-oasis`, { waitUntil: 'networkidle2', timeout: 25000 })
  await new Promise(r => setTimeout(r, 1000))
  // Esperar a que los tabs aparezcan
  await page.waitForSelector('[role="tab"]', { timeout: 15000 })

  // Hacer clic en la pestaña "Estadísticas" via evaluate
  await page.evaluate(() => {
    const tabs = document.querySelectorAll('[role="tab"]')
    const st = Array.from(tabs).find(t => t.textContent.trim() === 'Estadísticas')
    if (st) st.click()
  })
  // Esperar a que el panel de stats sea visible y las llamadas de red completen
  await new Promise(r => setTimeout(r, 2500))

  // Colapsar el SpawnMechanicsPanel (primer botón de toggle que tiene chevron)
  // para que el OasisCombatPlannerPanel sea visible en el viewport
  await page.evaluate(() => {
    // SpawnMechanicsPanel tiene un botón de toggle en su cabecera
    const toggleBtns = document.querySelectorAll('button[aria-expanded]')
    // El primer aria-expanded="true" es el SpawnMechanicsPanel colapsable
    const spawnToggle = Array.from(toggleBtns).find(
      b => b.getAttribute('aria-expanded') === 'true' &&
           b.textContent.includes('Mecánica')
    )
    if (spawnToggle) spawnToggle.click()
  })
  await new Promise(r => setTimeout(r, 400))

  // Scroll hasta el OasisCombatPlannerPanel
  await page.evaluate(() => {
    // Buscar la cabecera "Planificador de combate por oasis"
    const headings = document.querySelectorAll('h2')
    const planner = Array.from(headings).find(h => h.textContent.includes('Planificador'))
    if (planner) planner.scrollIntoView({ behavior: 'instant', block: 'start' })
  })
  await new Promise(r => setTimeout(r, 300))

  await page.screenshot({ path: outPath, fullPage: false })
  console.log('OK ' + outPath)
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-first-run', '--no-default-browser-check', '--hide-scrollbars'],
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 1 },
})

try {
  // ── 1. Modo claro — con datos (varias ciudades) ───────────────────────────
  {
    const page = await browser.newPage()
    await page.emulateMediaFeatures([
      { name: 'prefers-color-scheme', value: 'light' },
      { name: 'prefers-reduced-motion', value: 'no-preference' },
    ])
    await capture(page, '/tmp/planner-city-light.png', MOCK_SPAWN)
    await page.close()
  }

  // ── 2. Modo oscuro — con datos (varias ciudades) ──────────────────────────
  {
    const page = await browser.newPage()
    await page.emulateMediaFeatures([
      { name: 'prefers-color-scheme', value: 'dark' },
      { name: 'prefers-reduced-motion', value: 'no-preference' },
    ])
    await capture(page, '/tmp/planner-city-dark.png', MOCK_SPAWN)
    await page.close()
  }

  // ── 3. Estado vacío ───────────────────────────────────────────────────────
  {
    const page = await browser.newPage()
    await page.emulateMediaFeatures([
      { name: 'prefers-color-scheme', value: 'light' },
      { name: 'prefers-reduced-motion', value: 'no-preference' },
    ])
    await capture(page, '/tmp/planner-city-empty.png', MOCK_SPAWN_EMPTY)
    await page.close()
  }

  // ── 4. Estado error ───────────────────────────────────────────────────────
  {
    const page = await browser.newPage()
    await page.emulateMediaFeatures([
      { name: 'prefers-color-scheme', value: 'light' },
      { name: 'prefers-reduced-motion', value: 'no-preference' },
    ])
    await capture(page, '/tmp/planner-city-error.png', null, true)
    await page.close()
  }

} catch (e) {
  console.error('ERROR: ' + e.message)
  process.exitCode = 1
} finally {
  await browser.close()
}
