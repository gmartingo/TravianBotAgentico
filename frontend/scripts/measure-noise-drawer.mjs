/**
 * measure-noise-drawer.mjs — Mide el tiempo desde el clic en un destino hasta que
 * el NoiseDestinationDrawer está pintado e interactivo.
 *
 * Ruta real: /mundos/:worldId  (con pestaña "Ruido" en el sidebar)
 * Solo localhost. Asume worldId=2.
 * Repite N veces (abrir/cerrar) para confirmar que es lento CADA VEZ.
 */
import puppeteer from 'puppeteer-core'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const WORLD_ID = Number(process.env.WORLD_ID || 2)
const REPEATS = Number(process.env.REPEATS || 5)
const BASE_URL = 'http://localhost:5173'

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-first-run', '--no-default-browser-check'],
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 1 },
})

const page = await browser.newPage()
await page.emulateMediaFeatures([
  { name: 'prefers-reduced-motion', value: 'no-preference' },
])

// Redirigir los errores de consola del browser
page.on('console', msg => {
  if (msg.type() === 'error') console.log('  [browser error]', msg.text().slice(0, 120))
})

try {
  // 1. Navegar al mundo
  const worldUrl = `${BASE_URL}/mundos/${WORLD_ID}`
  console.log(`\nNavegando a ${worldUrl} ...`)
  await page.goto(worldUrl, { waitUntil: 'networkidle2', timeout: 20000 })

  // 2. Screenshot estado inicial
  await page.screenshot({ path: '/tmp/noise-01-world.png' })
  console.log('Screenshot: /tmp/noise-01-world.png')

  // 3. Hacer clic en la pestaña "Ruido" del sidebar
  //    El botón tiene aria-current cuando está activo; antes de eso buscamos por texto
  const noiseTabClicked = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('nav button'))
    // Buscar el botón de Ruido (texto puede ser 'Ruido', 'Noise', etc. según idioma)
    // El componente usa t('worldnav.noise')
    const btn = buttons.find(b => {
      const txt = b.textContent.trim().toLowerCase()
      return txt.includes('ruido') || txt.includes('noise') || txt.includes('bruit')
    })
    if (btn) { btn.click(); return { found: true, text: btn.textContent.trim() } }
    return { found: false, labels: buttons.map(b => b.textContent.trim().slice(0, 30)) }
  })
  console.log('Clic pestaña Ruido:', JSON.stringify(noiseTabClicked))

  if (!noiseTabClicked.found) {
    // Fallback: intentar por posición (5o botón del sidebar, índice 4)
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('nav button'))
      if (buttons[4]) buttons[4].click()
    })
  }

  // 4. Esperar a que cargue la tabla de destinos
  //    NoiseTab hace fetch y luego renderiza NoiseDestinationsTable
  await new Promise(r => setTimeout(r, 2000)) // Dar tiempo al fetch inicial

  await page.screenshot({ path: '/tmp/noise-02-tab.png' })
  console.log('Screenshot: /tmp/noise-02-tab.png')

  // Inspeccionar qué hay en la pantalla ahora
  const tabContent = await page.evaluate(() => {
    const main = document.querySelector('main')
    if (!main) return { html: document.body.innerHTML.slice(0, 1500) }
    return {
      buttons: Array.from(main.querySelectorAll('button')).map(b => ({
        text: b.textContent.trim().slice(0, 50),
        role: b.getAttribute('role'),
        type: b.type,
      })).slice(0, 20),
      tables: Array.from(main.querySelectorAll('table')).length,
      rows: Array.from(main.querySelectorAll('tr')).length,
      html: main.innerHTML.slice(0, 1000),
    }
  })
  console.log('Contenido de la pestaña:', JSON.stringify(tabContent, null, 2))

  // 5. Encontrar el elemento clickable que abre el drawer
  //    En NoiseDestinationsTable los destinos se clickan para abrir el drawer.
  //    Según el código, es un botón dentro de una fila de tabla (tr > td > button)
  //    o el tr mismo puede tener onClick.
  const destInfo = await page.evaluate(() => {
    // Buscar el primer botón clickable que parezca una fila de destino
    const main = document.querySelector('main')
    if (!main) return null

    // Tabla de destinos
    const rows = main.querySelectorAll('tbody tr')
    if (rows.length > 0) {
      const firstRow = rows[0]
      const rect = firstRow.getBoundingClientRect()
      // Buscar si la fila tiene un botón de "ver detalle"
      const btn = firstRow.querySelector('button')
      if (btn) {
        const bRect = btn.getBoundingClientRect()
        return { strategy: 'tbody-tr-btn', x: bRect.x + 5, y: bRect.y + 5, text: btn.textContent.trim().slice(0, 50) }
      }
      return { strategy: 'tbody-tr', x: rect.x + rect.width/2, y: rect.y + rect.height/2 }
    }

    // Sin tabla: buscar divs con rol de row
    const roleRows = main.querySelectorAll('[role="row"]')
    if (roleRows.length > 1) {
      const r = roleRows[1].getBoundingClientRect()
      return { strategy: 'role-row', x: r.x + r.width/2, y: r.y + r.height/2 }
    }

    // Último recurso: cualquier botón con texto que parezca una URL o patrón de destino
    const allBtns = Array.from(main.querySelectorAll('button'))
    const destBtn = allBtns.find(b => {
      const t = b.textContent.trim()
      return t.includes('/') && t.length > 3 && t.length < 100
    })
    if (destBtn) {
      const r = destBtn.getBoundingClientRect()
      return { strategy: 'url-btn', x: r.x + 5, y: r.y + 5, text: destBtn.textContent.trim().slice(0, 60) }
    }

    return null
  })

  if (!destInfo) {
    console.log('No se encontró elemento de destino clickable. Volcando HTML para diagnóstico...')
    const html = await page.evaluate(() => document.querySelector('main')?.innerHTML ?? document.body.innerHTML)
    console.log('HTML (primeros 3000):', html.slice(0, 3000))
    await page.screenshot({ path: '/tmp/noise-debug.png' })
    console.log('Screenshot diagnóstico: /tmp/noise-debug.png')
    await browser.close()
    process.exit(1)
  }

  console.log(`\nElemento de destino: ${JSON.stringify(destInfo)}`)

  // 6. Ciclo de medición
  const measurements = []

  for (let i = 0; i < REPEATS; i++) {
    // Asegurar drawer cerrado
    const drawerOpen = await page.evaluate(() => !!document.querySelector('[role="dialog"]'))
    if (drawerOpen) {
      await page.keyboard.press('Escape')
      await new Promise(r => setTimeout(r, 400))
    }

    await new Promise(r => setTimeout(r, 150))

    // MEDIR: t0 antes del clic, t1 cuando el dialog aparece en DOM
    const t0 = await page.evaluate(() => performance.now())
    await page.mouse.click(destInfo.x, destInfo.y)

    // Esperar a que role="dialog" sea visible en el DOM
    let drawerVisible = false
    let t1 = null
    try {
      await page.waitForSelector('[role="dialog"]', { timeout: 5000 })
      t1 = await page.evaluate(() => performance.now())
      drawerVisible = true
    } catch {
      console.log(`  Iter ${i+1}: timeout - el drawer no apareció en 5s`)
      continue
    }

    const drawerMs = Math.round(t1 - t0)

    // Esperar a que haya inputs dentro del dialog (interactivo)
    let interactiveMs = drawerMs
    try {
      await page.waitForFunction(() => {
        const d = document.querySelector('[role="dialog"]')
        return d && d.querySelectorAll('input').length > 0
      }, { timeout: 4000 })
      const t2 = await page.evaluate(() => performance.now())
      interactiveMs = Math.round(t2 - t0)
    } catch { /* usar drawerMs */ }

    measurements.push({ i: i + 1, drawerMs, interactiveMs })
    console.log(`  Iter ${i+1}: drawer visible=${drawerMs}ms  con inputs=${interactiveMs}ms`)

    if (i === 0) {
      await page.screenshot({ path: '/tmp/noise-03-drawer-open.png' })
      console.log('  Screenshot drawer: /tmp/noise-03-drawer-open.png')
    }
  }

  // 7. Resumen
  if (measurements.length > 0) {
    const d = measurements.map(m => m.drawerMs)
    const a = measurements.map(m => m.interactiveMs)
    const avg = arr => Math.round(arr.reduce((x,y) => x+y, 0) / arr.length)

    console.log('\n=== RESULTADO BASELINE ===')
    console.log(`Drawer visible (ms):   avg=${avg(d)}  [${d.join(', ')}]`)
    console.log(`Con inputs (ms):       avg=${avg(a)}  [${a.join(', ')}]`)
    console.log(`Animación declarada:   220ms (noise-drawer-in CSS)`)
    console.log(`Mediciones:            ${JSON.stringify(measurements)}`)
  }

} catch (e) {
  console.error('ERROR:', e.message, e.stack?.split('\n').slice(0,4).join('\n'))
  await page.screenshot({ path: '/tmp/noise-measure-error.png' }).catch(() => {})
  console.log('Screenshot: /tmp/noise-measure-error.png')
} finally {
  await browser.close()
}
