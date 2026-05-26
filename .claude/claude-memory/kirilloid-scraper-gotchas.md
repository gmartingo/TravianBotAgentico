---
name: kirilloid-scraper-gotchas
description: Gotchas técnicos al scrapear travian.kirilloid.ru con zendriver (sirven para Fase 2 mejoras y futuro scraper de edificios)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 77687a70-a3df-46b1-9d4f-f10022f688de
---

Lecciones que costaron ~6 iteraciones al construir el scraper de tropas ([[deferred-game-data-layer]]). El scraper vive en `adapters/scraper/kirilloid_scraper.py` + `scripts/load_kirilloid.py`.

**API de zendriver (instalado, Tab/Element):**
- `Tab.find()/find_all()` buscan por **TEXTO visible**, NO por CSS. Para CSS usar `Tab.select()/select_all()` (lanzan timeout) o `query_selector()/query_selector_all()` (devuelven None/[]). `Element` solo tiene `query_selector(_all)`, no `.find`.
- `Element.text` y `Element.parent` son **properties** (sin `await`, sin paréntesis). NO existe `get_attribute`: usar `el.attrs.get("x")`. El atributo HTML `class` se guarda como **`class_`** en `attrs`.
- `Element.save_screenshot()` ESCRIBE un fichero (jpeg por defecto) y devuelve la ruta (str). Para bytes de imagen: `base64.b64decode(await el.screenshot_b64(format="png", scale=1))`.
- `screenshot_b64` lanza "could not find position" si el elemento está `display:none` o sin caja (p.ej. iconos de columnas de mejora ocultas).

**kirilloid es un SPA con estado en el HASH:**
- `browser.get(url#hash)` cambiando solo el hash NO re-renderiza la tabla; kirilloid solo re-pinta al recibir una interacción (p.ej. click en bandera de `#langbar`). Por eso hay que forzar el re-render (el scraper hace el bucle de idiomas PRIMERO) ANTES de parsear stats/capturar iconos, o se lee la tribu anterior (off-by-one).
- Selectores SIEMPRE por clase/atributo estructural, nunca por texto/`alt` (multilenguaje).

**Numeración de iconos de unidad:** la clase `img.unit.uN` usa un id GLOBAL (romanos u1-u10, germanos u11-u20… = `(tribe_id-1)*10 + ordinal`), mientras que `td.name[unit]` va por-tribu (1-10). Capturar el icono RELATIVO a la fila de la tropa es lo robusto.

**Operativa:** perfil Chrome separado `profiles/scraper_kirilloid`. Un Chrome colgado de una ejecución interrumpida bloquea el perfil (pantalla parpadea, no navega) → cerrarlo antes de relanzar. Los delays humanos NO aplican aquí (kirilloid no es Travian): se usa `asyncio.sleep(0.15)` funcional tras el click de idioma.
