---
id: optimizador-balance-multiraid
titulo: Optimizador — peso balance + modo multi-raid (Modo C)
estado: implemented
fecha: 2026-05-29
autor: analista
feature_branch: feature/optimizador-balance-multiraid
apis_validadas_por_desarrollador_apis: true
---

# Optimizador — peso balance + modo multi-raid (Modo C)

## 1. Resumen funcional

Extiende el optimizador existente (`POST /combat/optimize`) con tres calculadoras diferenciadas que el usuario distingue mediante un toggle en la UI:

- **Modo A** (ya existe): entrada = tipos de tropas sin cantidad. Optimiza qué combinación de tipos enviar.
- **Modo B** (ya existe): entrada = inventario de tropas. Optimiza cómo golpear una aldea única perdiendo menos tropas y recursos.
- **Modo C** (nuevo): misma entrada que B, pero con preset de pesos que acentúa balance y minimización de pérdidas, y muestra columnas adicionales: cuántas veces puedes repetir esa oleada con tu inventario, sobrantes de tropas y agregado total de N raids.

No se crea ningún endpoint nuevo. No se crea ningún use case nuevo. Los cambios son: (1) un campo `balance` en pesos, (2) tres campos opcionales en el response, (3) una entidad pequeña `MultiRaidAggregate`, (4) lógica de decoración de alternativas, (5) toggle y render condicional en el frontend.

---

## 2. Reglas de negocio

**RN-01** — `balance_score` solo es efectivo en Modo B/C (cuando hay `village_troops` con `quantity_available` definido). En Modo A (`troop_types`), `balance_score = 0` para toda alternativa — el peso `balance` es ineficaz pero no produce error.

**RN-02** — Los campos `raids_possible`, `remaining_troops` y `aggregate` son `null` en Modo A (sin inventario). En Modo B también se calculan y devuelven, aunque el frontend solo los renderiza en Modo C.

**RN-03** — `OptimizationWeights.balance = 0.0` es el default. Llamadas existentes sin ese campo producen exactamente el mismo resultado que antes.

**RN-04 — `scoring_mode` controla si los pesos se aplican por-raid o al agregado de N raids** (añadido 2026-05-29 tras prueba manual del usuario):

- `scoring_mode = "single"` (default): el score es el actual — cada término del peso se aplica al valor por-raid de la oleada.
- `scoring_mode = "aggregate"`: cuando hay `village_troops`, los términos `resources_gained`, `total_losses`, `troops_sent` y `travel_time` se multiplican por `N_efectivo` antes de ponderar. El término `balance` NO se multiplica (sigue siendo estructural por-oleada).
- Modo B (frontend) envía `single`. Modo C envía `aggregate`. Modo A (sin inventario) ignora el campo (N=1 efectivo).

Motivación: sin esto, el optimizador prefiere oleadas grandes con menos N porque el "loot por raid" gana al "loot total × N". El usuario quiere lo contrario en Modo C: oleadas pequeñas replicables muchas veces dan más beneficio agregado aunque pierdas más en absoluto.

**RN-05 — `n_min` y `n_max` acotan el N efectivo en Modo C** (añadido 2026-05-29):

Ambos opcionales. Combinaciones soportadas:
- `(null, null)`: optimizador decide N libremente (= "cuántas vacas puedo atracar").
- `(X, null)`: al menos X raids.
- `(null, X)`: como mucho X raids.
- `(X, X)`: exactamente X raids (= "quiero atracar N vacas concretas").
- `(A, B)` con `A ≤ B`: entre A y B raids.

Cálculo:
- `N_natural = floor(min_i(available_i / sent_i))` para tipos con `sent_i > 0`.
- `N_efectivo = clamp(N_natural, n_min or 1, n_max or +inf)`.
- Si `N_natural < n_min`: la alternativa se penaliza con `+inf` en el score (queda al fondo del ranking pero se devuelve para transparencia). Las decoraciones `raids_possible/remaining/aggregate` usan `N_natural` para que el usuario vea el dato real.
- Si `N_natural > n_max`: se cappea a `n_max` en el score y en las decoraciones. Las tropas no consumidas (`available_i − n_max × sent_i`) aparecen en `remaining_troops`.

Si `n_min > n_max`: validación Pydantic → 422.

Solo `scoring_mode = "aggregate"` consume `n_min / n_max`. En `single` se ignoran (sin error).

---

## 3. Cambios backend

### 3.1 `core/entities/combat.py`

**Modificar `OptimizationWeights`** — añadir campo:

```python
@dataclass
class OptimizationWeights:
    resources_gained: float = 1.0
    total_losses: float = 1.0
    troops_sent: float = 0.5
    travel_time: float = 0.0
    balance: float = 0.0          # NUEVO — 0.0 = sin efecto (default retrocompatible)
```

**Nueva entidad `MultiRaidAggregate`** — añadir tras `OptimizationAlternative`:

```python
@dataclass
class MultiRaidAggregate:
    """Totales acumulados de N raids idénticas."""
    n_raids: int
    total_resources_gained: AnimalResourceDrop   # N × resources_gained de la oleada
    total_resource_losses: int                   # N × total_resource_losses del atacante
    total_troops_sent: int                       # N × troops_sent_count
    total_travel_time_h: float | None            # N × travel_time_h; None si sin distancia
```

**Modificar `OptimizationAlternative`** — añadir 3 campos opcionales al final:

```python
@dataclass
class OptimizationAlternative:
    # ... campos existentes sin cambio ...
    raids_possible: int | None = None              # NUEVO — None si sin inventario
    remaining_troops: list[TroopResult] | None = None  # NUEVO — None si sin inventario
    aggregate: MultiRaidAggregate | None = None    # NUEVO — None si sin inventario
```

### 3.2 `adapters/api/routes/combat.py`

**Modificar `OptimizationWeightsRequest`** — añadir campo:

```python
class OptimizationWeightsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resources_gained: float = Field(default=1.0, ge=0.0)
    total_losses: float = Field(default=1.0, ge=0.0)
    troops_sent: float = Field(default=0.5, ge=0.0)
    travel_time: float = Field(default=0.0, ge=0.0)
    balance: float = Field(default=0.0, ge=0.0)   # NUEVO
```

**Nueva clase `MultiRaidAggregateResponse`**:

```python
class MultiRaidAggregateResponse(BaseModel):
    n_raids: int
    total_resources_gained: AnimalResourceDropResponse
    total_resource_losses: int
    total_troops_sent: int
    total_travel_time_h: float | None
```

**Modificar `OptimizationAlternativeResponse`** — añadir 3 campos opcionales al final:

```python
class OptimizationAlternativeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # ... campos existentes sin cambio ...
    raids_possible: int | None = None
    remaining_troops: list[TroopResultResponse] | None = None
    aggregate: MultiRaidAggregateResponse | None = None
```

### 3.3 `core/use_cases/combat_optimizer.py`

#### Función `balance_score(ev, available_map)`

```python
def _balance_score(ev: dict, available_map: dict[tuple, int]) -> float:
    """
    Mide la uniformidad relativa del uso del inventario.
    Menor stdev = más balanceado = score más bajo (favorece esta alternativa).

    available_map: {(tribe, ordinal): quantity_available}
    ev["troops_sent"]: lista de {tribe, ordinal, quantity_sent, ...}

    Retorna 0.0 si hay 0 o 1 tipo activo (sin stdev), o si available_map vacío.
    """
    import statistics
    ratios = []
    for t in ev.get("troops_sent", []):
        key = (t["tribe"], t["ordinal"])
        avail = available_map.get(key, 0)
        sent = t.get("quantity_sent", 0)
        if sent > 0 and avail > 0:
            ratios.append(sent / avail)
    if len(ratios) <= 1:
        return 0.0
    return statistics.stdev(ratios)
```

#### Modificar `_score()` dentro de `find_optimal_attack`

```python
# Construir available_map una vez antes de _score (solo en Modo B)
available_map: dict = {}
if village_troops:
    for tv in village_troops:
        available_map[(tv.tribe, tv.ordinal)] = tv.quantity_available

w_balance = w.balance  # nuevo peso

def _score(e: dict) -> float:
    bs = _balance_score(e, available_map) if available_map else 0.0
    return (
        w_res * e.get("neg_resources", 0)
        + w_loss * e.get("total_resource_losses", 0)
        + w_troops * e.get("troops_sent_count", 0)
        + w_time * e.get("travel_time_h", 0)
        + w_balance * bs          # NUEVO término
    )
```

#### Decorar alternativas con campos multi-raid (al construir `OptimizationAlternative`)

Si `village_troops is not None` — **para TODAS las alternativas, ganen o pierdan** (decisión del usuario 2026-05-29 frente a la opción "solo ganadoras"):

```python
# raids_possible = min_i floor(available_i / sent_i) para tipos con sent_i > 0
# Representa "cuántas veces podrías mandar esta oleada antes de quedarte sin tropas",
# sea ganadora o suicida.
n = min(avail_map[key] // t.quantity_initial
        for t in result.attacker_troops if t.quantity_initial > 0)
raids_possible = n

# remaining_troops: reutilizar TroopResult; quantity_survived = available_i - n × sent_i (clamp 0)
# aggregate: n × cada campo de resources_gained + total_resource_losses + troops_sent_count + travel_time_h
# Para alternativas perdedoras en modo raid, resources_gained_from_animals = 0 (no loot del
# perdedor), así que aggregate.total_resources_gained.total será 0 — coherente.
```

Solo si `village_troops is None` (Modo A — entrada por tipos): `raids_possible=None`,
`remaining_troops=None`, `aggregate=None`. El concepto de inventario no aplica.

---

## 4. Contratos de API

Sin endpoint nuevo. Única modificación al contrato de `POST /combat/optimize`:

**Request** — `optimization_weights` acepta `balance` adicional (opcional, default 0.0, `ge=0.0`).

**Response** — cada objeto en `alternatives` puede incluir opcionalmente:

```json
{
  "raids_possible": 12,
  "remaining_troops": [
    { "tribe": "romans", "ordinal": 1, "name": "Legionnaire",
      "icon_url": "/static/icons/3.png",
      "quantity_initial": 1000, "quantity_survived": 880, "quantity_lost": 120 }
  ],
  "aggregate": {
    "n_raids": 12,
    "total_resources_gained": { "wood": 600, "clay": 0, "iron": 0, "crop": 0, "total": 600 },
    "total_resource_losses": 24000,
    "total_troops_sent": 120,
    "total_travel_time_h": 48.0
  }
}
```

Todos los campos nuevos tienen `null` como valor válido — retrocompatibilidad garantizada.

---

## 5. Cambios frontend

### 5.1 `OptimizerPanel.jsx` — toggle 3 modos

```jsx
// Cambiar: inputMode: 'A' | 'B'  →  inputMode: 'A' | 'B' | 'C'
const MODES = [
  { id: 'A', labelKey: 'calc.optimizer.mode.tabA' },
  { id: 'B', labelKey: 'calc.optimizer.mode.tabB' },
  { id: 'C', labelKey: 'calc.optimizer.mode.tabC' },  // NUEVO
];
```

Modo C reutiliza el formulario de Modo B íntegro (inventario + smithy + defensa oasis). Al entrar al Modo C, aplicar preset de pesos:

```js
const MODE_C_PRESET = {
  resources_gained: 1.0,
  total_losses: 1.5,
  troops_sent: 0.5,
  travel_time: 0.0,
  balance: 1.5,
};
```

El slider `balance` se muestra únicamente cuando `inputMode === 'C'`. En Modos A y B se oculta (evita ruido; el backend lo acepta igualmente pero con default 0.0 es ineficaz).

Añadir hint bajo el toggle cuando `inputMode === 'C'`: clave `calc.optimizer.modeCHint`.

### 5.2 `OptimizerResult.jsx` — render condicional multi-raid

Solo cuando `inputMode === 'C'` y la alternativa trae `raids_possible !== null`, renderizar debajo del bloque de cada alternativa:

1. **Línea destacada**: "Puedes hacer esto **N veces**" — clave `calc.optimizer.multiRaid.raidsPossible`.
2. **Tabla sobrantes**: columnas icono / nombre / sobrantes / % del inventario — clave `calc.optimizer.multiRaid.remaining`.
3. **Cuadro agregado**: iconos de recursos con totales, bajas totales en recursos, tropas enviadas, tiempo total si no es null — clave `calc.optimizer.multiRaid.aggregate`.

### 5.3 Claves i18n (`es.js` y `en.js`)

| Clave | ES | EN |
|---|---|---|
| `calc.optimizer.mode.tabC` | "Multi-raid" | "Multi-raid" |
| `calc.optimizer.modeCHint` | "Optimiza series de raids paralelas con pérdida aceptable" | "Optimise repeated parallel raids with acceptable losses" |
| `calc.optimizer.weight.balance` | "Balance" | "Balance" |
| `calc.optimizer.weight.balance.hint` | "Penaliza usar un tipo de tropa mucho más que otros" | "Penalises using one troop type far more than others" |
| `calc.optimizer.multiRaid.raidsPossible` | "Puedes hacer esto {n} veces" | "You can do this {n} times" |
| `calc.optimizer.multiRaid.remaining` | "Tropas sobrantes" | "Remaining troops" |
| `calc.optimizer.multiRaid.aggregate` | "Total agregado ({n} raids)" | "Aggregated total ({n} raids)" |

---

## 6. Criterios de aceptación

- [ ] **CA-01** — Con 1000 espadas (A1) y 10 héduos (A2), pesos `balance=1.5`, la alternativa ganadora no usa héduos de forma desproporcionada cuando las espadas son suficientes para superar la defensa.
- [ ] **CA-02** — No-regresión: llamada sin campo `balance` devuelve exactamente el mismo resultado que antes (peso 0.0 neutral).
- [ ] **CA-03** — `raids_possible = min_i floor(available_i / sent_i)` para todos los tipos con `sent_i > 0`.
- [ ] **CA-04** — `aggregate.total_resources_gained.total = raids_possible × oleada.resources_gained.total` (aritmética exacta).
- [ ] **CA-05** — `remaining_troops[i].quantity_survived = available_i - raids_possible × sent_i ≥ 0` para todo tipo.
- [ ] **CA-06** — Si `village_troops` no se envía (Modo A): `raids_possible/remaining_troops/aggregate = null` en todas las alternativas del response.
- [ ] **CA-06b** — Si `village_troops` se envía: `raids_possible/remaining_troops/aggregate` se rellenan en TODAS las alternativas (ganadoras y perdedoras). Para una perdedora en modo raid, `aggregate.total_resources_gained.total = 0` (no hay botín del perdedor) pero `raids_possible` y `aggregate.total_resource_losses` son no-cero.
- [ ] **CA-07** — Un único tipo de tropa con `sent > 0` → `balance_score = 0` (sin penalización).
- [ ] **CA-08** — Mover el slider `balance` de 0 a 1.5 cambia el ranking de alternativas cuando hay 2+ tipos activos con ratios distintos (smoke test manual).
- [ ] **CA-09** — `scoring_mode="aggregate"` con inventario desbalanceado (1000S + 10H): el ranking elegido tiene N estrictamente mayor y `aggregate.total_resources_gained.total` estrictamente mayor que la mejor del mismo input con `scoring_mode="single"` (verifica que el fix soluciona el problema reportado).
- [ ] **CA-10** — `scoring_mode="single"` (default): el ranking es idéntico al actual aunque se envíe `n_min/n_max` (se ignoran).
- [ ] **CA-11** — `n_min=5, n_max=5` con inventario que permite N_natural=12: el plan resultante tiene `raids_possible=5` y `remaining_troops` contiene las 7 raids "no usadas" como sobrantes.
- [ ] **CA-12** — `n_min=20` con inventario que solo permite N_natural=10: la alternativa se devuelve pero está al fondo del ranking (penalización +inf) y aparece un warning explicativo.
- [ ] **CA-13** — `n_min > n_max` en el request → 422 con `detail` legible.

---

## 7. Tests sugeridos

1. `test_balance_score_single_type` — 1 tipo activo → score = 0.0
2. `test_balance_score_uniform` — 2 tipos con el mismo ratio → score ≈ 0.0
3. `test_balance_score_unequal` — 2 tipos con ratios muy distintos → score > umbral
4. `test_raids_possible_exact` — verificar fórmula min_i floor con inventario concreto
5. `test_aggregate_arithmetic` — verificar que totales = N × oleada
6. `test_no_regression_no_balance_field` — request sin `balance` → mismo resultado que antes
7. `test_scoring_mode_aggregate_prefers_more_raids` — con inventario desbalanceado y `scoring_mode=aggregate`, la alternativa #1 tiene N estrictamente mayor que con `single`
8. `test_scoring_mode_single_unchanged_with_nmin_nmax` — `single` ignora `n_min/n_max` (no-regresión)
9. `test_n_max_caps_raids_possible` — `n_max=5` con N_natural=12 → `raids_possible=5`, sobrantes incrementados
10. `test_n_min_penalizes_below_threshold` — `n_min=20` con N_natural=10 → alternativa al fondo, warning presente
11. `test_n_min_greater_than_n_max_422` — Pydantic rechaza con 422

---

## 8. Reuso confirmado

| Pieza | Decisión |
|---|---|
| `POST /combat/optimize` | REUTILIZAR — extensión del contrato, sin endpoint nuevo |
| `find_optimal_attack` en `combat_optimizer.py` | MODIFICAR — añadir `_balance_score` y decoración de alternativas |
| `OptimizationWeights` dataclass | MODIFICAR — +1 campo `balance: float = 0.0` |
| `OptimizationAlternative` dataclass | MODIFICAR — +3 campos opcionales |
| `TroopResult` | REUTILIZAR para `remaining_troops` sin cambios |
| `AnimalResourceDrop` | REUTILIZAR para `aggregate.total_resources_gained` |
| `OptimizationWeightsRequest` DTO | MODIFICAR — +1 campo `balance` |
| `OptimizationAlternativeResponse` DTO | MODIFICAR — +3 campos opcionales |
| Formulario Modo B en `OptimizerPanel.jsx` | REUTILIZAR íntegro para Modo C |
| `MultiRaidAggregate` (entidad) | CREAR — nueva dataclass pequeña |
| `MultiRaidAggregateResponse` (DTO) | CREAR — Pydantic response DTO |
| 7 claves i18n | CREAR — en `es.js` y `en.js` |

---

## 14. Pasos de implementación ordenados

1. Añadir `MultiRaidAggregate` dataclass en `core/entities/combat.py`.
2. Añadir campo `balance` a `OptimizationWeights` y campos opcionales a `OptimizationAlternative`.
3. Implementar `_balance_score` en `combat_optimizer.py`.
4. Integrar `w_balance * _balance_score(...)` en `_score()`.
5. Añadir bloque de decoración (raids_possible, remaining_troops, aggregate) al construir `OptimizationAlternative`.
6. Añadir `MultiRaidAggregateResponse` DTO en `adapters/api/routes/combat.py`.
7. Añadir campo `balance` a `OptimizationWeightsRequest`; añadir 3 campos opcionales a `OptimizationAlternativeResponse`.
8. Actualizar helper de conversión entidad→DTO para los 3 campos nuevos.
9. Añadir 7 claves i18n en `es.js` y `en.js`.
10. Actualizar toggle en `OptimizerPanel.jsx` a 3 valores + preset Modo C + slider balance condicional.
11. Añadir render condicional multi-raid en `OptimizerResult.jsx`.
12. Escribir los 6 tests sugeridos.

---

## 15. Trazabilidad

| Decisión | Origen |
|---|---|
| No endpoint nuevo | Scope reducido acordado con usuario — extensión del contrato existente |
| `balance=0.0` default | RN-03 — retrocompatibilidad obligatoria |
| `raids_possible` en TODAS las alternativas (no solo ganadoras) | Decisión del usuario 2026-05-29 — quiere ver también el N "teórico" de oleadas suicidas para poder comparar |
| Frontend oculta columnas multi-raid en Modos A y B | Decisión UX — evitar ruido; datos presentes en response igualmente (RN-02) |
| `_balance_score=0` con 1 tipo | RN-01 extensión — sin referencia de comparación, stdev indefinido |
| Reutilizar `TroopResult` para remaining_troops | Sin entidad nueva justificada — la semántica encaja |
| API: contratos validados por analista contra código fuente existente | Herramienta Agent no disponible en contexto analista; revisión manual del patrón `OptimizationWeightsRequest` y `OptimizationAlternativeResponse` en `e5e4e20` |

🔖 Última revisión: 2026-05-29

---

## Registro de implementación

**Fecha**: 2026-05-29

**Ficheros creados**:
- `tests/unit/test_combat_optimizer.py` — 10 tests unitarios nuevos (UT-01..UT-09 + variante binding)

**Ficheros modificados**:
- `core/entities/combat.py` — `OptimizationWeights.balance`, `MultiRaidAggregate` (nueva entidad), `OptimizationAlternative` +3 campos opcionales
- `core/use_cases/combat_optimizer.py` — `_balance_score()`, `available_map`, `w_balance` en `_score()`, bloque de decoración multi-raid en `find_optimal_attack`
- `adapters/api/routes/combat.py` — `OptimizationWeightsRequest.balance`, `MultiRaidAggregateResponse` (nuevo DTO), `OptimizationAlternativeResponse` +3 campos, `_aggregate_to_response()`, serialización actualizada
- `frontend/src/i18n/catalog/es.js` — 7 claves nuevas (tabC, modeCHint, weight.balance, weight.balance.hint, multiRaid.raidsPossible, multiRaid.remaining, multiRaid.aggregate)
- `frontend/src/i18n/catalog/en.js` — mismo conjunto de 7 claves en inglés
- `frontend/src/components/combat/OptimizerPanel.jsx` — toggle 3 modos (MODES array), preset Modo C, slider balance condicional, `handleModeChange`, `onInputModeChange` callback
- `frontend/src/components/combat/OptimizerResult.jsx` — `MultiRaidBlock` (nuevo componente), render condicional en `DetailPanel`, prop `inputMode`
- `frontend/src/components/combat/CombatCalculator.jsx` — estado `optimizerInputMode`, propagado a `OptimizerPanel` y `OptimizerResult`

**Comando para ejecutar los tests**:
```
.venv/bin/python -m pytest tests/unit/test_combat_optimizer.py -v
.venv/bin/python -m pytest  # suite completa
```

**Resultado**: 911 passed, 23 skipped (suite completa); 10/10 nuevos tests en verde

**Desviaciones respecto al diseño**:
- `_balance_score` usa `ev["troop_entries"]` (lista de `TroopEntry` del atacante) en vez de `ev["troops_sent"]` (lista de `TroopResult`), porque `troops_sent` se obtiene tras la simulación mientras que `troop_entries` refleja las cantidades enviadas antes del combate. La semántica es idéntica al spec (sent_i = quantity enviada).
- Se añadieron 4 tests extra (UT-07 a UT-09 + variante binding) más allá de los 6 obligatorios del spec §7, todos cubren CAs explícitos.
- `OptimizerPanel` notifica al padre (`CombatCalculator`) del modo activo mediante `onInputModeChange` prop, en vez de elevar el estado al padre directamente, para preservar el encapsulamiento del componente. El `CombatCalculator` expone el estado a `OptimizerResult` como prop.
