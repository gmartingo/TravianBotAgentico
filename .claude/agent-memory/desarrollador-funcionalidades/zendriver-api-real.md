---
name: zendriver-api-real
description: API real de zendriver verificada contra el source instalado — evitar reintroducir el bug de usar .find() para CSS
metadata:
  type: feedback
---

API verificada en `.venv/lib/python3.14/site-packages/zendriver/core/`:

**Tab (tab.py)**
- `await page.query_selector(css)` → `Element | None` (None si no existe, NO lanza)
- `await page.query_selector_all(css)` → `list[Element]` ([] si nada)
- `await page.select(css, timeout)` → `Element` (LANZA TimeoutError si no aparece)
- `await page.find(text, ...)` → busca por TEXTO VISIBLE, NO por CSS — no usar para selectores

**Element (element.py)**
- `await el.query_selector(css)` → `Element | None`
- `await el.query_selector_all(css)` → `list[Element]`
- `el.text` → `str` (@property, SIN await, SIN paréntesis)
- `el.text_all` → `str` (@property, concatena texto de hijos)
- `el.parent` → `Element | None` (@property, SIN await — lanza RuntimeError si no tiene tree)
- `el.attrs` → `ContraDict` (dict-like); acceso: `el.attrs.get("unit")`, `el.attrs.get("style")`
- **IMPORTANTE**: el atributo HTML `class` se almacena como `class_` en `attrs` (zendriver remap en `_make_attrs`): usar `el.attrs.get("class_") or el.attrs.get("class")`
- `await el.screenshot_b64(format="png", scale=1)` → `str` (base64); para bytes: `base64.b64decode(...)`
- `await el.save_screenshot(filename, format, scale)` → `str` (ruta del fichero guardado, NO bytes)
- NO existe `el.get_attribute(...)` — obsoleto; usar `el.attrs.get(...)` o `el.get(name)`

**How to apply:** Al implementar cualquier función que interactúe con el browser en este proyecto, verificar siempre contra el source de zendriver antes de usar un método. El error original fue usar `page.find(css)` como si fuera querySelector.
