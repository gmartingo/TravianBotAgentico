/**
 * uishot.mjs — tester de UI del frontend LOCAL (solo localhost).
 *
 * ⚠️ Solo para desarrollo del dashboard. NUNCA apuntar a Travian (no es el bot,
 * no toca la capa anti-detección). Usa el Chrome del sistema vía puppeteer-core
 * (sin descargar navegador).
 *
 * Uso:
 *   node scripts/uishot.mjs <out.png> '<stepsJSON>'
 *   node scripts/uishot.mjs <out.png> <steps.json>   (ruta a fichero JSON)
 *
 * steps = array de pasos, ejecutados en orden, captura al final:
 *   {"goto":"http://localhost:5173/cuentas"}     navegar
 *   {"waitFor":".selector"}                        esperar a que aparezca
 *   {"click":"button[aria-haspopup='true']"}       clic
 *   {"fill":["#email","x@y.com"]}                  enfocar y teclear
 *   {"press":"Enter"}                              tecla
 *   {"wait":400}                                   esperar ms
 *
 * Viewport por env: W=1440 H=900 (deviceScaleFactor 1). Chrome por env CHROME_PATH.
 */
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const out = process.argv[2] || '/tmp/uishot.png'
const rawSteps = process.argv[3] || '[]'
let steps
try {
  steps = JSON.parse(rawSteps)
} catch {
  steps = JSON.parse(fs.readFileSync(rawSteps, 'utf8'))
}

const W = Number(process.env.W || 1440)
const H = Number(process.env.H || 900)

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-first-run', '--no-default-browser-check', '--hide-scrollbars'],
  defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
})

const page = await browser.newPage()
// Headless Chrome emula 'reduce motion' por defecto, lo que mata las transiciones
// CSS. Forzamos 'no-preference' para poder verificar animaciones.
await page.emulateMediaFeatures([
  { name: 'prefers-reduced-motion', value: 'no-preference' },
])
try {
  for (const step of steps) {
    if (step.goto) await page.goto(step.goto, { waitUntil: 'networkidle2', timeout: 15000 })
    if (step.waitFor) await page.waitForSelector(step.waitFor, { timeout: 8000 })
    if (step.click) await page.click(step.click)
    if (step.clickText) await page.click(`text/${step.clickText}`)
    if (step.fill) {
      await page.click(step.fill[0])
      await page.type(step.fill[0], step.fill[1])
    }
    if (step.press) await page.keyboard.press(step.press)
    if (step.wait) await new Promise((r) => setTimeout(r, step.wait))
  }
  await page.screenshot({ path: out })
  console.log('OK ' + out)
} catch (e) {
  console.error('STEP ERROR: ' + e.message)
  await page.screenshot({ path: out }).catch(() => {})
  process.exitCode = 1
} finally {
  await browser.close()
}
