/**
 * uishot-optimizer-rediseno.mjs — Verificación visual del rediseño de optimizadores.
 *
 * Solo localhost. NUNCA Travian.
 * Uso: node scripts/uishot-optimizer-rediseno.mjs <dir-salida>
 */
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5174'
const OUT_DIR = process.argv[2] || '/tmp/optimizer-rediseno'

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true })

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-first-run', '--no-default-browser-check', '--hide-scrollbars'],
  defaultViewport: { width: 1280, height: 900, deviceScaleFactor: 2 },
})

const page = await browser.newPage()
await page.emulateMediaFeatures([
  { name: 'prefers-reduced-motion', value: 'no-preference' },
])
await page.evaluateOnNewDocument(() => {
  localStorage.setItem('lang', 'es')
  localStorage.setItem('theme', 'light')
})

async function shot(name, label) {
  const outPath = path.join(OUT_DIR, name + '.png')
  await page.screenshot({ path: outPath, fullPage: false })
  console.log(`CAPTURA ${name}: ${label}`)
}

async function wait(ms) {
  return new Promise(r => setTimeout(r, ms))
}

// Clic en un botón del radiogroup del optimizador por texto exacto
// (evita confusión con los botones del toggle global Simulador/Optimizador)
async function clickOptimizerTab(text) {
  return page.evaluate((text) => {
    // Los botones del radiogroup están dentro del header de la sección ATACANTE
    // y tienen role="radio". Buscamos exactamente ese texto.
    const radios = Array.from(document.querySelectorAll('button[role="radio"]'))
    const btn = radios.find(b => b.textContent.trim() === text)
    if (btn) { btn.click(); return true }
    return false
  }, text)
}

// Clic en el toggle global (role="tab") por texto
async function clickGlobalTab(text) {
  return page.evaluate((text) => {
    const tabs = Array.from(document.querySelectorAll('button[role="tab"]'))
    const btn = tabs.find(b => b.textContent.trim() === text)
    if (btn) { btn.click(); return true }
    return false
  }, text)
}

let checks = []
function check(id, description, passed) {
  checks.push({ id, description, passed })
  console.log(`${passed ? 'OK  ' : 'FAIL'} [${id}] ${description}`)
}

try {
  // ── Navegar a /calculadora ─────────────────────────────────────────────────
  console.log(`Navegando a ${BASE_URL}/calculadora …`)
  await page.goto(BASE_URL + '/calculadora', { waitUntil: 'networkidle2', timeout: 25000 })
  await wait(1500)

  // ── Activar modo Optimizador ───────────────────────────────────────────────
  const optClicked = await clickGlobalTab('Optimizador')
  check('NAV', 'Tab "Optimizador" clickeable', optClicked)
  await wait(1200)

  // ─── CAPTURA 1: Multi-Tropa (pestaña por defecto) ──────────────────────────
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot('opt-01-multi-tropa', 'Multi-Tropa — checkboxes de tropas, sin sliders')

  // ── Verificación: nombres de pestañas ─────────────────────────────────────
  const radioTexts = await page.evaluate(() =>
    Array.from(document.querySelectorAll('button[role="radio"]')).map(b => b.textContent.trim())
  )
  console.log('Radios encontrados:', radioTexts)
  check('F1', 'Pestaña "Multi-Tropa" visible', radioTexts.includes('Multi-Tropa'))
  check('F2', 'Pestaña "Simulador" visible', radioTexts.includes('Simulador'))
  check('F3', 'Pestaña "Multi-Raid" visible', radioTexts.includes('Multi-Raid'))
  check('F4', '"Multi-tropa" (nombre viejo) ausente', !radioTexts.includes('Multi-tropa'))
  check('F5', '"Simulador ejército" (nombre viejo) ausente', !radioTexts.some(t => t.toLowerCase().includes('ejército')))
  check('F5b', '"Army simulator" (nombre viejo en inglés) ausente', !radioTexts.some(t => t.toLowerCase().includes('army')))

  // ── Verificación: NO hay sliders de pesos ─────────────────────────────────
  // Expandir config primero para ver el interior
  const configExpanded = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button, div[role="button"]'))
    const cfg = btns.find(b => {
      const txt = b.textContent || ''
      return txt.includes('CONFIGURACIÓN') || txt.includes('Configuración')
    })
    if (cfg) { cfg.click(); return true }
    return false
  })
  console.log('Config expandida:', configExpanded)
  await wait(600)

  const rangeCount = await page.evaluate(() =>
    document.querySelectorAll('input[type="range"]').length
  )
  check('F6', 'NO hay sliders input[type="range"]', rangeCount === 0)

  // ── Verificación: input % ganancia neta y tooltip ⓘ ──────────────────────
  const bodyText = await page.evaluate(() => document.body.textContent || '')
  check('F7', '"ganancia neta" en el DOM', bodyText.includes('ganancia neta'))

  const hasInfoBtn = await page.evaluate(() =>
    Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('ⓘ'))
  )
  check('F8', 'Botón ⓘ (tooltip) presente', hasInfoBtn)

  await shot('opt-02-config-expandida-multi-tropa', 'Config expandida — % ganancia neta + ⓘ, sin sliders')

  // ─── CAPTURA 2: Pestaña Simulador ─────────────────────────────────────────
  await clickOptimizerTab('Simulador')
  await wait(800)
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot('opt-03-simulador', 'Pestaña Simulador — inputs cantidad disponible por tropa')

  // Verificar que Simulador también carece de sliders
  const rangeCountSim = await page.evaluate(() =>
    document.querySelectorAll('input[type="range"]').length
  )
  check('F6b', 'Simulador: sin sliders range', rangeCountSim === 0)

  // ─── CAPTURA 3: Pestaña Multi-Raid ────────────────────────────────────────
  await clickOptimizerTab('Multi-Raid')
  await wait(800)
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot('opt-04-multi-raid', 'Multi-Raid — inputs cantidad + campo "Mínimo de oasis"')

  // ── Verificación: "Mínimo de oasis" presente ──────────────────────────────
  const bodyTextRaid = await page.evaluate(() => document.body.textContent || '')
  check('F9', '"Mínimo de oasis" visible en Multi-Raid', bodyTextRaid.includes('Mínimo de oasis'))

  const rangeCountRaid = await page.evaluate(() =>
    document.querySelectorAll('input[type="range"]').length
  )
  check('F10', 'Multi-Raid: sin sliders range', rangeCountRaid === 0)

  // ─── CAPTURA 4: Config expandida en Multi-Raid ────────────────────────────
  // (ya debería estar expandida; si no, expandir de nuevo)
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button, div[role="button"]'))
    const cfg = btns.find(b => {
      const txt = b.textContent || ''
      return txt.includes('CONFIGURACIÓN') || txt.includes('Configuración')
    })
    // Solo expandir si no está ya expandido
    const body = document.getElementById('opt-config-body')
    if (!body && cfg) cfg.click()
  })
  await wait(500)
  await shot('opt-05-config-multi-raid', 'Config en Multi-Raid — % ganancia neta + ⓘ, sin sliders')

  // ─── CAPTURA 5: Modo oscuro Multi-Raid ───────────────────────────────────
  await page.evaluate(() => {
    document.documentElement.dataset.theme = 'dark'
  })
  await wait(400)
  await shot('opt-06-multi-raid-dark', 'Multi-Raid modo oscuro')
  await page.evaluate(() => {
    document.documentElement.dataset.theme = 'light'
  })
  await wait(300)

  // ─── CAPTURA 6: Volver a Multi-Tropa ─────────────────────────────────────
  await clickOptimizerTab('Multi-Tropa')
  await wait(800)
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot('opt-07-multi-tropa-final', 'Multi-Tropa final — estado limpio')

} catch (err) {
  console.error('ERROR:', err.message, err.stack)
  try {
    await page.screenshot({ path: path.join(OUT_DIR, 'error-state.png'), fullPage: false })
  } catch (_) {}
} finally {
  await browser.close()
}

// ── Resumen ───────────────────────────────────────────────────────────────────
console.log('\n━━━ Resumen ━━━')
const passed = checks.filter(c => c.passed).length
checks.forEach(c => console.log(`  ${c.passed ? '[OK]' : '[FAIL]'} ${c.id} — ${c.description}`))
console.log(`\n${passed}/${checks.length} checks`)
console.log('Capturas en:', OUT_DIR)
process.exit(passed === checks.length ? 0 : 1)
