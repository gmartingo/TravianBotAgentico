---
id: task-order-randomization
titulo: Aleatorización de Orden en Tareas Iterativas
estado: ready-for-impl
fecha: 2026-05-30
autor: analista
apis_validadas_por_desarrollador_apis: ok
apis_validadas_fecha: 2026-05-30
---

# Aleatorización de Orden en Tareas Iterativas

## 1. Objetivo de negocio

El bot fue baneado por Travian (primera ofensa: downgrade del 33% de edificios). Una de las
causas identificadas: el bot recorría siempre sus colecciones (farm lists, aldeas, slots) en
el mismo orden determinista. Un analizador de comportamiento puede detectar que las mismas
farm lists se envían en la misma secuencia exacta en cada ciclo.

Este spec introduce un **helper transversal de aleatorización de orden** que el bot aplica
cada vez que itera sobre una colección. El orden de cada recorrido se elige aleatoriamente
entre tres estrategias:

- **DEFAULT**: el mismo orden en que el sistema tiene los elementos (top→down, igual que
  Travian muestra las listas en pantalla).
- **REVERSED**: orden inverso (bottom→top).
- **SHUFFLE**: orden completamente aleatorio (permutación aleatoria).

El helper es un **utility puro** — sin IO, sin estado, sin efectos secundarios — que toma
una lista y devuelve una copia reordenada. La estrategia a usar se elige aleatoriamente con
probabilidad configurable (default: 33%/33%/33%) aplicando la misma configuración global a
todos los puntos de aplicación.

---

## 2. Actores y permisos

| Actor | Rol |
|---|---|
| Bot (WorldAgent, use cases) | Llama a `apply_order(items)` antes de iterar sobre cualquier colección que deba tener orden aleatorio. |
| Usuario | Puede consultar y modificar la distribución de probabilidad de órdenes vía API (`GET/PUT /bot/config/traversal`). |
| Sistema | Persiste la configuración de probabilidades en BD (tabla `bot_config`, clave `traversal_order_probs`). |

No hay roles de autorización diferenciados.

---

## 3. Alcance

### Dentro del alcance

- Enum `TraversalOrder` con valores `DEFAULT`, `REVERSED`, `SHUFFLE` en `core/utils/traversal.py`.
- Dataclass `TraversalConfig` con las tres probabilidades (p_default, p_reversed, p_shuffle)
  que deben sumar 1.0.
- Función pura `apply_order(items, order)` que devuelve una nueva lista con el orden aplicado.
- Función `choose_order(config)` que elige aleatoriamente el `TraversalOrder` según las
  probabilidades configuradas.
- Función compuesta `ordered(items, config)` = `apply_order(items, choose_order(config))`.
- Lectura de la configuración global desde BD al arrancar el WorldAgent; recarga solo cuando
  el usuario la actualiza vía API.
- Punto de aplicación inmediato: `SendSchedulerGroupUseCase.execute()` en
  `core/use_cases/farm_lists.py` línea 363 — el loop sobre `farm_list_ids`.
- Endpoints HTTP:
  - `GET /bot/config/traversal` — devuelve la configuración actual de probabilidades.
  - `PUT /bot/config/traversal` — actualiza las probabilidades.
- Documentación de los puntos de aplicación futuros (§"Puntos de aplicación").

### Fuera del alcance

- Aleatorización por-tarea (probabilidades distintas para farm lists vs. edificios vs. tropas).
  Ver §13 (trade-offs) para la justificación.
- Semilla aleatoria configurable: se usa el `random` estándar de Python sin semilla fija, que
  es adecuado para anti-detección (no queremos reproducibilidad).
- Puerto propio (`TraversalPort`): el helper es una función pura determinista dado el input.
  No hay IO, no hay side effects, no necesita port. El port sería un over-engineering claro.
- Logs de auditoría del orden elegido en cada iteración: demasiado verbose para uso normal.
  Se puede añadir en modo DEBUG si se necesita.

---

## 4. Reglas de negocio

### RN-TOR01 — Tres estrategias de orden

| Estrategia | Comportamiento |
|---|---|
| `DEFAULT` | La lista se recorre en el orden original recibido. No se crea copia innecesaria (devuelve `list(items)` sin modificar el orden). |
| `REVERSED` | La lista se recorre de atrás hacia adelante. `list(reversed(items))`. |
| `SHUFFLE` | La lista se recorre en un orden aleatorio. `random.sample(items, len(items))`. |

### RN-TOR02 — Distribución de probabilidades equiprobable por defecto

La distribución por defecto es 33.3%/33.3%/33.3% (redondeada para sumar 1.0: exactamente
1/3 cada una). El usuario puede cambiarla a cualquier distribución donde la suma sea 1.0
(con un margen de tolerancia de ±0.01 por errores de punto flotante).

**Justificación de la distribución equiprobable:** si una estrategia tuviera mucho más peso
(p.ej. 80% SHUFFLE), el bot casi siempre haría shuffle, lo que en sí es un patrón
estadístico. La equiprobabilidad maximiza la entropía del patrón de orden observado.

### RN-TOR03 — Configuración global (no por-tarea)

La distribución de probabilidades es única y global para todo el bot (un único `TraversalConfig`
por instancia). No se configura por tipo de tarea.

**Justificación:** configurar probabilidades distintas por tipo de tarea (p.ej. farm lists con
40% SHUFFLE y edificios con 20% REVERSED) añadiría overhead de UX (más campos que el usuario
debe configurar y entender) sin beneficio anti-detección adicional apreciable. La
aleatorización ya rompe el patrón determinista con la configuración global. La diferencia
estadística entre "mismo config global" y "config por tipo" es mínima en la práctica.

### RN-TOR04 — `apply_order` no modifica la lista original

`apply_order(items, order)` siempre devuelve una **nueva lista**. La lista `items` original
nunca se modifica (sin `list.sort()` in-place, sin `random.shuffle()` in-place).
Esto es importante porque en algunos contextos la lista original es un atributo de una
entidad que no debe mutarse.

### RN-TOR05 — Idempotencia y reproducibilidad controlada

`apply_order` no tiene estado interno. Si se necesita reproducibilidad en tests, el caller
puede fijar `random.seed()` antes de llamar a `choose_order()` o `ordered()`. En producción
no se fija semilla.

### RN-TOR06 — El helper opera sobre cualquier tipo de secuencia

`apply_order` acepta cualquier `Sequence[T]` y devuelve `list[T]`. No depende del tipo de
los elementos (farm list IDs, aldea IDs, slot IDs, etc.).

---

## 5. Flujo principal y flujos alternativos

### Flujo principal — envío de farm lists con orden aleatorio (aplicación inmediata)

```
1. SendSchedulerGroupUseCase.execute(scheduler_id) se llama.
2. Obtiene farm_list_ids = scheduler.farm_list_ids (lista en orden original de BD).
3. Llama ordered(farm_list_ids, self._traversal_config) → farm_list_ids_ordered.
4. Itera sobre farm_list_ids_ordered (en lugar de farm_list_ids).
5. Cada farm list se procesa en el nuevo orden.
```

El cambio en el código es mínimo: sustituir `for i, farm_list_id in enumerate(farm_list_ids):`
por `for i, farm_list_id in enumerate(ordered(farm_list_ids, config)):`.

### Flujo alternativo — usuario actualiza la distribución de probabilidades

```
1. Usuario llama PUT /bot/config/traversal {"p_default": 0.2, "p_reversed": 0.3, "p_shuffle": 0.5}.
2. API valida que la suma ≈ 1.0 (±0.01).
3. API persiste en BD (tabla bot_config, clave traversal_order_probs).
4. API devuelve 200 con la configuración guardada.
5. El WorldAgent carga la nueva config en la siguiente iteración (ver §polling/invalidación).
```

### Flujo alternativo — arranque del WorldAgent

```
1. WorldAgent arranca.
2. Lee bot_config(key='traversal_order_probs') de BD.
3. Si no existe → usa TraversalConfig() con defaults (33/33/33).
4. Almacena self._traversal_config.
5. Pasa self._traversal_config a SendSchedulerGroupUseCase al construirlo (o lo inyecta directamente).
```

---

## 6. Edge cases

| ID | Situación | Tratamiento |
|---|---|---|
| EC-TOR01 | Lista vacía | `apply_order([], order)` devuelve `[]` sin error. |
| EC-TOR02 | Lista de 1 elemento | `apply_order([x], order)` devuelve `[x]` para cualquier orden. Correcto. |
| EC-TOR03 | Probabilidades que suman exactamente 0.0 (error grave) | `choose_order()` lanza `ValueError`. Nunca debería ocurrir si la escritura en BD validó correctamente. |
| EC-TOR04 | Probabilidades que suman 1.0 ± 0.01 (float imprecision) | Se acepta. `choose_order()` normaliza internamente si la suma no es exactamente 1.0. |
| EC-TOR05 | Una probabilidad es 0.0 (p.ej. p_reversed=0.0) | Válido. `choose_order()` nunca elige REVERSED en ese caso. No hay restricción de probabilidad mínima por estrategia. |
| EC-TOR06 | Una probabilidad es 1.0 y las demás son 0.0 (orden siempre fijo) | Válido aunque no recomendable. El sistema lo acepta. La anti-detección se reduce. |
| EC-TOR07 | `bot_config` no existe en BD al arrancar | Se usan los defaults (33/33/33). Sin error. Sin escritura en BD (no se escribe el default; solo se escribe cuando el usuario lo cambia explícitamente). |
| EC-TOR08 | BD corrompida devuelve un JSON inválido para traversal_order_probs | Se loguea el error, se usan los defaults. El bot no se detiene. |

---

## 7. Modelo de datos / cambios de esquema

### 7.1 Enum `TraversalOrder` (core/utils/traversal.py — archivo nuevo)

```python
from enum import Enum

class TraversalOrder(str, Enum):
    DEFAULT  = "DEFAULT"
    REVERSED = "REVERSED"
    SHUFFLE  = "SHUFFLE"
```

### 7.2 Dataclass `TraversalConfig` (core/utils/traversal.py)

```python
from dataclasses import dataclass, field

@dataclass
class TraversalConfig:
    p_default:  float = 1/3
    p_reversed: float = 1/3
    p_shuffle:  float = 1/3

    def __post_init__(self) -> None:
        total = self.p_default + self.p_reversed + self.p_shuffle
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Las probabilidades deben sumar 1.0 (±0.01). "
                f"Suma actual: {total:.4f}"
            )
        if any(p < 0 for p in (self.p_default, self.p_reversed, self.p_shuffle)):
            raise ValueError("Las probabilidades no pueden ser negativas.")
```

### 7.3 Funciones del helper (core/utils/traversal.py)

```python
import random
from typing import Sequence, TypeVar

T = TypeVar("T")

_DEFAULT_CONFIG = TraversalConfig()


def apply_order(items: Sequence[T], order: TraversalOrder) -> list[T]:
    """
    Devuelve una nueva lista con los elementos de 'items' en el orden indicado.
    No modifica la lista original.

    DEFAULT  → mismo orden
    REVERSED → orden inverso
    SHUFFLE  → permutación aleatoria
    """
    if order == TraversalOrder.DEFAULT:
        return list(items)
    elif order == TraversalOrder.REVERSED:
        return list(reversed(items))
    elif order == TraversalOrder.SHUFFLE:
        return random.sample(list(items), len(items))
    else:
        raise ValueError(f"TraversalOrder desconocido: {order!r}")


def choose_order(config: TraversalConfig = _DEFAULT_CONFIG) -> TraversalOrder:
    """
    Elige aleatoriamente un TraversalOrder según las probabilidades de config.
    Usa random.choices para la distribución de pesos.
    """
    choices = [TraversalOrder.DEFAULT, TraversalOrder.REVERSED, TraversalOrder.SHUFFLE]
    weights = [config.p_default, config.p_reversed, config.p_shuffle]
    return random.choices(choices, weights=weights, k=1)[0]


def ordered(
    items: Sequence[T],
    config: TraversalConfig = _DEFAULT_CONFIG,
) -> list[T]:
    """
    Función de conveniencia: elige el orden aleatoriamente y aplica.
    Equivalente a apply_order(items, choose_order(config)).

    Ejemplo de uso:
        for farm_list_id in ordered(farm_list_ids, self._traversal_config):
            ...
    """
    return apply_order(items, choose_order(config))
```

### 7.4 Persistencia en BD — tabla `bot_config`

Se reutiliza una tabla genérica de configuración del bot (clave-valor). Si no existe, se crea.
No se crea una tabla propia para `traversal_order_probs`.

**Decisión:** en lugar de una tabla dedicada `bot_traversal_config` con columnas individuales,
se usa el patrón clave-valor (`bot_config`) que es estándar para configuraciones globales del
bot. Esto evita crear una tabla nueva para cada ajuste global futuro.

```sql
CREATE TABLE IF NOT EXISTS bot_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL    -- JSON serializado
);
```

La clave `traversal_order_probs` almacena:

```json
{"p_default": 0.333, "p_reversed": 0.333, "p_shuffle": 0.334}
```

### 7.5 Puerto `BotConfigDbPort` (core/ports/bot_config_db_port.py)

Puerto genérico para la tabla `bot_config`. Reutilizable para otras configuraciones globales
futuras del bot.

```python
from abc import ABC, abstractmethod
from typing import Any

class BotConfigDbPort(ABC):

    @abstractmethod
    async def get_config(self, key: str) -> Any | None:
        """Devuelve el valor deserializado de la clave, o None si no existe."""

    @abstractmethod
    async def set_config(self, key: str, value: Any) -> None:
        """Persiste el valor serializado como JSON para la clave."""
```

---

## 8. Contratos de API / interfaces

La feature expone dos endpoints. Contratos validados por `desarrollador-apis` el 2026-05-30.

### 8.1 `GET /bot/config/traversal` — Configuración actual de orden de recorrido

Devuelve la distribución de probabilidades actualmente configurada para el orden de
iteración. No requiere `Accept-Language` (devuelve floats de configuración).

```
GET /bot/config/traversal
Content-Type: application/json

Response 200:
{
  "p_default":  0.333,    // probabilidad de usar el orden original (DEFAULT)
  "p_reversed": 0.333,    // probabilidad de usar el orden inverso (REVERSED)
  "p_shuffle":  0.334,    // probabilidad de usar orden aleatorio (SHUFFLE)
  "is_default": true      // true si el usuario nunca modificó la config (usa defaults 1/3 cada una)
}

Response 500: { "detail": "Error interno del servidor." }
```

**Nota:** no hay `404` para este endpoint — la config siempre existe (usa defaults si el
usuario nunca la configuró). `is_default: true` comunica ese estado al cliente.

### 8.2 `PUT /bot/config/traversal` — Actualizar distribución de probabilidades

Reemplaza la distribución de probabilidades de orden de iteración. Operación idempotente:
el mismo body dos veces produce el mismo estado. No requiere `Accept-Language`.

```
PUT /bot/config/traversal
Content-Type: application/json

Request body:
{
  "p_default":  0.2,    // obligatorio; float >= 0.0
  "p_reversed": 0.3,    // obligatorio; float >= 0.0
  "p_shuffle":  0.5     // obligatorio; float >= 0.0
}
// Restricción: p_default + p_reversed + p_shuffle debe estar en [0.99, 1.01]

Response 200:
{
  "p_default":  0.2,
  "p_reversed": 0.3,
  "p_shuffle":  0.5,
  "is_default": false
}

Response 422: { "detail": "Las probabilidades deben sumar 1.0 (±0.01). Suma actual: 1.15." }
             // Se produce cuando TraversalConfig.__post_init__ lanza ValueError;
             // el handler lo convierte en HTTPException(422).
Response 422: { "detail": "Las probabilidades no pueden ser negativas." }
             // FastAPI genera 422 automáticamente para valores de tipo inválido en el body.
Response 500: { "detail": "Error interno del servidor." }
```

**Nota sobre el código 422 para validaciones semánticas:** los errores de validación del
body (tipos incorrectos, campos ausentes) los genera FastAPI automáticamente como `422`.
Las validaciones semánticas (suma != 1.0, negativos) deben convertirse desde `ValueError`
a `HTTPException(status_code=422)` en el handler o en un exception handler registrado;
no como `400`, que se reserva para JSON malformado (que FastAPI también maneja solo).

**Nota sobre el prefijo `/bot/config/`:** los endpoints de configuración global del bot no van
bajo `/worlds/{id}/` porque son globales a la instancia del bot, no por mundo. El mismo helper
`ordered()` usa la misma config en todos los mundos.

---

## 9. Flujo lógico paso a paso (pseudocódigo / mermaid)

### 9.1 Diagrama de flujo de `ordered()`

```mermaid
flowchart LR
    A[items: Sequence[T]] --> B{choose_order(config)}
    B -- "DEFAULT (p1)" --> C[list(items)]
    B -- "REVERSED (p2)" --> D[list(reversed(items))]
    B -- "SHUFFLE (p3)" --> E[random.sample(items)]
    C --> F[list[T] ordenada]
    D --> F
    E --> F
```

### 9.2 Integración en `SendSchedulerGroupUseCase.execute()`

Cambio mínimo en `core/use_cases/farm_lists.py`:

```python
# ANTES (línea 363):
for i, farm_list_id in enumerate(farm_list_ids):

# DESPUÉS:
from core.utils.traversal import ordered

for i, farm_list_id in enumerate(ordered(farm_list_ids, self._traversal_config)):
```

El dataclass `SendSchedulerGroupUseCase` recibe `traversal_config: TraversalConfig` como
parámetro adicional (con default `TraversalConfig()` para no romper constructores existentes):

```python
@dataclass
class SendSchedulerGroupUseCase:
    browser: FarmListBrowserPort
    db: FarmListDbPort
    traversal_config: TraversalConfig = field(default_factory=TraversalConfig)
```

El WorldAgent pasa `self._traversal_config` al construir `SendSchedulerGroupUseCase`.

### 9.3 Carga y recarga de la configuración en WorldAgent

```python
async def _load_traversal_config(self) -> TraversalConfig:
    """
    Carga la configuración de traversal desde BD.
    Si no existe o está corrompida, usa defaults.
    """
    try:
        raw = await self._bot_config_db.get_config("traversal_order_probs")
        if raw is None:
            return TraversalConfig()
        return TraversalConfig(
            p_default=raw["p_default"],
            p_reversed=raw["p_reversed"],
            p_shuffle=raw["p_shuffle"],
        )
    except Exception as exc:
        log.warning("Error cargando traversal_config, usando defaults: %s", exc)
        return TraversalConfig()
```

**Recarga:** la configuración se carga al arrancar. Para que el usuario pueda cambiarla sin
reiniciar, el WorldAgent puede recargarla periódicamente (p.ej. una vez por ciclo completo
de N iteraciones) o el endpoint PUT puede señalizar la necesidad de recarga vía BD (similar
al mecanismo de `mode_override` de human-sessions). En v1 se recarga al arrancar; la recarga
en caliente queda como mejora futura.

---

## 10. Validaciones y reglas

| Regla | Dónde se valida | Comportamiento en fallo |
|---|---|---|
| Las probabilidades suman 1.0 ±0.01 | `TraversalConfig.__post_init__()` + endpoint PUT | `ValueError` → 422 en endpoint |
| Las probabilidades no son negativas | `TraversalConfig.__post_init__()` | `ValueError` → 422 |
| `apply_order` no modifica la lista original | Implementación (usa `list()`, `reversed()`, `random.sample()`) | Invariante de implementación; no requiere validación en runtime |
| `items` vacía | `apply_order` devuelve `[]` | Sin error; comportamiento correcto |
| `TraversalOrder` desconocido en `apply_order` | `raise ValueError(f"TraversalOrder desconocido: {order!r}")` | No debería ocurrir si el enum está completo |

---

## 11. Puntos de aplicación — actuales y futuros

Esta sección documenta dónde se aplica el helper hoy y dónde se aplicará cuando se
implementen otras features. El desarrollador que implemente una feature futura solo necesita
leer esta sección para saber que debe llamar a `ordered()` antes de iterar.

### 11.1 Puntos de aplicación ACTUALES (v1 de este spec)

| Localización | Colección iterada | Por qué aleatorizar |
|---|---|---|
| `core/use_cases/farm_lists.py:363` (`SendSchedulerGroupUseCase.execute`) | `farm_list_ids` del scheduler | Las farm lists se enviaban siempre en el mismo orden; firma detectada en el baneo. |

### 11.2 Puntos de aplicación FUTUROS (cuando se implementen)

Estos puntos de aplicación son identificados ahora para que el implementador de cada feature
sepa que debe usar `ordered()`. No forman parte del alcance de este spec.

| Feature futura | Localización estimada | Colección a aleatorizar |
|---|---|---|
| Entrenamiento de tropas en N aldeas | `core/use_cases/troops_training.py` (a crear) | Lista de `village_ids` donde entrenar |
| Construcción de edificios en N aldeas | `core/use_cases/buildings.py` (a crear) | Lista de `village_ids` donde construir |
| Raids puntuales a N aldeas | `core/use_cases/raids.py` (a crear) | Lista de `target_village_ids` |
| Sondeo de N slots en una farm list | `core/use_cases/farm_lists.py` (futuro) | Lista de `slot_ids` dentro de una farm list |
| Seed de oasis groups al arrancar | `core/scheduling/world_agent.py:seed_oasis_groups_from_db()` | Lista de `groups` en el wake-up |
| Iteración de N farm schedulers en seed | `core/scheduling/world_agent.py:seed_from_schedulers()` | Lista de `schedulers` |

**Regla para implementadores de features futuras:** cada vez que iteres sobre una colección
de N elementos donde N > 1 y el orden es arbitrario (no hay dependencia de orden entre
elementos), usa `ordered(items, self._traversal_config)` en lugar de iterar directamente.

---

## 12. Seguridad, rendimiento y concurrencia

### Rendimiento

- `apply_order` es O(N) para DEFAULT y REVERSED, O(N) para SHUFFLE (`random.sample`
  implementa Fisher-Yates en CPython). Para colecciones de tamaño típico (2-20 farm lists),
  el coste es negligible.
- `choose_order` es O(1): `random.choices` con 3 opciones.
- No hay IO, no hay asyncio, no hay locks: el helper es completamente síncrono y seguro
  para uso en contextos async (no bloquea el event loop).

### Concurrencia

- `TraversalConfig` es un dataclass inmutable en la práctica (no debería mutarse en runtime).
  La actualización vía API crea un nuevo `TraversalConfig` y lo asigna al WorldAgent.
- `apply_order` no tiene estado compartido. Puede llamarse concurrentemente sin riesgo
  (aunque en este proyecto el WorldAgent es single-threaded asyncio).

### Anti-detección

- **La aleatoriedad de `random.sample`** es criptográficamente no-segura pero estadísticamente
  adecuada para anti-detección. No se necesita `secrets` (que es para criptografía); basta
  con `random` estándar.
- **No fijar semilla** en producción: fijar la semilla produciría la misma secuencia de órdenes
  en cada ejecución, lo cual sería tan detectable como el orden fijo original.
- **La distribución equiprobable** maximiza la entropía del patrón de orden observado por
  Travian. Si una estrategia dominara (p.ej. 90% SHUFFLE), el patrón de "siempre desordenado"
  sería estadísticamente tan inusual como "siempre ordenado".

---

## 13. Plan de pruebas

### Pruebas unitarias (core, sin IO)

| ID | Caso | Entrada | Esperado |
|---|---|---|---|
| UT-TOR01 | `apply_order` DEFAULT conserva el orden | [3, 1, 2], DEFAULT | [3, 1, 2] |
| UT-TOR02 | `apply_order` REVERSED invierte | [3, 1, 2], REVERSED | [2, 1, 3] |
| UT-TOR03 | `apply_order` SHUFFLE es permutación | [1, 2, 3, 4, 5], SHUFFLE | mismos elementos, posiblemente diferente orden |
| UT-TOR04 | `apply_order` no modifica la lista original | original=[1,2,3], apply(original, SHUFFLE) | original sigue siendo [1,2,3] |
| UT-TOR05 | `apply_order` lista vacía | [], cualquier orden | [] |
| UT-TOR06 | `apply_order` lista de 1 elemento | [42], cualquier orden | [42] |
| UT-TOR07 | `choose_order` respeta las probabilidades (estadístico) | config con p_default=1.0 | siempre devuelve DEFAULT |
| UT-TOR08 | `choose_order` con p_shuffe=1.0 | config con p_shuffle=1.0 | siempre devuelve SHUFFLE |
| UT-TOR09 | `TraversalConfig` suma > 1.01 → ValueError | p_d=0.5, p_r=0.5, p_s=0.5 | ValueError |
| UT-TOR10 | `TraversalConfig` suma < 0.99 → ValueError | p_d=0.1, p_r=0.1, p_s=0.1 | ValueError |
| UT-TOR11 | `TraversalConfig` suma 1.0 ± 0.01 → OK | p_d=0.334, p_r=0.333, p_s=0.333 | sin error |
| UT-TOR12 | `TraversalConfig` con probabilidad negativa → ValueError | p_d=-0.1 | ValueError |
| UT-TOR13 | `ordered()` equivale a apply_order(choose_order()) | semilla fija, config cualquiera | resultado idéntico |
| UT-TOR14 | `apply_order` SHUFFLE: con N=5, 100 llamadas producen al menos 2 órdenes distintos | list(range(5)), SHUFFLE × 100 | al menos 2 resultados distintos (probabilidad de todos iguales ≈ 0) |

### Pruebas de integración (con use cases reales)

| ID | Caso | Descripción |
|---|---|---|
| IT-TOR01 | `SendSchedulerGroupUseCase` con mock de BD y browser: orden aleatorio aplicado | Configurar scheduler con 3 farm lists. Ejecutar 10 veces. Verificar que al menos dos ejecuciones producen órdenes distintos. |
| IT-TOR02 | `PUT /bot/config/traversal` con suma != 1.0 → 422 | Llamar endpoint con valores inválidos. Verificar respuesta 422. |
| IT-TOR03 | `PUT /bot/config/traversal` válido → `GET` devuelve el mismo valor | Round-trip de configuración. |
| IT-TOR04 | EC-TOR07: `bot_config` sin clave traversal → defaults | Sin fila en BD, leer config → TraversalConfig() defaults. |
| IT-TOR05 | EC-TOR08: JSON corrompido en BD → defaults | Insertar JSON inválido en bot_config, leer config → defaults sin error fatal. |

---

## 14. Riesgos y trade-offs

### Decisión: helper puro (no port)

**Justificación:** `apply_order()` y `choose_order()` no tienen IO, no tienen estado externo,
no necesitan ser intercambiados en tests (el resultado es observable directamente).
Introducir un `TraversalPort` con `apply_order()` como método abstracto sería
over-engineering: los ports existen para desacoplar el core del IO (browser, BD, red).
Un helper matemático no necesita ese desacoplamiento.

**Trade-off aceptado:** si en el futuro se necesita un mecanismo de logging centralizado de
cada orden elegido, habrá que tocar la función directamente. Pero ese caso de uso es poco
probable y se puede resolver con un wrapper o un decorator sin introducir un port.

### Decisión: configuración global (no por-tarea)

**Justificación:** el overhead de UX de configurar probabilidades por tipo de tarea
(farm lists, tropas, edificios, raids) es alto: el usuario tendría que entender qué hace
cada tipo de tarea y ajustar N conjuntos de probabilidades. El beneficio anti-detección de
la configuración por-tarea es marginal: si el orden ya es aleatorio globalmente, distinguir
entre "shuffle en farm lists 40% vs. 33%" no añade varianza significativa desde la
perspectiva de Travian.

**Trade-off aceptado:** si en el futuro se detecta que un tipo de tarea específico necesita
una distribución diferente (p.ej. raids de alta frecuencia necesitan más SHUFFLE que
actividades de baja frecuencia), se puede extender el modelo añadiendo config por tipo.
La interfaz de `ordered(items, config)` ya lo soporta: basta con pasar un config diferente.

### Decisión: `random.sample` en vez de `random.shuffle` in-place

**Justificación:** `random.shuffle` modifica la lista in-place, violando RN-TOR04. El uso de
`random.sample(items, len(items))` produce una nueva lista sin modificar la original. El coste
es idéntico (O(N), mismo algoritmo Fisher-Yates en CPython).

### Decisión: tabla genérica `bot_config` en vez de tabla dedicada

**Justificación:** crear una tabla `bot_traversal_config` con 3 columnas de tipo REAL sería
correcto pero genera deuda de mantenimiento: cada nueva configuración global del bot
requeriría una nueva tabla. El patrón clave-valor con serialización JSON es estándar para
configuraciones globales de baja frecuencia de acceso (se lee al arrancar, se escribe cuando
el usuario lo cambia). El trade-off es que no hay tipos en BD (todo es TEXT), pero la
deserialización y validación en `TraversalConfig.__post_init__` compensa.

### Riesgo R-TOR01 — SHUFFLE en listas de 2 elementos solo tiene 2 posibles órdenes

Con 2 farm lists, SHUFFLE elige entre 2 permutaciones. La entropía es mínima (1 bit).
En ese caso, DEFAULT y REVERSED ya cubren las 2 opciones; SHUFFLE no añade nada nuevo.

**Mitigación:** no es un problema real. Con 2 elementos, cualquier orden es ya una variación
suficiente. El caso degenerado de 1 elemento produce siempre el mismo resultado, que es
correcto (no hay alternativa).

---

## 15. Pasos de implementación ordenados

### Paso 1 — Helper puro `core/utils/traversal.py` (archivo nuevo)

- Crear `TraversalOrder` (enum).
- Crear `TraversalConfig` (dataclass con validación en `__post_init__`).
- Crear `apply_order()`, `choose_order()`, `ordered()`.
- Tests: UT-TOR01 a UT-TOR14.

### Paso 2 — Puerto genérico `BotConfigDbPort` (core/ports/bot_config_db_port.py)

- ABC con `get_config()` y `set_config()`.
- Sin implementar aún.

### Paso 3 — Tabla `bot_config` y adaptador (adapters/db/)

- DDL de `bot_config` (§7.4).
- Implementar `BotConfigSQLiteAdapter`: `get_config()` deserializa JSON, `set_config()`
  serializa JSON + INSERT OR REPLACE.
- Tests: IT-TOR04, IT-TOR05.

### Paso 4 — Integración en `SendSchedulerGroupUseCase`

- Añadir `traversal_config: TraversalConfig` al dataclass con default `TraversalConfig()`.
- Sustituir el loop de la línea 363 por `enumerate(ordered(farm_list_ids, self.traversal_config))`.
- Tests: IT-TOR01.

### Paso 5 — Carga de config en WorldAgent

- Añadir `self._bot_config_db: BotConfigDbPort` al WorldAgent.
- Implementar `_load_traversal_config()` (§9.3).
- Pasar el config cargado a `SendSchedulerGroupUseCase` al construirlo.

### Paso 6 — Endpoints HTTP (adapters/api/routes/bot_config.py — archivo nuevo o sección en existing)

- `GET /bot/config/traversal`
- `PUT /bot/config/traversal`
- Registrar el router en `adapters/api/main.py`.
- Delegar la validación de contratos al agente `desarrollador-apis` antes de commitear.
- Tests: IT-TOR02, IT-TOR03.

### Paso 7 — Verificación end-to-end

- Todos los tests UT-TOR01…UT-TOR14 y IT-TOR01…IT-TOR05 pasan.
- Los tests existentes de farm lists pasan al 100%.

---

## 16. Criterios de aceptación

Checklist verificable por el implementador sin preguntas abiertas:

- [ ] CA-TOR01: `TraversalOrder` enum existe en `core/utils/traversal.py` con valores `DEFAULT`, `REVERSED`, `SHUFFLE`.
- [ ] CA-TOR02: `TraversalConfig` dataclass existe con campos `p_default`, `p_reversed`, `p_shuffle` (float). Valida en `__post_init__` que la suma ∈ [0.99, 1.01] y que ningún valor es negativo.
- [ ] CA-TOR03: `TraversalConfig()` (sin argumentos) produce p=1/3 para cada estrategia.
- [ ] CA-TOR04: `apply_order(items, DEFAULT)` devuelve una lista con los mismos elementos en el mismo orden.
- [ ] CA-TOR05: `apply_order(items, REVERSED)` devuelve una lista con los elementos en orden inverso.
- [ ] CA-TOR06: `apply_order(items, SHUFFLE)` devuelve una lista con los mismos elementos pero en orden potencialmente distinto; la lista original no se modifica.
- [ ] CA-TOR07: `apply_order([], cualquier_orden)` devuelve `[]` sin error.
- [ ] CA-TOR08: `choose_order(TraversalConfig(p_default=1.0, p_reversed=0.0, p_shuffle=0.0))` siempre devuelve `DEFAULT` (100 iteraciones).
- [ ] CA-TOR09: `ordered(items, config)` devuelve el mismo resultado que `apply_order(items, choose_order(config))` con la misma semilla aleatoria.
- [ ] CA-TOR10: `SendSchedulerGroupUseCase` tiene campo `traversal_config: TraversalConfig` (con default que no rompe constructores existentes).
- [ ] CA-TOR11: El loop en `SendSchedulerGroupUseCase.execute()` itera sobre `ordered(farm_list_ids, self.traversal_config)` en lugar de `farm_list_ids` directamente.
- [ ] CA-TOR12: El WorldAgent carga `TraversalConfig` desde BD al arrancar; si no existe usa defaults sin error.
- [ ] CA-TOR13: `GET /bot/config/traversal` devuelve `{"p_default": ..., "p_reversed": ..., "p_shuffle": ..., "is_default": bool}`.
- [ ] CA-TOR14: `PUT /bot/config/traversal` con suma != 1.0 devuelve 422.
- [ ] CA-TOR15: `PUT /bot/config/traversal` con valores válidos devuelve 200 y persiste en BD.
- [ ] CA-TOR16: Todos los tests UT-TOR01…UT-TOR14 pasan.
- [ ] CA-TOR17: Todos los tests IT-TOR01…IT-TOR05 pasan.
- [ ] CA-TOR18: Los tests existentes de farm lists pasan al 100% tras esta implementación.

---

## 17. Trazabilidad

| Decisión técnica | Requisito / Edge case que la origina |
|---|---|
| Helper puro, no port | §3 (fuera del alcance): el helper no tiene IO. Un port sería over-engineering. Ver §14 trade-off. |
| Tres estrategias: DEFAULT/REVERSED/SHUFFLE | Requisito del usuario: variar entre "mismo orden", "invertido" y "aleatorio". |
| Distribución 33/33/33 por defecto | RN-TOR02: la distribución equiprobable maximiza la entropía del patrón de orden observado. |
| Configuración global, no por-tarea | RN-TOR03: overhead de UX sin beneficio anti-detección adicional apreciable. Ver §14 trade-off. |
| `random.sample` en vez de `random.shuffle` in-place | RN-TOR04: `apply_order` no modifica la lista original. |
| Tabla genérica `bot_config` | §7.4: evita deuda de mantenimiento de tablas por cada ajuste global. |
| Punto de aplicación inmediato: `farm_lists.py:363` | Palantir identificó esta línea como la única iteración determinista a tocar hoy. |
| Puntos de aplicación futuros documentados en §11.2 | Los implementadores de features futuras necesitan saber que deben usar `ordered()`. Documentarlo en el spec es la única forma de que "otro agente en frío" lo sepa. |
| Recarga de config al arrancar (no en caliente en v1) | Simplicidad: el mecanismo de invalidación de caché en caliente es un over-engineering para v1. La recarga al reiniciar es suficiente para una configuración que el usuario cambia raramente. |
