/**
 * profile-noise-drawer.mjs — Profiling real del drawer de ruido.
 *
 * PROBLEMA con la medición anterior:
 *   - El drawer siempre está montado en DOM (optimización anterior).
 *   - waitForSelector('[role="dialog"]') resuelve instantáneamente (~6ms)
 *     porque el elemento YA existe. No mide nada útil.
 *
 * ESTA VERSIÓN mide:
 *   1. Interaction-to-first-contentful-paint del CONTENIDO del drawer:
 *      inyecta un MutationObserver que detecta cuándo el panel pasa de
 *      visibility:hidden a visibility:visible (o transform cambia a translateX(0)).
 *   2. Usa performance.mark() inyectados en el browser para medir:
 *      - t0: justo antes del clic
 *      - t_visible: cuando el panel se anima a visible (CSS transition start)
 *      - t_content_ready: cuando el input del formulario tiene su valor (React re-renderizó)
 *   3. Inyecta un IntersectionObserver en el input del formulario para
 *      detectar cuándo está efectivamente pintado en viewport.
 *   4. Usa PerformanceObserver para capturar "longtask" (>50ms) durante la apertura.
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
  { name: 'prefers-reduced-motion', value: 'reduce' }, // Quitar animación para medir solo React
])
page.on('console', msg => {
  const t = msg.type()
  if (t === 'error' || t === 'warn') console.log(`  [browser ${t}]`, msg.text().slice(0, 200))
  if (msg.text().startsWith('[PROFILE]')) console.log(' ', msg.text())
})

try {
  const worldUrl = `${BASE_URL}/mundos/${WORLD_ID}`
  console.log(`\nNavegando a ${worldUrl} ...`)
  await page.goto(worldUrl, { waitUntil: 'networkidle2', timeout: 30000 })

  // 1. Clic en pestaña Ruido
  const tabClicked = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('nav button, [role="tab"], [role="tablist"] button'))
    const btn = buttons.find(b => {
      const txt = b.textContent.trim().toLowerCase()
      return txt.includes('ruido') || txt.includes('noise')
    })
    if (!btn) {
      // intentar por data-tab o aria-label
      const fallback = document.querySelector('[aria-label*="ruido" i], [aria-label*="noise" i], [data-tab="noise"]')
      if (fallback) { fallback.click(); return true }
      return false
    }
    btn.click()
    return true
  })
  console.log('Clic pestaña Ruido:', tabClicked)

  // Esperar carga inicial del tab (fetch EP-N01 + EP-N03)
  await new Promise(r => setTimeout(r, 2500))
  await page.screenshot({ path: '/tmp/profile-noise-01-tab.png' })
  console.log('Screenshot: /tmp/profile-noise-01-tab.png')

  // 2. Encontrar el botón/fila que abre el drawer
  const destInfo = await page.evaluate(() => {
    // Buscar el dialog drawer (ya montado, cerrado)
    const dialog = document.querySelector('[role="dialog"]')
    if (!dialog) return { error: 'No dialog en DOM' }

    // Buscar filas de la tabla de destinos. En NoiseDestinationsTable
    // cada fila tiene un botón con aria-label o usa onClick en tr.
    const main = document.querySelector('main')
    if (!main) return { error: 'No main' }

    // Estrategia 1: botón dentro de fila de tabla
    const trs = Array.from(main.querySelectorAll('tbody tr'))
    for (const tr of trs) {
      const btn = tr.querySelector('button')
      if (btn) {
        const r = btn.getBoundingClientRect()
        if (r.width > 0) {
          return { strategy: 'table-row-btn', x: r.x + r.width / 2, y: r.y + r.height / 2, label: btn.textContent.trim().slice(0, 60) }
        }
      }
      // La fila misma puede tener role="button" o cursor:pointer
      const r = tr.getBoundingClientRect()
      if (r.width > 0) return { strategy: 'tr-click', x: r.x + r.width / 2, y: r.y + r.height / 2 }
    }

    // Estrategia 2: cualquier elemento con tabIndex y texto que parezca destino
    const candidates = Array.from(main.querySelectorAll('[tabindex], button, tr'))
    for (const el of candidates) {
      const txt = el.textContent.trim()
      if (txt.includes('/') && txt.length > 3 && txt.length < 120) {
        const r = el.getBoundingClientRect()
        if (r.width > 0 && r.height > 0) {
          return { strategy: 'text-url-el', x: r.x + r.width / 2, y: r.y + r.height / 2, label: txt.slice(0, 60) }
        }
      }
    }

    // Diagnóstico: listar todos los botones y inputs del main
    return {
      error: 'No se encontró elemento de destino',
      buttons: Array.from(main.querySelectorAll('button')).slice(0, 15).map(b => ({
        text: b.textContent.trim().slice(0, 40),
        rect: (() => { const r = b.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) } })()
      })),
      trs: trs.length,
    }
  })

  if (destInfo.error) {
    console.log('ERROR al encontrar destino:', JSON.stringify(destInfo, null, 2))
    await page.screenshot({ path: '/tmp/profile-noise-debug.png' })
    await browser.close()
    process.exit(1)
  }
  console.log(`\nDestino encontrado: ${JSON.stringify(destInfo)}`)

  // 3. Inyectar los performance marks en el browser para rastrear React render
  await page.evaluate(() => {
    // Monkey-patch de requestAnimationFrame para detectar el primer frame tras el click
    window.__profileDrawer = {
      t0: null,
      tDialogVisible: null,
      tInputReady: null,
      tFirstFrame: null,
      longtasks: [],
    }

    // PerformanceObserver para long tasks
    try {
      const lo = new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
          window.__profileDrawer.longtasks.push({
            start: Math.round(entry.startTime),
            dur: Math.round(entry.duration),
          })
        }
      })
      lo.observe({ type: 'longtask', buffered: false })
      window.__profileDrawer._longTaskObserver = lo
    } catch (e) { /* longtask no disponible en todos los browsers */ }
  })

  // 4. Ciclo de medición
  const measurements = []
  const allLongtasks = []

  for (let i = 0; i < REPEATS; i++) {
    console.log(`\n--- Iteración ${i + 1}/${REPEATS} ---`)

    // Cerrar drawer si estuviera abierto (presionar Escape)
    const isOpen = await page.evaluate(() => {
      const d = document.querySelector('[role="dialog"]')
      return d && d.getAttribute('aria-hidden') === 'false'
    })
    if (isOpen) {
      await page.keyboard.press('Escape')
      await new Promise(r => setTimeout(r, 300))
    }
    await new Promise(r => setTimeout(r, 200))

    // Limpiar estado de profiling
    await page.evaluate(() => {
      window.__profileDrawer.t0 = null
      window.__profileDrawer.tDialogVisible = null
      window.__profileDrawer.tInputReady = null
      window.__profileDrawer.tFirstFrame = null
      window.__profileDrawer.longtasks = []
      performance.clearMarks()
      performance.clearMeasures()
    })

    // Inyectar watcher ANTES del clic:
    // 1. Observa cuándo el dialog cambia aria-hidden de true a false
    // 2. Observa cuándo el primer input dentro del dialog tiene valor (React terminó de renderizar)
    await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]')
      if (!dialog) return

      // MutationObserver para aria-hidden
      const mo = new MutationObserver((mutations) => {
        for (const m of mutations) {
          if (m.attributeName === 'aria-hidden' && dialog.getAttribute('aria-hidden') === 'false') {
            const now = performance.now()
            window.__profileDrawer.tDialogVisible = now
            performance.mark('drawer-visible')
            console.log(`[PROFILE] drawer aria-hidden→false en ${Math.round(now)}ms abs`)
            mo.disconnect()
          }
        }
      })
      mo.observe(dialog, { attributes: true, attributeFilter: ['aria-hidden'] })
      window.__profileDrawer._mo = mo

      // También observar el style (transform) por si aria-hidden no cambia
      const moStyle = new MutationObserver(() => {
        const style = dialog.style.transform
        const vis = dialog.style.visibility
        if (style === 'translateX(0px)' || style === 'translateX(0)' || vis === 'visible') {
          if (!window.__profileDrawer.tDialogVisible) {
            window.__profileDrawer.tDialogVisible = performance.now()
            performance.mark('drawer-style-visible')
          }
          moStyle.disconnect()
        }
      })
      moStyle.observe(dialog, { attributes: true, attributeFilter: ['style'] })
      window.__profileDrawer._moStyle = moStyle
    })

    // t0: justo antes del clic
    const t0 = await page.evaluate(() => {
      const now = performance.now()
      window.__profileDrawer.t0 = now
      performance.mark('click-start')
      return now
    })

    // CLIC en el destino
    await page.mouse.click(destInfo.x, destInfo.y)

    // Esperar a que React renderice (máx 3s)
    // Estrategia: pooling cada 16ms (1 frame) hasta que:
    //   a) el input dentro del dialog tiene el valor del label del destino, O
    //   b) hay al menos 2 inputs visibles en el dialog, O
    //   c) el panel es visible (transform = translateX(0) o visibility = visible)
    let tContent = null
    const deadline = Date.now() + 3000
    while (Date.now() < deadline) {
      const state = await page.evaluate(() => {
        const dialog = document.querySelector('[role="dialog"]')
        if (!dialog) return { ready: false }

        const ariaHidden = dialog.getAttribute('aria-hidden')
        const style = dialog.style
        const isVisible = ariaHidden === 'false' ||
          style.transform === 'translateX(0px)' ||
          style.transform === 'translateX(0)' ||
          style.visibility === 'visible'

        // ¿Hay inputs visibles?
        const inputs = Array.from(dialog.querySelectorAll('input'))
        const visibleInputs = inputs.filter(inp => {
          const r = inp.getBoundingClientRect()
          return r.width > 0 && r.height > 0
        })

        // ¿Hay contenido de sección (titulos uppercase)?
        const sections = dialog.querySelectorAll('section')

        return {
          ready: isVisible && visibleInputs.length >= 2,
          isVisible,
          inputCount: visibleInputs.length,
          sectionCount: sections.length,
          now: performance.now(),
        }
      })

      if (state.ready) {
        tContent = state.now
        break
      }
      await new Promise(r => setTimeout(r, 16))
    }

    // Medir también cuándo el primer PathCard está visible (NoisePathList)
    let tPathList = null
    const pathListState = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]')
      if (!dialog) return null
      // NoisePathList renderiza divs con border y rutas. Buscar por clase o estructura.
      // Los PathCard tienen `border: 1px solid var(--border)` y marginBottom: 8px
      // Buscamos cualquier div con clase path-header (CSS de app.css)
      const pathHeaders = dialog.querySelectorAll('.path-header')
      if (pathHeaders.length > 0) return { found: true, count: pathHeaders.length, now: performance.now() }

      // Si no hay rutas, buscar el texto del empty state
      const allText = dialog.textContent
      const hasPathSection = allText.includes('Rutas') || allText.includes('Routes') || allText.includes('paths')
      return { found: false, hasPathSection, now: performance.now() }
    })
    tPathList = pathListState?.now ?? tContent

    // Capturar long tasks ocurridas durante este ciclo
    const profile = await page.evaluate((t0ref) => {
      const p = window.__profileDrawer
      const entries = performance.getEntriesByType('measure')
        .concat(performance.getEntriesByType('mark'))
        .filter(e => e.startTime >= t0ref - 5)
        .map(e => ({ name: e.name, start: Math.round(e.startTime), dur: Math.round(e.duration ?? 0) }))

      return {
        tDialogVisible: p.tDialogVisible,
        longtasks: p.longtasks.filter(lt => lt.start >= t0ref - 5),
        marks: entries,
      }
    }, t0)

    const interactionToVisible = tContent != null ? Math.round(tContent - t0) : null
    const interactionToPathList = tPathList != null ? Math.round(tPathList - t0) : null

    console.log(`  t0 (clic):          ${Math.round(t0)} ms (performance.now)')`)
    console.log(`  t_content_ready:    ${tContent != null ? Math.round(tContent) + 'ms abs → ' + interactionToVisible + 'ms desde clic' : 'TIMEOUT'}`)
    console.log(`  t_pathlist:         ${tPathList != null ? Math.round(tPathList) + 'ms abs → ' + interactionToPathList + 'ms desde clic' : 'TIMEOUT'}`)
    if (profile.tDialogVisible) {
      console.log(`  t_aria_hidden→false: ${Math.round(profile.tDialogVisible - t0)} ms desde clic`)
    }
    if (profile.longtasks.length > 0) {
      console.log(`  Long tasks (>50ms):`, JSON.stringify(profile.longtasks))
    }

    measurements.push({
      i: i + 1,
      interactionToVisible,
      interactionToPathList,
      longtasks: profile.longtasks,
    })

    if (i === 0) {
      await page.screenshot({ path: '/tmp/profile-noise-02-drawer.png' })
      console.log('  Screenshot: /tmp/profile-noise-02-drawer.png')
    }

    // Cerrar para siguiente iteración
    await page.keyboard.press('Escape')
    await new Promise(r => setTimeout(r, 300))
  }

  // 5. Ahora medir cambio de destino (si hay > 1 destino)
  console.log('\n--- Midiendo CAMBIO de destino ---')
  // Abrir drawer del primer destino
  await page.mouse.click(destInfo.x, destInfo.y)
  await new Promise(r => setTimeout(r, 600))

  // Buscar si hay un segundo destino para clicar
  const dest2Info = await page.evaluate((firstX, firstY) => {
    const main = document.querySelector('main')
    if (!main) return null
    const trs = Array.from(main.querySelectorAll('tbody tr'))
    if (trs.length < 2) return { onlyOne: true }
    const tr2 = trs[1]
    const btn = tr2.querySelector('button') || tr2
    const r = btn.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  }, destInfo.x, destInfo.y)

  console.log('Segundo destino:', JSON.stringify(dest2Info))

  // 6. Resumen final
  const valid = measurements.filter(m => m.interactionToVisible !== null)
  if (valid.length > 0) {
    const vis = valid.map(m => m.interactionToVisible)
    const plist = valid.filter(m => m.interactionToPathList !== null).map(m => m.interactionToPathList)
    const avg = arr => Math.round(arr.reduce((a, b) => a + b, 0) / arr.length)
    const max = arr => Math.max(...arr)

    console.log('\n=== RESUMEN DE PROFILING ===')
    console.log(`Interaction-to-content-ready:   avg=${avg(vis)}ms  max=${max(vis)}ms  valores=[${vis.join(', ')}]`)
    if (plist.length > 0) {
      console.log(`Interaction-to-pathlist-render: avg=${avg(plist)}ms  max=${max(plist)}ms  valores=[${plist.join(', ')}]`)
    }

    const allLt = valid.flatMap(m => m.longtasks)
    if (allLt.length > 0) {
      console.log(`Long tasks detectadas: ${allLt.length}`)
      allLt.forEach(lt => console.log(`  +${lt.start}ms dur=${lt.dur}ms`))
    } else {
      console.log('Long tasks: ninguna detectada')
    }

    console.log('\n=== DIAGNÓSTICO ===')
    if (avg(vis) > 200) {
      console.log('LENTO (>200ms): cuello en React render o fetch de paths')
    } else if (avg(vis) > 100) {
      console.log('MODERADO (100-200ms): puede sentirse como lag en UI')
    } else {
      console.log('RÁPIDO (<100ms): percepción puede deberse a otro factor (animación, fetch visible)')
    }
  }

  // 7. Diagnóstico de componentes: inspeccionar el árbol del drawer
  console.log('\n=== ÁRBOL DEL DRAWER (snapshot) ===')
  const treeSnap = await page.evaluate(() => {
    const dialog = document.querySelector('[role="dialog"]')
    if (!dialog) return 'No dialog'

    function snap(el, depth = 0) {
      if (depth > 5) return ''
      const tag = el.tagName?.toLowerCase() ?? '?'
      const role = el.getAttribute?.('role') ?? ''
      const cls = el.className ? ` .${el.className.toString().split(' ').slice(0, 2).join('.')}` : ''
      const id = el.id ? `#${el.id}` : ''
      const txt = el.childElementCount === 0 ? ` "${el.textContent.trim().slice(0, 30)}"` : ''
      let out = `${'  '.repeat(depth)}${tag}${id}${cls}${role ? `[${role}]` : ''}${txt}\n`
      for (const child of Array.from(el.children).slice(0, 10)) {
        out += snap(child, depth + 1)
      }
      return out
    }
    return snap(dialog).slice(0, 3000)
  })
  console.log(treeSnap)

} catch (e) {
  console.error('ERROR:', e.message)
  console.error(e.stack?.split('\n').slice(0, 6).join('\n'))
  await page.screenshot({ path: '/tmp/profile-noise-error.png' }).catch(() => {})
} finally {
  await browser.close()
}
