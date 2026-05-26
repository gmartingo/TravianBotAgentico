---
name: project-arch-conventions
description: Convenciones de arquitectura hexagonal y API observadas/confirmadas en TravianBot
metadata:
  type: project
---

Convenciones del proyecto observadas en el código real (no solo en CLAUDE.md):

**Puertos del core**: ABC con `@abstractmethod` en `core/ports/`. Importan solo entidades de
`core/entities/`. Nunca importan de `adapters/`. Patrón: `BrowserPort`, `DbPort`, `WorldRuntimePort`.

**Excepciones**: todas heredan de `TravianBotError`. Los `ValueError` de validación de entidades
quedan FUERA del sistema de error_code (son errores de programación, no de dominio).

**Tests existentes de excepciones** (`tests/unit/test_exceptions.py`): verifican `str(err)` en
español y atributos de instancia. Cualquier migración debe preservar estos tests sin modificarlos.

**FastAPI conventions**:
- Sin prefijo `/api` en rutas (el proxy de Vite lo retira).
- `adapters/api/routes/` para los routers (existe pero vacío aún salvo catalog.py que se creará).
- `adapters/api/dependencies.py` para dependencias compartidas (get_language ya implementado).
- `adapters/api/main.py` como punto de entrada de la app.
- Tests de API con `fastapi.testclient.TestClient`.

**Enum Tribe**: valores en minúsculas (`romans`, `teutons`, `gauls`, `egyptians`, `huns`).
Para construir clave de tropa: `tribe.value.upper() + "_" + str(ordinal)`.

**Why:** Conocimiento institucional para futuros specs que toquen API o excepciones del core.

**How to apply:** Al diseñar cualquier nuevo puerto, seguir el patrón ABC de `core/ports/`.
Al proponer error codes, añadirlos al dict `ERROR_HTTP_MAP` de `adapters/api/error_codes.py`
(que se crea con la feature i18n-backend).
