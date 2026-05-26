---
name: third-party-scraper-no-antidetection
description: No aplicar el guardian anti-detección a scrapers de terceros (kirilloid); solo proteger el driver compartido + perfil separado
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 77687a70-a3df-46b1-9d4f-f10022f688de
---

Para scrapers de sitios de TERCEROS (p.ej. kirilloid `build.php`/`troops.php`), NO invocar al agente `guardian-antideteccion` ni aplicar el tratamiento anti-detección completo. kirilloid es una web pública externa: no hay Travian que nos detecte, así que no hay nada que "evadir".

**Why:** el usuario señaló que involucrar al anti-detección para un scraper de una web externa es sobreingeniería. La regla del CLAUDE.md "cambios en adapters/browser/, selectores o timings → guardian" está pensada para código TRAVIAN-FACING, no para scrapers de terceros.

**How to apply:** la única preocupación anti-detección real con estos scrapers es INDIRECTA porque reutilizan el driver de browser y un perfil Chrome compartidos con el bot. Basta un chequeo ligero (yo mismo, sin agente): (1) `adapters/browser/driver.py` intacto (`git diff` vacío), y (2) usan un perfil SEPARADO (`profiles/scraper_kirilloid`), nunca el de una cuenta jugadora. Lo de "selectores estructurales / sin delays humanos" en estos scrapers es robustez/cortesía con kirilloid, NO evasión de Travian. Los tests `test_scraper_kirilloid*_antideteccion.py` están mal etiquetados (son integridad del driver + robustez). Reservar el guardian para `adapters/browser/` y las interacciones reales con Travian. Ver [[kirilloid-scraper-gotchas]] y [[guardian-agent-not-invocable]].
