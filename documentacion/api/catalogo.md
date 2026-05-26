# Referencia de API — Catálogo y manejo de errores i18n

Endpoints: `GET /catalog/buildings`, `GET /catalog/troops/{tribe}`
Comportamiento transversal: exception handler global con traducciones

Spec de referencia: [`docs/specs/i18n-backend.md`](../../docs/specs/i18n-backend.md)
Implementación: `adapters/api/routes/catalog.py`, `adapters/api/main.py`

---

## Convención global: cabecera `Accept-Language`

Todos los endpoints del proyecto (salvo `/health`) exigen la cabecera `Accept-Language`.

| Propiedad | Valor |
|---|---|
| Formato | BCP 47 simple: `es`, `en`, `de`, `fr`, `ru` |
| Variantes regionales | Aceptadas y truncadas: `es-ES` → `es`, `en-US` → `en` |
| Cabecera ausente | `400 Bad Request` |
| Idioma no soportado | `400 Bad Request` |
| Idioma por defecto | No hay default silencioso — el header es obligatorio |

Los idiomas soportados son: `de`, `en`, `es`, `fr`, `ru`.

---

## Cabeceras de respuesta presentes en todos los endpoints

Añadidas por el middleware `add_security_headers` (aplicado a todas las respuestas):

| Cabecera | Valor | Descripción |
|---|---|---|
| `X-Request-ID` | UUID v4 | Reutiliza el de la request si llegó; genera uno nuevo si no |
| `X-API-Version` | `0.1.0` | Versión de la API |
| `X-Content-Type-Options` | `nosniff` | Previene MIME sniffing |
| `X-Frame-Options` | `DENY` | Previene clickjacking |
| `Content-Type` | `application/json; charset=utf-8` | Siempre para respuestas JSON |

El `X-Request-ID` de la request se propaga a la respuesta: si el cliente envía `X-Request-ID: abc-123`, la respuesta incluirá ese mismo valor.

---

## `GET /catalog/buildings`

Devuelve el catálogo completo de edificios de Travian con el nombre en el idioma solicitado.

### Request

```
GET /catalog/buildings
Accept-Language: en
```

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `Accept-Language` | Header | Sí | Idioma solicitado |

### Response 200

```
Content-Type: application/json; charset=utf-8
Cache-Control: public, max-age=3600
X-Request-ID: <uuid>
X-API-Version: 0.1.0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
```

**Body — idioma con catálogo completo (`Accept-Language: en`)**:
```json
{
  "buildings": [
    {"gid": 1,  "alias": "woodcutter",  "language": {"en": "Woodcutter"}},
    {"gid": 2,  "alias": "clay_pit",    "language": {"en": "Clay Pit"}},
    {"gid": 3,  "alias": "iron_mine",   "language": {"en": "Iron Mine"}},
    {"gid": 15, "alias": "barracks",    "language": {"en": "Barracks"}}
  ]
}
```

**Body — fallback parcial (`Accept-Language: de` cuando falta alguna entrada)**:

En el estado actual del catálogo, `de` está completo para edificios, por lo que todas las claves serán `"de"`. Si en el futuro alguna entrada queda vacía, la clave sería `"es"` para esa entrada:

```json
{
  "buildings": [
    {"gid": 1, "alias": "woodcutter", "language": {"de": "Holzfäller"}},
    {"gid": 2, "alias": "clay_pit",   "language": {"de": "Lehmgrube"}}
  ]
}
```

**Body — idioma con tropas sin catálogo (`Accept-Language: de`) — para ilustrar fallback**:
Si hubiera un edificio con `"de": ""`, llegaría así:
```json
{"gid": 999, "alias": "future_building", "language": {"es": "Nombre en español"}}
```
La clave `"es"` (en vez de `"de"`) indica que se aplicó el fallback para ese item.

**Schema del body**:
```
BuildingsCatalogResponse
  buildings: list[BuildingItem]
    BuildingItem
      gid: int             — identificador numérico del edificio (gid de Travian)
      alias: str           — nombre legible para logs (ej. "woodcutter") — NO usar para selectores
      language: dict[str, str]  — exactamente una entrada: {idioma_servido: nombre}
```

**Catálogo actual**: 40 edificios (gid 1–40). Todos con traducciones completas en `es`, `en`, `de`, `fr`, `ru`.

### Errores

| Código | Condición | Body |
|---|---|---|
| 400 | `Accept-Language` ausente | `{"detail": "Cabecera 'Accept-Language' obligatoria. Valores válidos: ['de', 'en', 'es', 'fr', 'ru']"}` |
| 400 | Idioma no soportado (ej. `ja`) | `{"detail": "Idioma 'ja' no soportado. Valores válidos: ['de', 'en', 'es', 'fr', 'ru']"}` |

---

## `GET /catalog/troops/{tribe}`

Devuelve las tropas de una tribu con el nombre en el idioma solicitado.

### Request

```
GET /catalog/troops/romans
Accept-Language: es
```

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `tribe` | Path (string) | Sí | Tribu: `romans`, `teutons`, `gauls`, `egyptians`, `huns` (minúsculas) |
| `Accept-Language` | Header | Sí | Idioma solicitado |

FastAPI valida `tribe` contra el enum `Tribe` antes de ejecutar el handler. Si el valor no es un miembro válido del enum, se devuelve 422 automáticamente (sin intervención del código de la app).

### Response 200

```
Content-Type: application/json; charset=utf-8
Cache-Control: public, max-age=3600
X-Request-ID: <uuid>
X-API-Version: 0.1.0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
```

**Body — idioma con catálogo completo (`Accept-Language: es`)**:
```json
{
  "tribe": "romans",
  "troops": [
    {"ordinal": 1, "key": "ROMANS_1",  "language": {"es": "Legionario"}},
    {"ordinal": 2, "key": "ROMANS_2",  "language": {"es": "Pretoriano"}},
    {"ordinal": 3, "key": "ROMANS_3",  "language": {"es": "Explorador de los Imperios"}},
    {"ordinal": 4, "key": "ROMANS_4",  "language": {"es": "Equite de los Imperios"}},
    {"ordinal": 5, "key": "ROMANS_5",  "language": {"es": "Equite de los Imperios II"}},
    {"ordinal": 6, "key": "ROMANS_6",  "language": {"es": "Equite de los Cesares"}},
    {"ordinal": 7, "key": "ROMANS_7",  "language": {"es": "Ariete"}},
    {"ordinal": 8, "key": "ROMANS_8",  "language": {"es": "Catapulta de fuego"}},
    {"ordinal": 9, "key": "ROMANS_9",  "language": {"es": "Senador"}},
    {"ordinal": 10, "key": "ROMANS_10", "language": {"es": "Colono romano"}}
  ]
}
```

**Body — fallback total (`Accept-Language: de` — tropas no tienen `de`)**:
```json
{
  "tribe": "romans",
  "troops": [
    {"ordinal": 1, "key": "ROMANS_1", "language": {"es": "Legionario"}},
    {"ordinal": 2, "key": "ROMANS_2", "language": {"es": "Pretoriano"}}
  ]
}
```
Todas las claves son `"es"` porque el catálogo de tropas en `de` está vacío. El cliente que pida `de` recibirá los nombres en `es` para todas las tropas.

**Schema del body**:
```
TroopsCatalogResponse
  tribe: str               — valor del enum Tribe en minúsculas (ej. "romans")
  troops: list[TroopItem]
    TroopItem
      ordinal: int          — posición en la tribu, base 1 (1..10)
      key: str              — clave de catálogo (ej. "ROMANS_1") — útil para debugging
      language: dict[str, str] — exactamente una entrada: {idioma_servido: nombre}
```

**Tribus y número de tropas**:

| Tribu | Tropas (ordinals) |
|---|---|
| `romans` | 10 (ROMANS_1 a ROMANS_10) |
| `teutons` | 10 (TEUTONS_1 a TEUTONS_10) |
| `gauls` | 10 (GAULS_1 a GAULS_10) |
| `egyptians` | 10 (EGYPTIANS_1 a EGYPTIANS_10) |
| `huns` | 10 (HUNS_1 a HUNS_10) |

### Errores

| Código | Condición | Body |
|---|---|---|
| 400 | `Accept-Language` ausente | `{"detail": "Cabecera 'Accept-Language' obligatoria. Valores válidos: [...]"}` |
| 400 | Idioma no soportado | `{"detail": "Idioma 'XX' no soportado. Valores válidos: [...]"}` |
| 404 | Tribu válida en enum pero sin tropas en catálogo | `{"detail": "No hay tropas definidas para la tribu 'romans' en el catálogo"}` |
| 422 | `tribe` fuera del enum (`persians`, etc.) | Body estándar de FastAPI (Unprocessable Entity) — automático |

**Nota sobre el 404**: el mensaje del 404 está en español fijo (no localizado). Ver divergencia IMPL-03 en el documento de código.

---

## Exception handler global — TravianBotError

Cualquier excepción de dominio (`TravianBotError`) que no sea capturada por un router específico llega a este handler.

### Cómo funciona

1. Extrae el idioma del `Accept-Language` de la request con fallback silencioso a `es`.
2. Busca la plantilla del mensaje en el catálogo usando el `error_code` de la excepción.
3. Interpola los `params` de la excepción en la plantilla.
4. Determina el HTTP status code por `error_code`.
5. Devuelve `JSONResponse` con el mensaje traducido.

### Mapa de error_code → HTTP status

| `error_code` | HTTP status | Excepción |
|---|---|---|
| `ACCOUNT_NOT_FOUND` | 404 | `AccountNotFoundError` |
| `DUPLICATE_ACCOUNT` | 409 | `DuplicateAccountError` |
| `WORLD_NOT_FOUND` | 404 | `WorldNotFoundError` |
| `SESSION_NOT_ACTIVE` | 409 | `SessionNotActiveError` |
| `INVALID_CREDENTIALS` | 401 | `InvalidCredentialsError` |
| `LOGIN_FAILED` | 401 | `LoginFailedError` — login fallido (credenciales, red, clave Fernet rotada). No distingue causa (RN-13 del spec de sesión). Ver [`api/sesion.md`](sesion.md). |
| `VILLAGE_NOT_FOUND` | 404 | `VillageNotFoundError` |
| `FARM_LIST_NOT_FOUND` | 404 | `FarmListNotFoundError` |
| `TROOP_NOT_FOUND` | 404 | `TroopNotFoundError` |
| `BUILDING_NOT_FOUND` | 404 | `BuildingNotFoundError` |
| `LOGIN_ERROR` | 500 | `LoginError` |
| `BROWSER_ERROR` | 500 | `BrowserError` |
| `DATABASE_ERROR` | 500 | `DatabaseError` |
| Cualquier otro | 500 | `TravianBotError` base |

### Body de error estándar

```json
{"detail": "<mensaje localizado según Accept-Language>"}
```

**Ejemplo — `AccountNotFoundError(42)` con `Accept-Language: en`**:
```json
{"detail": "Account 42 not found"}
```

**Ejemplo — mismo error con `Accept-Language: es`**:
```json
{"detail": "Cuenta 42 no encontrada"}
```

**Ejemplo — idioma con fallback a `es` (`Accept-Language: de`, excepción sin plantilla `de`)**:
```json
{"detail": "Mundo 5 no encontrado"}
```
(Mensaje en español porque `WORLD_NOT_FOUND` no tiene plantilla en `de`.)

### Modo verbose (`X-Verbose: true`)

Si la request incluye `X-Verbose: true`, la respuesta añade `error_details`:

```json
{
  "detail": "<mensaje localizado>",
  "error_details": {
    "exception": "core.exceptions.AccountNotFoundError",
    "http_code": 404,
    "timestamp": "2026-05-24T10:30:00+00:00",
    "trace": [
      {
        "file": "/path/to/file.py",
        "line": 42,
        "function": "some_function",
        "locals": {
          "account_id": "42",
          "password": "***REDACTED***",
          "user_data_dir": "***REDACTED***"
        }
      }
    ]
  }
}
```

El modo verbose está pensado exclusivamente para debugging interno del operador del dashboard. Las variables locales de los frames se enmascaran automáticamente:
- `password`, `token`, `api_key`, `authorization` → `***REDACTED***`
- `user_data_dir`, `profile_dir` → `***REDACTED***`
- Cualquier variable cuyo valor contenga un dominio de Travian → `***REDACTED***`

### Cabeceras en respuestas de error

Las mismas cabeceras mínimas que en el resto de respuestas (`X-Request-ID`, `X-API-Version`, `X-Content-Type-Options`, `X-Frame-Options`, `Content-Type`). No incluyen `Cache-Control`.

---

## Notas de implementación para el frontend

- El campo `language` de cada item tiene **exactamente una entrada**. Para obtener solo el nombre: `Object.values(item.language)[0]`.
- Si la clave del campo `language` es diferente al idioma pedido → ese item cayó a fallback. El cliente puede usar esta información para indicar al operador qué traducciones no están disponibles en su idioma.
- El wrapper `BuildingsCatalogResponse` no tiene campo `lang` — el idioma efectivo viaja dentro de cada item, no en el wrapper.
- Los valores en el campo `alias` (ej. `"woodcutter"`) son para logs y debugging; no representan el nombre oficial del edificio ni son estables para selectores.

---

## Divergencias código/spec

Ver sección "Divergencias código/spec" en [`documentacion/backend/i18n.md`](../backend/i18n.md) para el listado completo con evaluación.

Resumen para API:
- **IMPL-02**: `Accept-Language` declarado como opcional a nivel FastAPI para devolver 400 (no 422) cuando falta. Comportamiento correcto, mecanismo no intuitivo.
- **IMPL-03**: el 404 de tribu sin tropas usa `detail` en español fijo (no pasa por `get_message`).

---

🔖 Última revisión: 2026-05-26
