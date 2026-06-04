/**
 * Captura de pantallas para el manual de sesión humana.
 * Ejecutar: node capture-sessions.mjs
 * Prerequisito: app corriendo en http://localhost:5173, world_id=2
 */
import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ASSETS = __dirname;
const BASE = 'http://localhost:5173';
const WORLD_ID = 2;

// Navegar a la pestaña de sesión del mundo
const SESSION_URL = `${BASE}/#/worlds/${WORLD_ID}/session`;

async function waitAndCapture(page, filename, description) {
  console.log(`  Capturando: ${filename} (${description})`);
  await page.waitForTimeout(1200); // esperar animaciones + datos
  await page.screenshot({ path: path.join(ASSETS, filename), fullPage: false });
  console.log(`  OK: ${filename}`);
}

async function navigateToSession(page) {
  // Navegar al mundo - puede necesitar ir primero a la lista de cuentas
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  // Intentar navegar directamente a la sesión del mundo
  await page.goto(`${BASE}/#/worlds/${WORLD_ID}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    locale: 'es-ES',
  });
  const page = await context.newPage();

  try {
    console.log('=== Captura de pantallas: Human Sessions ===');

    // ── 1. Vista principal: tab Sesión ────────────────────────────────────────
    console.log('\n[1] Tab Sesión - estado general');
    await navigateToSession(page);

    // Hacer clic en "Sesión" en el sidebar
    const sessionTabSelectors = [
      'text=Sesión',
      'a[href*="session"]',
      '[data-tab="session"]',
      'button:has-text("Sesión")',
      'a:has-text("Sesión")',
    ];
    let clicked = false;
    for (const sel of sessionTabSelectors) {
      try {
        await page.click(sel, { timeout: 3000 });
        clicked = true;
        console.log(`  Clic en sidebar con: ${sel}`);
        break;
      } catch { /* intentar siguiente */ }
    }
    if (!clicked) {
      console.log('  No se encontró botón de Sesión, intentando navegar por URL...');
      // Intentar ruta directa
      await page.goto(`${BASE}/#/worlds/${WORLD_ID}/session`, { waitUntil: 'networkidle' });
    }
    await page.waitForTimeout(2500);
    await waitAndCapture(page, 'session-01-vista-general.png', 'Tab sesión completo — panel estado + override + calendario');

    // ── 2. Panel de estado (zoom) ──────────────────────────────────────────────
    console.log('\n[2] Panel de estado (detalle)');
    // Tomar captura con viewport más estrecho para enfocarse en el panel
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(500);
    const statusPanel = await page.$('[class*="status"], [data-testid="status"], div:has(> [aria-live])')
      .catch(() => null);
    if (statusPanel) {
      await statusPanel.screenshot({ path: path.join(ASSETS, 'session-02-panel-estado.png') });
      console.log('  OK: session-02-panel-estado.png (elemento)');
    } else {
      // Capturar viewport desde arriba
      await page.setViewportSize({ width: 800, height: 450 });
      await page.waitForTimeout(400);
      await page.screenshot({ path: path.join(ASSETS, 'session-02-panel-estado.png'), clip: { x: 0, y: 0, width: 800, height: 450 } });
      await page.setViewportSize({ width: 1280, height: 900 });
      console.log('  OK: session-02-panel-estado.png (viewport clip)');
    }

    // ── 3. Selector de días + barra de timeline ───────────────────────────────
    console.log('\n[3] Selector de días y barra de timeline');
    // Hacer clic en el primer día (Lun / índice 0) para abrir el editor
    const daySelectors = [
      '[role="tablist"] [role="tab"]:first-child',
      '[role="tablist"] button:first-child',
      'button[aria-selected]',
    ];
    let dayClicked = false;
    for (const sel of daySelectors) {
      try {
        await page.click(sel, { timeout: 2000 });
        dayClicked = true;
        console.log(`  Clic en día con: ${sel}`);
        break;
      } catch { /* intentar siguiente */ }
    }
    await page.waitForTimeout(1500);
    await waitAndCapture(page, 'session-03-selector-dias.png', 'Selector de 7 días + barra de timeline + editor de bloques');

    // ── 4. Editor de bloques (detalle) ────────────────────────────────────────
    console.log('\n[4] Editor de bloques');
    // Scroll al editor
    await page.evaluate(() => {
      const tables = document.querySelectorAll('table');
      if (tables.length) tables[0].scrollIntoView({ behavior: 'smooth' });
    });
    await page.waitForTimeout(800);
    await waitAndCapture(page, 'session-04-editor-bloques.png', 'Editor de bloques del día con tabla start/end/modo');

    // ── 5. Panel de override ──────────────────────────────────────────────────
    console.log('\n[5] Panel de override (botones de modo)');
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(500);
    await waitAndCapture(page, 'session-05-panel-override.png', 'Botones HARDCORE / PASIVO / Descanso total');

    // ── 6. Estado PASIVO seleccionado ─────────────────────────────────────────
    console.log('\n[6] Clic en PASIVO (override)');
    const pasivoSelectors = [
      'button:has-text("PASIVO")',
      'button:has-text("Pasivo")',
      'button[aria-pressed]:nth-of-type(2)',
    ];
    let pasivoClicked = false;
    for (const sel of pasivoSelectors) {
      try {
        await page.click(sel, { timeout: 2000 });
        pasivoClicked = true;
        console.log(`  Clic PASIVO con: ${sel}`);
        break;
      } catch { /* intentar siguiente */ }
    }
    await page.waitForTimeout(2500);
    if (pasivoClicked) {
      await waitAndCapture(page, 'session-06-override-activo.png', 'Override PASIVO activo con countdown y botón cancelar');
    } else {
      console.log('  PASIVO no clicado, capturando estado actual');
      await waitAndCapture(page, 'session-06-override-activo.png', 'Panel override estado actual');
    }

    // ── 7. Modo oscuro ────────────────────────────────────────────────────────
    console.log('\n[7] Modo oscuro');
    // Intentar toggle de tema
    const themeSelectors = [
      'button[aria-label*="tema"]',
      'button[aria-label*="theme"]',
      'button[title*="oscuro"]',
      'button[title*="dark"]',
      '[data-theme-toggle]',
    ];
    let themeToggled = false;
    for (const sel of themeSelectors) {
      try {
        await page.click(sel, { timeout: 2000 });
        themeToggled = true;
        console.log(`  Toggle tema con: ${sel}`);
        break;
      } catch { /* intentar siguiente */ }
    }
    // Alternativa: emular prefers-color-scheme
    if (!themeToggled) {
      await context.close();
      const darkContext = await browser.newContext({
        viewport: { width: 1280, height: 900 },
        locale: 'es-ES',
        colorScheme: 'dark',
      });
      const darkPage = await darkContext.newPage();
      await darkPage.goto(`${BASE}`, { waitUntil: 'networkidle' });
      await darkPage.waitForTimeout(1500);
      // Navegar a sesión
      for (const sel of sessionTabSelectors) {
        try {
          const inWorldFirst = await darkPage.goto(`${BASE}/#/worlds/${WORLD_ID}`, { waitUntil: 'networkidle' });
          await darkPage.waitForTimeout(1500);
          await darkPage.click(sel, { timeout: 2000 });
          break;
        } catch { /* intentar siguiente */ }
      }
      await darkPage.waitForTimeout(2500);
      await darkPage.screenshot({ path: path.join(ASSETS, 'session-07-modo-oscuro.png'), fullPage: false });
      console.log('  OK: session-07-modo-oscuro.png (dark context)');
      await darkContext.close();
    } else {
      await page.waitForTimeout(800);
      await waitAndCapture(page, 'session-07-modo-oscuro.png', 'Vista completa en modo oscuro');
    }

    console.log('\n=== Capturas completadas ===');

  } catch (err) {
    console.error('ERROR:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
