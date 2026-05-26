---
name: scraper-utils-extraction
description: adapters/scraper/utils.py centraliza _remove_background/_wait_for_element; kirilloid_scraper.py los re-exporta para compatibilidad con tests existentes
metadata:
  type: project
---

`adapters/scraper/utils.py` contiene las utilidades compartidas entre scrapers de kirilloid:
- `_color_distance` — distancia euclidiana RGBA
- `_remove_background` — flood-fill Pillow para quitar fondo de iconos
- `_wait_for_element` — espera activa de selector CSS (requiere browser en runtime)

`kirilloid_scraper.py` las importa y re-exporta con `# noqa: F401` para no romper los tests
que importan directamente de kirilloid_scraper.

**How to apply:** Todo scraper nuevo importa desde `adapters.scraper.utils`, nunca desde `kirilloid_scraper`.
