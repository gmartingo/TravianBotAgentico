/**
 * uishot-calc.mjs — Capturas para el manual de usuario "Calculadora de combate".
 *
 * Solo localhost:5173. NUNCA Travian ni sitios externos.
 *
 * Uso:
 *   node scripts/uishot-calc.mjs <directorio-salida>
 */
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const BASE_URL = 'http://localhost:5173'
const OUT_DIR = process.argv[2] || '/tmp/calc-caps'

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true })

const W = 1280
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
  localStorage.clear()
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

// Rellena un input de texto por su índice dentro de todos los inputs de la página
// usando el mecanismo nativo de React (dispara evento change correcto)
async function fillInput(idx, value) {
  await page.evaluate(({ idx, value }) => {
    const inputs = Array.from(document.querySelectorAll('input'))
    const inp = inputs[idx]
    if (!inp) return false
    // Nativo de React: setter del objeto nativo
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set
    nativeInputValueSetter.call(inp, value)
    inp.dispatchEvent(new Event('input', { bubbles: true }))
    inp.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  }, { idx, value })
}

// Hace clic en un botón por su texto exacto
async function clickByText(text) {
  return await page.evaluate((text) => {
    const btns = Array.from(document.querySelectorAll('button'))
    const btn = btns.find(b => b.textContent.trim() === text)
    if (btn) { btn.click(); return true }
    return false
  }, text)
}

// Hace clic en el primer botón cuyo texto contenga la cadena (insensible a mayúsculas)
async function clickContaining(text) {
  return await page.evaluate((text) => {
    const btns = Array.from(document.querySelectorAll('button'))
    const btn = btns.find(b => b.textContent.trim().toLowerCase().includes(text.toLowerCase()))
    if (btn) { btn.click(); return true }
    return false
  }, text)
}

try {
  // ─── 1. Navegar a la calculadora ─────────────────────────────────────────────
  console.log('Navigating to /calculadora...')
  await page.goto(BASE_URL + '/calculadora', { waitUntil: 'networkidle2', timeout: 20000 })
  await wait(1500)

  // ─── CAPTURA 1: Estado inicial ────────────────────────────────────────────────
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot('calc-01-vista-inicial', 'Calculadora — estado inicial, pestaña Simulador activa, TribeBar visible')

  // ─── 2. Simulador: seleccionar tribu RO ──────────────────────────────────────
  await clickByText('RO')
  await wait(800)
  await shot('calc-02-tribu-seleccionada', 'TribeBar Romanos seleccionado (RO dorado), TroopGrid con 10 tropas')

  // ─── 3. Rellenar tropas atacantes ────────────────────────────────────────────
  // Listar todos los inputs de la página para debugear
  const inputInfo = await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input'))
    return inputs.map((inp, i) => ({
      i,
      placeholder: inp.placeholder,
      value: inp.value,
    }))
  })
  console.log('Inputs en la página:', JSON.stringify(inputInfo.slice(0, 25)))

  // Los inputs de cantidad del TroopGrid tienen placeholder="0"
  // En Romanos hay 10 tropas atacantes (T1-T10), indices 0..9 (cantidad) intercalados con smithy
  // Estructura: [qty0, smy0, qty1, smy1, ...]
  // Poner 500 en T1 (Legionario) y 200 en T3 (Impedido)
  await fillInput(0, '500')  // T1 cantidad
  await wait(200)
  await fillInput(4, '200')  // T3 cantidad (index 4 = tercer par × 2 - offset de smithy par)
  await wait(400)

  await shot('calc-03-tropas-atacante', 'TroopGrid con cantidades — 500 en columna T1 (Legionario), 200 en T3 (Impedido)')

  // ─── 4. Defensor: tribu NATURE ya seleccionada por defecto ───────────────────
  // La captura actual ya muestra NA en el defensor. Poner animales.
  // Los inputs del defensor NATURE están después de los del atacante
  // 10 tropas atacante × 2 (qty+smithy) = 20 inputs antes + 2 del muro/cantero + algunos más
  // Necesitamos el índice real — usar placeholder="0" para localizarlos
  const allInputsAfter = await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input'))
    return inputs.map((inp, i) => ({
      i,
      placeholder: inp.placeholder,
      value: inp.value,
    }))
  })
  console.log('Todos los inputs:', JSON.stringify(allInputsAfter))

  // Buscar el bloque del defensor: el grupo de inputs después del atacante
  // Normalmente: 10 qty + 10 smithy (atacante) = 20, luego 2 (muro + cantero), luego defensor
  // El TroopGrid del defensor NATURE tiene solo qty (no smithy para animales) = 10 inputs
  // Intentar inputs 22-31 si hay 20+2 antes
  const defStart = allInputsAfter.findIndex((inp, i) => i >= 20 && inp.placeholder === '0' && inp.value === '')
  console.log('Defensor inputs start at index:', defStart)

  if (defStart >= 0) {
    await fillInput(defStart, '40')     // Rata: 40
    await wait(150)
    await fillInput(defStart + 1, '30') // Araña: 30
    await wait(150)
    await fillInput(defStart + 4, '15') // Animal 5 (Jabalí): 15
    await wait(400)
  }

  await shot('calc-04-defensor-oasis', 'Defensor NATURE con animales configurados (Rata 40, Araña 30, Jabalí 15)')

  // ─── 5. Clic en SIMULAR ──────────────────────────────────────────────────────
  const simClicked = await clickContaining('Simular')
  console.log('Simular clicked:', simClicked)
  await wait(4000) // esperar respuesta de la API

  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(400)
  await shot('calc-05-resultado-simulador', 'Resultado del simulador — badge de ganador, ratio, tabla TÚ y DEFENSOR')

  // ─── 6. Scroll para ver las stats ────────────────────────────────────────────
  await page.evaluate(() => window.scrollTo(0, 600))
  await wait(400)
  await shot('calc-06-stats-tabla', 'StatsTable — fuerza infantería/caballería y tabla de recursos (botín, coste, neto)')

  // ─── 7. Cambiar al modo Ataque para ver diferencias ──────────────────────────
  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(300)
  await clickByText('Ataque')
  await wait(500)
  await shot('calc-07-modo-ataque', 'Formulario con modo Ataque activado (catapultas y arietes como asedio)')

  // Volver a Saqueo
  await clickByText('Saqueo')
  await wait(400)

  // ─── 8. Cambiar a la pestaña Optimizador ─────────────────────────────────────
  await clickByText('Optimizador')
  await wait(1200)
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot('calc-08-optimizador-multi-tropa', 'Optimizador — pestaña activa, modo Multi-tropa (Modo A), iconos de tropas T1-T10')

  // ─── 9. Modo "Simulador ejército" (Modo B) ────────────────────────────────────
  await clickByText('Simulador ejército')
  await wait(800)
  await shot('calc-09-modo-simulador-ejercito', 'Modo Simulador ejército (Modo B) — inputs de cantidad disponible por tropa')

  // ─── 10. Modo Multi-raid (Modo C) ─────────────────────────────────────────────
  await clickByText('Multi-raid')
  await wait(800)
  await shot('calc-10-modo-multi-raid', 'Modo Multi-raid (Modo C) — slider Balance, preset de pesos, hint de series de raids')

  // ─── 11. Volver a Multi-tropa, seleccionar tropas y optimizar ─────────────────
  await clickByText('Multi-tropa')
  await wait(600)

  // Seleccionar tribu RO en el optimizador
  const optRoClicked = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'))
    // El TribeBar del optimizador puede tener un "RO" — clicarlo
    const roBtn = btns.find(b => b.textContent.trim() === 'RO')
    if (roBtn) { roBtn.click(); return true }
    return false
  })
  console.log('RO tribe in optimizer:', optRoClicked)
  await wait(800)

  // En Multi-tropa los iconos son clickeables (seleccionar tipos)
  // Clic en T1 y T2 para seleccionarlos
  await page.evaluate(() => {
    // Buscar los chips de tropas del optimizador (T1, T2, etc.)
    const troopChips = Array.from(document.querySelectorAll('[class*="troop"], [title^="T"]'))
    if (troopChips.length >= 2) {
      troopChips[0].click()
      troopChips[1].click()
    }
    // Alternativa: buscar divs/botones con imágenes de tropas
    const divs = Array.from(document.querySelectorAll('div[style*="cursor: pointer"], div[style*="cursor:pointer"]'))
    divs.slice(0, 2).forEach(d => d.click())
  })
  await wait(600)

  // Poner animales en DEFENSA DEL OASIS del optimizador
  const optInputInfo = await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input'))
    return inputs.map((inp, i) => ({ i, placeholder: inp.placeholder, value: inp.value }))
  })
  console.log('Optimizer inputs:', JSON.stringify(optInputInfo))

  // Los inputs del defensor del oasis son los que tienen placeholder="0" en el optimizador
  // En Multi-tropa no hay inputs de cantidad para el atacante (solo selección visual)
  // Los de DEFENSA DEL OASIS son los primeros que encontramos
  if (optInputInfo.length > 0) {
    await fillInput(optInputInfo[0].i, '30') // primer animal: 30
    await wait(150)
    if (optInputInfo.length > 2) {
      await fillInput(optInputInfo[2].i, '20') // tercer animal: 20
      await wait(150)
    }
  }

  // Clic en Optimizar
  const optClicked = await clickContaining('Optimizar')
  console.log('Optimizar clicked:', optClicked)
  await wait(7000) // el optimizador puede tardar varios segundos

  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(500)
  await shot('calc-11-resultado-optimizador', 'Resultado del optimizador — lista de alternativas Pareto con rank, tropas y recursos')

  // ─── 12. Ver el detalle de la primera alternativa ─────────────────────────────
  // Intentar clic en la primera fila del resultado
  const detailOpened = await page.evaluate(() => {
    // Buscar botones de "Ver detalle" o filas expandibles
    const btns = Array.from(document.querySelectorAll('button'))
    const det = btns.find(b =>
      b.textContent && (
        b.textContent.toLowerCase().includes('detalle') ||
        b.textContent === '›' || b.textContent === '▶' || b.textContent === '>'
      )
    )
    if (det) { det.click(); return 'detail-button' }

    // Buscar filas con tabindex o cursor pointer
    const rows = Array.from(document.querySelectorAll('[tabindex="0"], [role="row"]'))
    if (rows.length > 1) { rows[1].click(); return 'row' }

    // Buscar el primer elemento clickeable en el resultado del optimizador
    const resultDivs = Array.from(document.querySelectorAll('div'))
      .filter(d => {
        const s = window.getComputedStyle(d)
        return s.cursor === 'pointer' && d.offsetHeight > 30 && d.offsetWidth > 100
      })
    if (resultDivs.length > 0) { resultDivs[0].click(); return 'div-pointer' }
    return null
  })
  console.log('Detail opened:', detailOpened)
  await wait(1200)

  await page.evaluate(() => window.scrollTo(0, 0))
  await wait(400)
  await shot('calc-12-detalle-alternativa', 'Detalle inline de alternativa del optimizador con TravianReport completo')

  // ─── 13. Resultado con datos reales del simulador — disparar con API ──────────
  // Volver al simulador y forzar un resultado real llamando a la API con datos conocidos
  await clickByText('Simulador')
  await wait(1000)

  // Inyectar resultado conocido via la API de React si es posible
  // Alternativa: abrir el resultado directamente usando fetch desde el browser
  await page.evaluate(async () => {
    // Llamar a la API desde el browser para tener un resultado real
    // Esto simula exactamente lo que haría el usuario
    const resp = await fetch('/api/combat/simulate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept-Language': 'es',
      },
      body: JSON.stringify({
        attacker: {
          tribe: 'romans',
          attack_type: 'raid',
          troops: [
            { ordinal: 1, quantity: 500, smithy_level: 0 },
            { ordinal: 3, quantity: 200, smithy_level: 0 },
          ],
          hero_attack_points: 0,
          hero_attack_bonus_percent: 0,
          alliance_bonus: 0,
          morale: 100,
          artifacts: { fast_troops: 1.0, diet: 1.0 },
          catapult_targets: [],
          rams: null,
        },
        defenders: [{
          tribe: 'nature',
          troops: [
            { tribe: 'nature', ordinal: 1, quantity: 40, smithy_level: 0 },
            { tribe: 'nature', ordinal: 2, quantity: 30, smithy_level: 0 },
            { tribe: 'nature', ordinal: 5, quantity: 15, smithy_level: 0 },
          ],
          hero_defense_points: 0,
          hero_defense_bonus_percent: 0,
          artifacts: { strong_buildings: 1.0, great_cranny: 1.0 },
          village_resources: null,
        }],
        wall: { wall_level: 0, stonemason_level: 0, wall_tribe: null },
        config: { server_speed: 1.0, distance_fields: null },
      }),
    })
    const data = await resp.json()
    window._lastCombatResult = data
    console.log('API result:', JSON.stringify(data).substring(0, 200))
  })
  await wait(500)

  const apiResult = await page.evaluate(() => window._lastCombatResult)
  console.log('API result keys:', apiResult ? Object.keys(apiResult) : 'null')
  console.log('Attacker wins:', apiResult?.attacker_wins, 'Ratio:', apiResult?.ratio)

} catch (err) {
  console.error('ERROR:', err.message)
  try {
    await shot('calc-error-state', 'Estado de error durante la captura')
  } catch (_) {}
} finally {
  await browser.close()
  console.log('\nCapturas completadas en:', OUT_DIR)
}
