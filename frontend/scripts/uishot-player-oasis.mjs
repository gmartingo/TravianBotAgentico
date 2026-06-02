/**
 * uishot-player-oasis.mjs — Captura headless del OasisCombatPlannerPanel v2.6
 * (anidado Jugador → Aldea → Oasis).
 *
 * Intercepta la llamada a /attack-reports/stats/oasis/spawn-composition y devuelve
 * un mock con 3 jugadores (GonnaDie, CrazyMouse, Desconocido) + sus aldeas + oasis,
 * así se verifica el anidado visual sin necesidad de backend real ni datos en BD.
 *
 * Uso:
 *   node scripts/uishot-player-oasis.mjs [out-prefix]
 *   # Genera: <out-prefix>-light.png  y  <out-prefix>-dark.png
 *
 * Precondiciones: el dev server ya está en http://localhost:5173
 */
import puppeteer from 'puppeteer-core'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const prefix = process.argv[2] || '/tmp/planner-v26'
const W = 1440
const H = 1100

// ── Mock EP-SPAWN con attackers (v2.6) ──────────────────────────────────────
const MOCK_RESPONSE = {
  computed_at: '2026-06-02T10:00:00.000000+00:00',
  timer_min: 7,
  oasis: [
    // GonnaDie / aldea "05"
    {
      coord_x_dest: -70,
      coord_y_dest: 73,
      total_attacks: 12,
      last_attack: '2026-06-02T08:00:00',
      inferred_type: 'cereal',
      confidence: 'medium',
      spawn_status: 'respawning',
      elapsed_seconds: 7200.0,
      attackers: [
        { player: 'GonnaDie', village: '05' },
        { player: 'CrazyMouse', village: '05 Caesar On Leave' },
      ],
      species: [
        { animal_ordinal: 1, icon_url: '/static/icons/nature_1.png', avg_present_per_burst: 3.0, max_present_per_burst: 5, is_anomaly: false, spawn_timer_s: 300, worst_case_count: 6, def_infantry_contribution: 180, def_cavalry_contribution: 120 },
        { animal_ordinal: 5, icon_url: '/static/icons/nature_5.png', avg_present_per_burst: 2.0, max_present_per_burst: 3, is_anomaly: false, spawn_timer_s: 540, worst_case_count: 4, def_infantry_contribution: 400, def_cavalry_contribution: 500 },
        { animal_ordinal: 9, icon_url: '/static/icons/nature_9.png', avg_present_per_burst: 4.5, max_present_per_burst: 7, is_anomaly: false, spawn_timer_s: 780, worst_case_count: 8, def_infantry_contribution: 700, def_cavalry_contribution: 1000 },
      ],
      worst_case_summary: { def_infantry_total: 1280, def_cavalry_total: 1620 },
    },
    // GonnaDie / aldea "02"
    {
      coord_x_dest: 12,
      coord_y_dest: -45,
      total_attacks: 8,
      last_attack: '2026-06-01T20:00:00',
      inferred_type: 'hierro',
      confidence: 'low',
      spawn_status: 'cooldown',
      elapsed_seconds: 50000.0,
      attackers: [
        { player: 'GonnaDie', village: '02' },
      ],
      species: [
        { animal_ordinal: 1, icon_url: '/static/icons/nature_1.png', avg_present_per_burst: 2.0, max_present_per_burst: 3, is_anomaly: false, spawn_timer_s: 300, worst_case_count: 4, def_infantry_contribution: 120, def_cavalry_contribution: 80 },
        { animal_ordinal: 2, icon_url: '/static/icons/nature_2.png', avg_present_per_burst: 1.5, max_present_per_burst: 2, is_anomaly: false, spawn_timer_s: 360, worst_case_count: 3, def_infantry_contribution: 105, def_cavalry_contribution: 90 },
        { animal_ordinal: 4, icon_url: '/static/icons/nature_4.png', avg_present_per_burst: 1.0, max_present_per_burst: 2, is_anomaly: false, spawn_timer_s: 480, worst_case_count: 3, def_infantry_contribution: 195, def_cavalry_contribution: 180 },
        { animal_ordinal: 8, icon_url: '/static/icons/nature_8.png', avg_present_per_burst: 0.5, max_present_per_burst: 1, is_anomaly: true, spawn_timer_s: 720, worst_case_count: null, def_infantry_contribution: 0, def_cavalry_contribution: 0 },
      ],
      worst_case_summary: { def_infantry_total: 420, def_cavalry_total: 350 },
    },
    // CrazyMouse / "05 Caesar On Leave" (ya añadido en primer oasis)
    // CrazyMouse / aldea "01" — oasis propio
    {
      coord_x_dest: 25,
      coord_y_dest: 30,
      total_attacks: 5,
      last_attack: '2026-06-02T06:00:00',
      inferred_type: 'madera',
      confidence: 'medium',
      spawn_status: 'unknown',
      elapsed_seconds: 14400.0,
      attackers: [
        { player: 'CrazyMouse', village: '01 Rome But Broke' },
      ],
      species: [
        { animal_ordinal: 5, icon_url: '/static/icons/nature_5.png', avg_present_per_burst: 3.0, max_present_per_burst: 4, is_anomaly: false, spawn_timer_s: 540, worst_case_count: 5, def_infantry_contribution: 500, def_cavalry_contribution: 625 },
        { animal_ordinal: 6, icon_url: '/static/icons/nature_6.png', avg_present_per_burst: 2.0, max_present_per_burst: 3, is_anomaly: false, spawn_timer_s: 600, worst_case_count: 4, def_infantry_contribution: 440, def_cavalry_contribution: 540 },
        { animal_ordinal: 7, icon_url: '/static/icons/nature_7.png', avg_present_per_burst: 1.5, max_present_per_burst: 2, is_anomaly: false, spawn_timer_s: 660, worst_case_count: 2, def_infantry_contribution: 340, def_cavalry_contribution: 360 },
      ],
      worst_case_summary: { def_infantry_total: 1280, def_cavalry_total: 1525 },
    },
    // "Desconocido" / "Desconocido" — siempre al final
    {
      coord_x_dest: 99,
      coord_y_dest: -99,
      total_attacks: 1,
      last_attack: '2026-05-20T10:00:00',
      inferred_type: null,
      confidence: null,
      spawn_status: 'unknown',
      elapsed_seconds: 1000000.0,
      attackers: [
        { player: 'Desconocido', village: 'Desconocido' },
      ],
      species: [],
      worst_case_summary: null,
    },
  ],
}

async function capture(theme) {
  const outPath = `${prefix}-${theme}.png`
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-first-run', '--no-default-browser-check', '--hide-scrollbars'],
    defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
  })
  const page = await browser.newPage()

  // Interceptar la llamada al endpoint EP-SPAWN y devolver el mock
  await page.setRequestInterception(true)
  page.on('request', (req) => {
    if (req.url().includes('/attack-reports/stats/oasis/spawn-composition')) {
      req.respond({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_RESPONSE),
      })
    } else {
      req.continue()
    }
  })

  // Forzar tema vía localStorage antes de cargar
  await page.evaluateOnNewDocument((themeValue) => {
    localStorage.setItem('theme', themeValue)
  }, theme)

  try {
    // Navegar a la pestaña de stats de attack-reports (ruta real de la app)
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle2', timeout: 15000 })

    // Aplicar data-theme al <html> si el sistema no lo hace automáticamente
    if (theme === 'dark') {
      await page.evaluate(() => {
        document.documentElement.setAttribute('data-theme', 'dark')
      })
    }

    // Esperar a que la app esté lista (sidebar presente)
    await page.waitForSelector('[class*="sidebar"], nav, aside', { timeout: 8000 }).catch(() => {})
    await new Promise((r) => setTimeout(r, 800))

    // Navegar a attack-reports si hay un link en el sidebar
    try {
      // Buscar link de "Reportes" o similar en el sidebar
      const navClicked = await page.evaluate(() => {
        const links = Array.from(document.querySelectorAll('a, [role="link"], nav button'))
        const reportLink = links.find(
          (el) => el.textContent && /oasis|report|reporte/i.test(el.textContent)
        )
        if (reportLink) { reportLink.click(); return true }
        return false
      })
      if (navClicked) {
        await new Promise((r) => setTimeout(r, 1000))
      }
    } catch (_) {}

    // Intentar hacer clic en la pestaña "Estadísticas" si existe
    try {
      await page.evaluate(() => {
        const tabs = Array.from(document.querySelectorAll('[role="tab"], button'))
        const statsTab = tabs.find(
          (el) => el.textContent && /estad|stats/i.test(el.textContent)
        )
        if (statsTab) statsTab.click()
      })
      await new Promise((r) => setTimeout(r, 600))
    } catch (_) {}

    await new Promise((r) => setTimeout(r, 500))
    await page.screenshot({ path: outPath })
    console.log(`OK ${outPath}`)
  } catch (e) {
    console.error(`ERROR [${theme}]: ${e.message}`)
    await page.screenshot({ path: outPath }).catch(() => {})
    process.exitCode = 1
  } finally {
    await browser.close()
  }
}

await capture('light')
await capture('dark')
