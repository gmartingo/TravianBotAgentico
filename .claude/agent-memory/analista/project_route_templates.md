---
name: project-route-templates
description: Portal desarrollador rutas — v1 implementada (Fase A); v2 ready-for-impl (rev.3 gaps anti-detección cerrados); 4 invariantes guardian incorporados al spec
metadata:
  type: project
---

## Portal de Desarrollador de Rutas (`docs/specs/route-templates-developer-portal.md`)

**Estado v1:** `implemented` (Fase A backend completada; Fases B router HTTP y C UI pendientes)
**Estado v2 — Rutas Atómicas Componibles:** `ready-for-impl` PENDIENTE gate `desarrollador-apis` sobre §v2.8

### Modelo de datos clave

- Nueva entidad `RouteTemplate` (global, sin world_id) + `RouteTemplatePath` → `core/entities/noise.py`
- Reutiliza `NavigationStep` existente sin cambios
- 3 tablas nuevas: `route_templates`, `route_template_paths`, `route_template_steps`
- Nuevo adaptador: `adapters/db/route_template_sqlite_adapter.py`
- Nuevo puerto: `core/ports/route_template_db_port.py`
- Migración M-RT01: `template_id INTEGER REFERENCES route_templates(id) ON DELETE SET NULL` en `noise_destinations`

### Decisiones cerradas

1. **Instancias independientes** tras clonar: re-sync solo explícito (EP-RT09). No hay push automático.
2. **Colisión de clonado** (UNIQUE world_id+url_pattern): 409 con `conflicting_destination_id`; `force=true` hace UPSERT.
3. **Borrado de plantilla**: instancias quedan con `template_id=NULL` (ON DELETE SET NULL). No destructivo.
4. **Re-sync (EP-RT09)**: reemplaza paths/steps atómicamente; preserva `navigation_weight`, `is_dead`, `consecutive_failures_count`, `last_used_at` de la instancia.
5. **Idempotencia de clon**: misma plantilla + mismo mundo → 200 (ya existe), no 201.

### Endpoints nuevos EP-RT01..RT10

- EP-RT01: `GET /route-templates` (lista, filtro category, include_paths)
- EP-RT02: `POST /route-templates` (crear)
- EP-RT03: `GET /route-templates/{id}` (detalle con paths+steps)
- EP-RT04: `PUT /route-templates/{id}` (PATCH; slug/category/url_pattern inmutables)
- EP-RT05: `DELETE /route-templates/{id}` (instancias quedan huérfanas)
- EP-RT06: `GET /route-templates/{id}/paths`
- EP-RT07: `POST /route-templates/{id}/clone-to-world/{world_id}?force=`
- EP-RT08: `POST /worlds/{id}/noise/apply-templates` (bulk, no atómico)
- EP-RT09: `POST /route-templates/{id}/sync-to-world/{world_id}`
- EP-RT10: `POST /route-templates/{id}/test` (wrapper de EP-N14 existente)

### Modificaciones a endpoints existentes

- EP-N03 response: añade campo `template_id` (null o int)
- EP-N04 request: acepta `template_id` opcional

### Seed inicial (~20 plantillas)

Categorías: navegación estándar (6), edificios (10 con gids verificados), perfil/oasis (4).
Gids clave del catálogo:
- rally_point=13, academy=14, barracks=15, stable=16, trade_office=20
- great_market=21, embassy=22, hero_mansion=23, warehouse=10, granary=11
- Farm list = submenú de rally_point (gid=13), NO gid propio

### Frontend — mapa de reutilización de componentes (palantir gate cierre)

- Nueva ruta `/rutas` en `App.jsx` bajo `ManagementShell`
- Nuevo fichero `frontend/src/pages/RouteTemplatesPage.jsx` (stub; orquesta hijos directamente)
- `NoiseTab` NO se monta en `/rutas` (sus efectos dependen de `worldId`)
- REUTILIZAR sin tocar: `NoisePathWizard`, `NoiseStepEditor`, `NoiseWizardStepForm`,
  `NoiseDerivedSelectorFeedback`, `NoiseOriginSelector` (pasar origins por prop en modo controlled)
- AJUSTAR con prop `mode: "world"|"template"` sin duplicar: `NoiseDestinationsTable`,
  `NoiseDestinationDrawer` (hoy fetcha `getNoisePaths(worldId, dest.id)` internamente)

### Notas anti-detección

- Steps de plantillas siguen las mismas restricciones: delay_min_ms >= 200, delay_max_ms <= 5000
- Sin Accept-Language en endpoints de plantillas (datos del desarrollador, no localizados)

### v2 rev.2 — navigation_weight fuera de la plantilla (2026-06-05)

**DECISIÓN CERRADA:** `navigation_weight` NO pertenece a la plantilla global.

- `RouteTemplate` dataclass: sin campo `navigation_weight`, sin validación de rango en `__post_init__`.
- `route_templates` SQL: columna eliminada con migración idempotente M-RT03 (`ALTER TABLE … DROP COLUMN`).
  SQLite >= 3.35 soporta DROP COLUMN. El catálogo está vacío al aplicar, sin pérdida de datos.
- `seeds/route_templates.json`: sin campo `navigation_weight` en ningún ítem.
- EP-RT02/03/04/01: sin `navigation_weight` en request ni response de plantilla.
- **EP-RT07** `clone-to-world`: request body incluye `navigation_weight` (default 1.0, rango [0.1, 5.0]).
  El handler pasa ese valor como `frequency_weight` al crear el `NoiseDestination`.
- **EP-RT08** `apply-templates`: request body incluye `default_navigation_weight` (default 1.0).
  Peso uniforme para toda la operación bulk. Para pesos distintos por plantilla, usar EP-RT07 individualmente.
- **EP-RT09** `sync-to-world`: NO toca `frequency_weight` del destino (igual que antes).
- UI catálogo (`/rutas`): formulario crear/editar sin campo de peso; tabla global sin columna peso.
- UI clonar a mundo: slider/input `navigation_weight` visible SOLO en el flujo de clonado/asignación.
- UI tabla por-mundo: `NoiseDestinationsTable` en modo "world" sigue mostrando el peso como siempre.
- Migración M-RT03 añadida como función en `RouteTemplateSQLiteAdapter.ensure_tables()`.
- Ver §v2-PESO en el spec para el resumen completo.

### Extensiones al subsistema de noise (palantir gate cierre)

- `NoiseDbPort.create_destination` → añadir `template_id: int | None = None` (retrocompatible)
- `NoiseSQLiteAdapter.create_destination` → igual; actualizar INSERT para incluir la columna
- `NoiseDbPort` + `NoiseSQLiteAdapter` → añadir métodos nuevos:
  - `find_destination_by_url(world_id, url_pattern) → NoiseDestination | None`
  - `find_destination_by_template(world_id, template_id) → NoiseDestination | None`
- `_validate_url_pattern` y `_same_or_subdomain` (≈línea 570 de noise_sqlite_adapter.py)
  ya existen → REUTILIZAR en el handler de clonado, NO copiar. Opción A: importar directamente;
  opción B: extraer a `adapters/db/_url_validation.py`. Decisión para el implementador.

### Seed

- Datos en `seeds/route_templates.json` (NO en `seeds/game_data/` ni constantes Python)
- `seed_route_templates()` lee el JSON; no usa `seed_loader.py` (exclusivo de kirilloid)

### EP-RT10 test en vivo

- Estrategia: clonar temporal → leer NavigationPath real de BD → execute_path_test → borrar (try/finally)
- Si ya existe instancia clonada del mundo: usar esa, no clonar temporal

### v3 — Modo PROBAR RUTA con sesión gestionada desde /rutas (2026-06-05)

**DECISIONES CERRADAS v3:**

1. **`_ensure_session`**: helper privado en el handler de EP-RT10 (adaptador API, no core).
   Idempotente: `is_active → return`. Si no hay sesión → `get_account_id_for_world` → `LoginUseCase.execute`.
   Errores: `WorldOrphanError`→404, `FernetDecryptionError`→401, `LoginFailedError`→401.

2. **`execute_path_test_standalone`**: función module-level en `core/scheduling/world_agent.py`
   (no método de WorldAgent). Recibe `browser, path, lock`. WorldAgent.execute_path_test
   se convierte en thin wrapper. Opción (c) elegida (no WorldAgent on-demand, no status quo).

3. **EP-RT10-v3**: elimina restricción `RUNNING && _session_active`. Llama `_ensure_session`
   primero. Luego: si WorldAgent RUNNING → su método; si no → `execute_path_test_standalone`
   con lock ad-hoc. Nuevo 401 (Fernet/login), nuevo 404 (mundo sin cuenta). 409 "desconectado" desaparece.

4. **EP-RT12 NUEVO**: `DELETE /worlds/{world_id}/session` — cierra Chrome de un mundo desde
   cualquier contexto. En `farm.py` (cohesión con gestión de ciclo de vida del mundo). 204 idempotente.

5. **`stop_agent` ajustado**: tras `request_stop()` también `session_registry.close_session(world_id)`.
   Retrocompatible (sin cambio de contrato HTTP). Parar mundo = cerrar Chrome.

6. **`WorldOrphanError`**: nueva excepción en `core/exceptions.py`, campo `world_id: int`.

7. **Anti-detección**: mantener sesión entre tests es CORRECTO (menos logins = menos firmas de bot).
   Guardian debe auditar `_ensure_session` (login on-demand) y `execute_path_test_standalone`.

8. **Gates pendientes**: desarrollador-apis (EP-RT10-v3 / EP-RT12) + guardian (ensure_session + standalone).

**ENDPOINTS v3:**
- EP-RT10: contrato ajustado (ver §v3.4.1 del spec)
- EP-RT12 NUEVO: `DELETE /worlds/{world_id}/session` → `farm.py`

### v2 — Rutas Atómicas Componibles (2026-06-05)

**DECISIONES CERRADAS v2:**

1. **Granularidad atómica**: 1 ruta = 1 clic. Profundidad = cadena de rutas con `origin_template_id`.
2. **Auto-referencia FK nullable**: `route_templates.origin_template_id INTEGER REFERENCES route_templates(id) ON DELETE SET NULL`.
   - NULL = raíz (ejecutable desde cualquier parte, equivale a NavigationOrigin.ANY).
   - int = clicar primero la cadena del origen, luego el clic propio.
   - ON DELETE SET NULL: borrar origen convierte las hijas en raíces.
3. **Anti-ciclos**: `validate_no_cycle` en `core/use_cases/route_template_service.py`. → 409 con `cycle_path`. Límite: 20 niveles.
4. **Resolución de cadena**: `resolve_origin_chain` → `list[ResolvedStep]`. Servicio puro en core. Lo usa el motor y EP-RT11.
5. **Seed v2**: 2 pasadas (raíces primero, hijas con `origin_slug` en JSON). Catálogo v1 vaciado (seeds/route_templates.json reseteado a []).
6. **Motor (world_agent.py)**: requiere gate guardian-antideteccion antes del commit (Paso v2-8). El motor lee route_templates globales en tiempo de ejecución; el clon de una hija NO arrastra el clon del origen.
7. **Endpoint nuevo**: EP-RT11 `GET /route-templates/{id}/chain` — cadena resuelta para render en tabla de UI.
8. **origin en route_template_paths**: patrón `"ROUTE_TEMPLATE:<id>"` (análogo a `VILLAGE_<n>` existente) para rutas con origen.

**ENDPOINTS delta v2 (gate desarrollador-apis PENDIENTE):**
- EP-RT01: añadir `origin_template_id` a cada ítem response
- EP-RT02: añadir `origin_template_id` request/response; validar anti-ciclos
- EP-RT03: añadir `origin_template_id` al response
- EP-RT04: `origin_template_id` ahora editable (no era campo antes)
- EP-RT11 NUEVO: `GET /route-templates/{id}/chain`

**Migración:** M-RT02 — `ALTER TABLE route_templates ADD COLUMN origin_template_id`

**REGLA ANTI-DETECCIÓN v2 — NO NEGOCIABLE (rev.1 2026-06-05):**

9. **Vector de navegación = human_click exclusivo, nunca browser.get:**
   - Una ruta NUNCA se accede por URL directa. SIEMPRE clicando el hipervínculo/botón
     con `human_click`/`human_click_at_rect` (Bézier + gaussiana truncada en el rect).
   - `url_pattern` y `expected_url_after_click` son SOLO datos de verificación: se
     comparan con la URL actual del browser tras el click. Nunca se pasan a browser.get.
   - `ORIGIN_PATHS` queda obsoleto como mecanismo de navegación en cadenas atómicas.
     Puede conservarse como etiqueta semántica para compatibilidad con noise v1.
   - Si un elemento no aparece (verificación de URL del eslabón anterior falló), se aborta
     la cadena y se reporta el eslabón fallido. human_click hace scroll internamente si el
     elemento está offscreen (no añadir lógica de scroll en el motor).
   - Esto aplica también al modo test (EP-RT10): el test recorre la cadena por clicks,
     no por URL.
   - Gate guardian-antideteccion OBLIGATORIO sobre el Paso v2-8 antes de commitear
     world_agent.py. El guardian verifica: cero browser.get en la cadena, delays
     humanizados [delay_min_ms, delay_max_ms], verificación de URL solo como check.
   - Ver §v2-REGLA-NAV en el spec para la especificación completa.

### v2 rev.3 — Cierre de gaps anti-detección del guardian (2026-06-05)

**4 gaps cerrados como invariantes de diseño en el spec:**

**GAP-1 (INVARIANTE-NAV-01):** guard de tipo explícito al inicio de `_execute_noise_action`
y `execute_path_test` en world_agent.py. El bloque con `browser.get(anchor_url)` del flujo
v1 es estructuralmente INALCANZABLE cuando `path.origin.startswith("ROUTE_TEMPLATE:")`.
La verificación es por `grep -n "browser\.get\|tab\.get"` sobre la rama atómica — debe
devolver cero resultados. El guardian lo verifica antes del merge.

**GAP-2 (INVARIANTE ARRANQUE EN FRÍO — §v2-ARRANQUE-FRIO):** Si el browser no está en una
página válida de Travian (dominio incorrecto, pantalla de login), el motor ABORTA con
`ColdStartAbortError` y el scheduler reintenta en la próxima ventana. PROHIBIDO resolver
arranque en frío con cualquier forma de browser.get/tab.get. La noise_destination NO se
marca is_dead por este fallo. Detección sin navegar: URL del tab pertenece al dominio del
world_server Y no es pantalla de login.

**GAP-3 (piso defensivo en runtime):** El motor aplica `max(200, step.delay_min_ms)` en
lugar de `step.delay_min_ms` directamente. Defensa en profundidad: protege incluso si el
dato en BD llega corrupto con valor menor de 200. Cero coste adicional.

**GAP-4 (selectores estructurales obligatorios — §v2-REGLA-SELECTORES):** EP-RT02 y
EP-RT04 rechazan con 422 cualquier selector que contenga `:has-text(`, `:contains(`,
`text()=` o `contains(text(),`. Mensaje de error legible con explicación multi-idioma.
Patrón consistente con la validación de `delay_min_ms < 200` ya existente. EC-RT12
actualizado para reflejar el nuevo comportamiento. No requiere re-gate de desarrollador-apis.

**Criterios de aceptación nuevos:** CA-V2-16 (grep sobre rama atómica), CA-V2-17 (arranque
en frío), CA-V2-18 (piso de delay + 422 de selector).

**Tests nuevos:** TI-V2-11..TI-V2-15 en §v2.12.

**Recomendación seed (no bloqueante):** variar rangos delay entre eslabones; añadir dwell
en páginas de contenido; nunca delay_min = delay_max; preferir números "sucios" a redondos.

**Why:** El usuario quiere curar un catálogo maestro de rutas de Travian de forma global y clonarlas a cada mundo.
**How to apply:** Al diseñar futuros endpoints de ruido o templates, verificar este modelo primero. La entidad RouteTemplate vive en noise.py. En v2, la composición es por auto-referencia FK, no por multi-step por ruta. En cualquier lógica de ejecución de rutas: siempre human_click, nunca browser.get. Los gaps cerrados en rev.3 son invariantes de diseño que deben respetarse en cualquier extensión futura del motor de ejecución de rutas.
