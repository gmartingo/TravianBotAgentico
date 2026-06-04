/**
 * test_pathcard_v4.mjs — Verificación visual de PathCard v4
 *
 * Abre /mundos/1, inyecta en el DOM un panel de test con los 4 estados
 * de PathCard v4 (usando los tokens CSS del proyecto cargados en la página)
 * y toma capturas. Solo localhost, nunca Travian.
 *
 * Uso: node scripts/test_pathcard_v4.mjs
 */
import puppeteer from 'puppeteer-core'
import path from 'node:path'

const CHROME =
  process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-first-run', '--hide-scrollbars'],
  defaultViewport: { width: 480, height: 900, deviceScaleFactor: 2 },
})

const page = await browser.newPage()
await page.goto('http://localhost:5173/mundos/1', { waitUntil: 'networkidle2', timeout: 15000 })
await new Promise(r => setTimeout(r, 800))

// ── Inyectar panel de estados v4 usando los tokens CSS ya cargados ──────────
await page.evaluate(() => {
  const existing = document.getElementById('v4-test-panel')
  if (existing) existing.remove()

  const panel = document.createElement('div')
  panel.id = 'v4-test-panel'
  panel.style.cssText = `
    position: fixed; top: 60px; right: 16px; width: 440px; z-index: 9999;
    background: var(--bg); border: 2px solid var(--accent);
    border-radius: 8px; padding: 12px; font-family: var(--font-sans);
    font-size: 13px; overflow: hidden; max-height: 820px; overflow-y: auto;
    box-shadow: 0 8px 32px rgba(0,0,0,.18);
  `

  const btnMini = `
    display:inline-flex;align-items:center;gap:4px;height:24px;padding:0 8px;
    border:1px solid var(--border-strong);background:var(--surface);color:var(--text);
    border-radius:var(--radius-sm);font-family:inherit;font-size:11px;cursor:pointer;flex-shrink:0;
  `
  const header = (label, isDead = false) => `
    display:flex;align-items:center;gap:6px;padding:8px 10px;
    background:${isDead ? 'rgba(201,53,44,.04)' : 'var(--surface)'};
    flex-wrap:wrap;border:1px solid var(--border);border-radius:var(--radius-sm);
    margin-bottom:4px;
  `
  const section = (title) =>
    `<p style="font-size:11px;font-weight:600;color:var(--text-tertiary);margin:10px 0 5px;
    text-transform:uppercase;letter-spacing:.04em;">${title}</p>`

  const originBadge = (origin) =>
    `<span style="display:inline-flex;align-items:center;border-radius:999px;
    padding:1px 7px;font-size:11px;font-weight:500;background:var(--surface-2);
    color:var(--text-secondary);white-space:nowrap;font-family:var(--font-mono);">${origin}</span>`

  const pencilSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
  </svg>`

  panel.innerHTML = `
    <div style="font-weight:700;font-size:12px;margin-bottom:10px;color:var(--text);">
      PathCard v4 — Verificación visual
    </div>

    ${section('1. Idle — ruta activa (lápiz opaco=0 en no-hover)')}
    <div class="path-header" style="${header()}">
      <div style="display:flex;align-items:center;gap:4px;flex:1;min-width:0">
        <button style="appearance:none;border:none;background:transparent;cursor:pointer;
          padding:0;font-family:inherit;font-size:13px;font-weight:500;color:var(--text);
          overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          Ir al mapa mundial
        </button>
        <button class="rename-pencil" aria-label="Renombrar ruta" style="
          appearance:none;border:none;background:transparent;cursor:pointer;padding:4px;
          color:var(--text-tertiary);border-radius:var(--radius-sm);
          display:inline-flex;align-items:center;flex-shrink:0;opacity:0;transition:opacity 150ms;">
          ${pencilSvg}
        </button>
      </div>
      ${originBadge('MAP')}
      <span style="font-size:11px;font-weight:500;color:var(--success);
        background:rgba(36,138,61,.10);border-radius:999px;padding:1px 7px;white-space:nowrap;">
        ● Activa
      </span>
      <button style="${btnMini}">Probar</button>
      <button style="${btnMini}">Editar pasos</button>
      <button style="appearance:none;border:none;background:transparent;cursor:pointer;
        padding:4px;font-size:10px;color:var(--text-tertiary);">▼</button>
      <button aria-label="Más acciones" aria-haspopup="menu" style="
        width:26px;height:26px;border:none;background:transparent;cursor:pointer;
        color:var(--text-tertiary);font-size:14px;border-radius:var(--radius-sm);
        display:inline-flex;align-items:center;justify-content:center;letter-spacing:1px;">
        ⋯
      </button>
    </div>

    ${section('2. Renombrando — input inline activo (Probar/Editar pasos ocultos)')}
    <div style="${header()}">
      <input type="text" value="Ir al mapa mundial" aria-label="Nombre de la ruta" style="
        flex:1;padding:4px 8px;
        border:1px solid var(--border-strong);outline:2px solid var(--accent);
        border-radius:var(--radius-sm);background:var(--surface);color:var(--text);
        font-family:inherit;font-size:13px;min-width:100px;"/>
      <button aria-label="Confirmar renombrado" style="
        width:22px;height:22px;display:inline-flex;align-items:center;justify-content:center;
        border:1px solid var(--border-strong);background:var(--surface);
        border-radius:var(--radius-sm);cursor:pointer;font-size:12px;color:var(--success);">✓</button>
      <button aria-label="Cancelar renombrado" style="
        width:22px;height:22px;display:inline-flex;align-items:center;justify-content:center;
        border:none;background:transparent;border-radius:var(--radius-sm);cursor:pointer;
        font-size:12px;color:var(--text-tertiary);">✕</button>
      ${originBadge('MAP')}
      <span style="font-size:11px;font-weight:500;color:var(--success);
        background:rgba(36,138,61,.10);border-radius:999px;padding:1px 7px;white-space:nowrap;">
        ● Activa
      </span>
      <button style="appearance:none;border:none;background:transparent;cursor:pointer;
        padding:4px;font-size:10px;color:var(--text-tertiary);">▼</button>
      <button style="width:26px;height:26px;border:none;background:transparent;cursor:pointer;
        color:var(--text-tertiary);font-size:14px;display:inline-flex;align-items:center;
        justify-content:center;letter-spacing:1px;">⋯</button>
    </div>

    ${section('3. Error renombrado — label vacío (✓ deshabilitado)')}
    <div style="${header()}">
      <input type="text" value="" placeholder="(vacío)" aria-label="Nombre de la ruta" style="
        flex:1;padding:4px 8px;border:1px solid var(--danger);
        border-radius:var(--radius-sm);background:var(--surface);color:var(--text);
        font-family:inherit;font-size:13px;min-width:100px;"/>
      <button disabled aria-label="Confirmar renombrado" style="
        width:22px;height:22px;display:inline-flex;align-items:center;justify-content:center;
        border:1px solid var(--border-strong);background:var(--surface);
        border-radius:var(--radius-sm);cursor:not-allowed;font-size:12px;
        color:var(--success);opacity:0.5;">✓</button>
      <button aria-label="Cancelar renombrado" style="
        width:22px;height:22px;display:inline-flex;align-items:center;justify-content:center;
        border:none;background:transparent;border-radius:var(--radius-sm);cursor:pointer;
        font-size:12px;color:var(--text-tertiary);">✕</button>
      ${originBadge('MAP')}
      <span style="font-size:11px;font-weight:500;color:var(--success);
        background:rgba(36,138,61,.10);border-radius:999px;padding:1px 7px;">● Activa</span>
      <button style="appearance:none;border:none;background:transparent;cursor:pointer;
        padding:4px;font-size:10px;color:var(--text-tertiary);">▼</button>
      <button style="width:26px;height:26px;border:none;background:transparent;cursor:pointer;
        color:var(--text-tertiary);font-size:14px;display:inline-flex;align-items:center;
        justify-content:center;letter-spacing:1px;">⋯</button>
      <!-- mensaje error segunda línea -->
      <span role="alert" style="width:100%;padding-inline-start:4px;
        font-size:11px;color:var(--danger);">
        El nombre no puede estar vacío.
      </span>
    </div>

    ${section('4. Menú ⋯ abierto — popover "Eliminar ruta"')}
    <div style="${header()} position:relative;">
      <div style="display:flex;align-items:center;gap:4px;flex:1;min-width:0">
        <button style="appearance:none;border:none;background:transparent;cursor:pointer;
          padding:0;font-family:inherit;font-size:13px;font-weight:500;color:var(--text);">
          Ir al mapa mundial
        </button>
      </div>
      ${originBadge('MAP')}
      <span style="font-size:11px;font-weight:500;color:var(--success);
        background:rgba(36,138,61,.10);border-radius:999px;padding:1px 7px;">● Activa</span>
      <button style="${btnMini}">Probar</button>
      <button style="${btnMini}">Editar pasos</button>
      <button style="appearance:none;border:none;background:transparent;cursor:pointer;
        padding:4px;font-size:10px;color:var(--text-tertiary);">▼</button>
      <div style="position:relative;">
        <button aria-label="Más acciones" aria-expanded="true" style="
          width:26px;height:26px;border:none;background:var(--surface-2);cursor:pointer;
          color:var(--text-secondary);font-size:14px;border-radius:var(--radius-sm);
          display:inline-flex;align-items:center;justify-content:center;letter-spacing:1px;">⋯</button>
        <div role="menu" style="
          position:absolute;top:100%;right:0;
          background:var(--surface);border:1px solid var(--border);
          border-radius:var(--radius-sm);box-shadow:0 4px 16px rgba(0,0,0,.14);
          min-width:160px;z-index:50;padding:4px 0;
          margin-top:2px;
        ">
          <div style="padding:6px 12px 4px;font-size:11px;color:var(--text-tertiary);
            font-style:italic;">¿Eliminar esta ruta?</div>
          <button role="menuitem" style="
            width:100%;text-align:start;padding:8px 12px;border:none;
            background:transparent;color:var(--danger);font-size:13px;
            cursor:pointer;font-family:inherit;display:block;
          ">Eliminar ruta</button>
          <div style="display:flex;gap:8px;padding:4px 12px 8px;">
            <button style="font-size:12px;color:var(--text-secondary);
              border:1px solid var(--border);background:transparent;
              padding:2px 10px;border-radius:var(--radius-sm);cursor:pointer;
              font-family:inherit;">Cancelar</button>
          </div>
        </div>
      </div>
    </div>

    ${section('5. Ruta muerta — cabecera is_dead')}
    <div class="path-header" style="${header(false, true)}">
      <span style="color:var(--danger);flex-shrink:0;">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
          aria-hidden="true">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </span>
      <div style="display:flex;align-items:center;gap:4px;flex:1;min-width:0">
        <button style="appearance:none;border:none;background:transparent;cursor:pointer;
          padding:0;font-family:inherit;font-size:13px;font-weight:500;
          color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          Ruta rota
        </button>
        <button class="rename-pencil" style="
          appearance:none;border:none;background:transparent;cursor:pointer;padding:4px;
          color:var(--text-tertiary);border-radius:var(--radius-sm);
          display:inline-flex;align-items:center;flex-shrink:0;opacity:0;transition:opacity 150ms;">
          ${pencilSvg}
        </button>
      </div>
      ${originBadge('DORF1')}
      <span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;
        font-weight:500;color:var(--danger);background:rgba(201,53,44,.10);
        border-radius:999px;padding:1px 7px;font-family:var(--font-mono);white-space:nowrap;">
        ○ Muerta · 3 fallos consecutivos
      </span>
      <button style="${btnMini}">Reactivar</button>
      <button style="${btnMini}">Probar</button>
      <button style="${btnMini}">Editar pasos</button>
      <button style="appearance:none;border:none;background:transparent;cursor:pointer;
        padding:4px;font-size:10px;color:var(--text-tertiary);">▼</button>
      <button style="width:26px;height:26px;border:none;background:transparent;cursor:pointer;
        color:var(--text-tertiary);font-size:14px;display:inline-flex;align-items:center;
        justify-content:center;letter-spacing:1px;">⋯</button>
    </div>
  `

  document.body.appendChild(panel)
})

await new Promise(r => setTimeout(r, 400))
await page.screenshot({ path: '/tmp/noise_v4_pathcard_states.png' })
console.log('OK /tmp/noise_v4_pathcard_states.png')

await browser.close()
