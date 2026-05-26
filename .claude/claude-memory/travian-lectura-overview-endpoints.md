---
name: travian-lectura-overview-endpoints
description: Feature de endpoints de lectura de Travian (overview/resources/culture-points/troops) — decisiones compartidas y organización en 4 equipos paralelos
metadata: 
  node_type: memory
  type: project
  originSessionId: cd834879-4582-461e-a117-20ce1252e74c
---

Feature: **endpoints de lectura del estado del juego** desde las páginas de overview agregadas de Travian (icono de resumen arriba a la derecha). Cuatro bloques:
- **overview** — aldeas + movimientos entrantes (ataques/atracos/refuerzos propios y aliados) + construcción en curso (sin tiempo) + entrenamiento + mercaderes libres/totales.
- **resources** — pestañas útiles: almacenado por aldea + sumatorio + mercaderes; producción bruta por aldea (NO resta consumo de cereal del ejército); capacidad almacén/granero. Se omite la pestaña warehouse (% calculable).
- **culture-points** — CP producidos por aldea + fiestas activas y tiempo restante.
- **troops** — own troops (máximo por aldea/tipo), troops in village (presentes ahora), smithy (mejoras + nivel), hospital (curación/salientes), training (tiempo encolado en cuartel/establo/taller/hospital).

Es **estado dinámico del jugador**, distinto de la capa estática de datos de juego del scraper de kirilloid (ver [[deferred-game-data-layer]]).

**Decisiones acordadas (2026-05-25):**
- **Cuándo leer:** en vivo bajo demanda + **caché con TTL corto** (evitar golpear Travian en refrescos seguidos del dashboard).
- **Enfoque:** **parsers desacoplados** HTML→datos, testeados contra **HTML real de muestra que captura el usuario**. NO se depende aún de sesión viva; se cablea cuando exista el `SessionRegistry`. Hoy `adapters/browser/login.py` devuelve un `zd.Browser` vivo pero nadie lo retiene (el `SessionRegistry`/impl de `WorldRuntimePort` sigue diferido, declarado fuera de alcance en docs/specs/login.md).
- **Organización:** **4 equipos en paralelo**, uno por bloque, cada uno con su propio analista + desarrolladores. **palantir y la sesión principal (coordinador) son GLOBALES** por encima de los 4.
- **guardian-antideteccion APLICA** (navegación a Travian + selectores estructurales + timings). Recordar: selectores estructurales, nunca por texto visible (Travian es multilenguaje).
- Toda API exige `Accept-Language` (probablemente `get_language` obligatoria aquí, sin campo `language` en respuesta).

**Why:** los 4 bloques comparten muchísima infraestructura (fetch autenticado de la página overview + caché TTL + utilidades de parseo HTML + mapeo de aldeas + abstracción de la fuente de sesión). Si los 4 equipos van 100% independientes, salen 4 copias duplicadas de ese núcleo. El rol global de palantir es precisamente extraer ese tronco común y que se construya UNA vez.

**How to apply:** correr palantir como gate de entrada global UNA vez sobre todo el feature; luego análisis en paralelo (4 analistas, cada uno escribe su propio spec en docs/specs/, sin colisión); luego palantir revisa los 4 specs juntos para consolidar el tronco compartido; construir el tronco una vez; después implementación por bloque (worktrees aislados para evitar colisión de ficheros).

**REALIDAD CONFIRMADA con HTML real (2026-05-25, servidor ts20.x2.america.travian.com, T4.x galos):**
- Modelo **AGREGADO** (no por-aldea): páginas en `{server}/village/statistics` con pestañas. Cada pestaña = 1 página con TODAS las aldeas (una fila por aldea + `tr.sum` totales). Esto corrige el spec del tronco (docs/specs/lectura-overview-tronco-comun.md) que asumía `dorf1.php/dorf3.php` por aldea → el analista debe rehacerlo a modelo agregado y URLs reales.
- URLs reales: `/village/statistics/overview` (`#overview`), `/resources` (`#ressources`), `/resources/production` (`#production`), `/resources/capacity` (`#capacity`), `/culturepoints` (`#culture_points`), `/troops` o `/troops/own` (`#troops`), `/troops/support` (`.vil_troops` por aldea), `/troops/smithy` (`.under_progress`), `/troops/hospital`, `/troops/training`.
- Aldea = `newdid` en hrefs = `Village.game_id`; nombre = texto del link.
- Tipo de tropa SIEMPRE por clase `img.unit.uNN` (idioma-independiente), nunca por `alt`.
- **Gotcha**: los números vienen con caracteres bidi U+202D/U+202C + separador de miles → `parse_int` debe limpiarlos.
**ESTADO (implementado, 2026-05-25/26):** los 4 bloques IMPLEMENTADOS y verificados contra fixtures. Endpoints: `GET /game/overview/{world_id}`, `/game/resources/{world_id}` (agrega stored+production+capacity), `/game/culture-points/{world_id}`, `/game/troops/{world_id}/{own,support,smithy,hospital,training}`. Suite 623 passed. Patrón hexagonal-limpio: el ROUTER hace `port.get_page_html` + `Parser.parse`; el use case (core) recibe datos parseados (+ lang + translation_port para enriquecer uNN/gid→nombre localizado). Parsers en `adapters/browser/parsers/` (+ `_common.py` helpers), DTOs frozen en `core/dtos/`, use cases en `core/use_cases/`, routers en `adapters/api/routes/game_*.py`. Localización i18n funciona (uNN→`unit_class_to_tribe_ordinal` en `core/utils/units.py`→`translation_port.get_troop_name`); errores localizados vía handler global (códigos OVERVIEW_PAGE_NOT_LOADED/OVERVIEW_FIXTURE_NOT_FOUND añadidos a messages.json). **Chequeo de sesión: cada endpoint, en modo live, devuelve 503 `SessionNotActiveError` (localizado) si no hay navegador vivo — fail-fast en el port.**
- **PENDIENTE para datos reales/prueba manual live: el `SessionRegistry`** (impl de `WorldRuntimePort`) que cablea el navegador logueado al `LiveOverviewAdapter` (`get_browser` hoy es `lambda: None` → siempre 503 en live). Es la siguiente feature. Modo `fixture` (default, `OVERVIEW_SOURCE`) funciona sin sesión.
- **Para arrancar la app**: `python main.py` (uvicorn :8000) necesita `TRAVIAN_BOT_SECRET_KEY` en `.env` (Fernet, feature accounts). En tests, `tests/conftest.py` genera una efímera. `main.py` hace `load_dotenv()`.
- Rama `feature/kirilloid-buildings` con WIP de kirilloid+accounts mezclado; git pendiente de separar con OK del usuario.
- Los **10 fixtures reales** ya guardados en `tests/fixtures/overview/` (overview, resources, resources_production, resources_capacity, culturepoints, troops_own, troops_support, troops_smithy, troops_hospital, troops_training) + un README con selectores, mapa de gid (13 smithy, 17 mercado, 19 cuartel, 20 establo, 21 taller, 24 ayuntamiento, 46 hospital) y gotchas. Tribu detectable por `i.tribeN_medium` (tribe3=Galos).
