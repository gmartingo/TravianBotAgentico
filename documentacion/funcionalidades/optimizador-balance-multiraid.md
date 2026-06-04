# Funcionalidad: Optimizador de balance multiraid

Spec: `docs/specs/optimizador-balance-multiraid.md` (estado: `implemented`, 2026-05-29)
Spec base: `docs/specs/simulador-combate.md` §RN-09, §RN-10
Diseño UI: `docs/design/simulador-combate-ui.md` §6.4, §6.5
Doc de código: `documentacion/backend/simulador-combate.md`

---

## 1. Qué problema resuelve

El jugador que farmea oasis con frecuencia enfrenta dos decisiones repetidas cada día:

1. **¿Qué tropas enviar?** — sin saber qué combinación minimiza las pérdidas.
2. **¿Cuántas veces puedo repetir esto?** — con un inventario finito de tropas.

El optimizador automatiza ambas decisiones. Dado un oasis y un conjunto de tropas disponibles, calcula las combinaciones de tropas que mejor cumplen con los objetivos del jugador (maximizar recursos obtenidos, minimizar bajas) y devuelve un ranking Pareto de alternativas. El Modo C ("Multi-raid") añade la proyección de cuántas veces se puede repetir la oleada óptima antes de agotar el inventario.

---

## 2. Actores

| Actor | Rol |
|---|---|
| Jugador | Configura los objetivos y el inventario; interpreta el ranking de alternativas |
| API `/combat/optimize` | Ejecuta la optimización multi-objetivo en el backend |
| `simulate_combat` | El optimizador evalúa cada candidato llamando al mismo motor de combate del simulador |
| pymoo / fallback por muestreo | Algoritmo que explora el espacio de combinaciones |

---

## 3. Los tres modos del optimizador

| Modo | Label en UI | Qué hace |
|---|---|---|
| **A** | "Multi-tropa" | El usuario marca qué tipos de tropa puede usar (sin cantidad). El optimizador busca la mínima combinación ganadora de esos tipos. |
| **B** | "Simulador ejército" | El usuario introduce su inventario real (cantidades por tropa). El optimizador respeta esas cantidades como límite máximo. |
| **C** | "Multi-raid" | Igual que B pero con scoring por agregado de N raids: el sistema elige la oleada que, repetida muchas veces, da más beneficio total. Añade columnas: cuántas veces puedes repetir la oleada, tropas sobrantes y totales acumulados. |

---

## 4. Reglas de negocio

### Criterio de optimización

El optimizador evalúa cuatro objetivos (todos configurables con pesos):

| Objetivo | Peso por defecto | Descripción |
|---|---|---|
| Recursos ganados de animales | 1.0 | Maximiza los drops de NATURE al matar todos los animales |
| Pérdidas en recursos | 1.0 | Minimiza el coste de producción de las tropas perdidas |
| Tropas enviadas | 0.5 | Minimiza el número total de tropas enviadas |
| Tiempo de marcha | 0.0 | Solo si se proporciona distancia |

El resultado es un **frente de Pareto**: ninguna alternativa domina a otra en todos los objetivos al mismo tiempo. Así el usuario elige según sus prioridades del momento.

### Score de balance (Modo B/C)

Cuando hay inventario, el peso `balance` penaliza las alternativas que usan un tipo de tropa desproporcionadamente más que los otros. Se calcula como la desviación estándar de los ratios `enviadas / disponibles` por tipo. Un uso homogéneo de todas las tropas da `balance_score = 0` (sin penalización).

El Modo C aplica un preset: `resources_gained=1.0, total_losses=1.5, troops_sent=0.5, balance=1.5`. Esto favorece oleadas que usen el inventario de forma equilibrada y minimicen las bajas (porque se van a repetir muchas veces).

### Scoring por agregado (Modo C — scoring_mode="aggregate")

Sin el scoring por agregado, el optimizador preferiría oleadas únicas grandes con alto loot por raid. El Modo C invierte la lógica: los términos del score se multiplican por N (número de raids posibles con ese inventario), así que una oleada pequeña repetible 50 veces puntúa mejor que una grande repetible solo 2 veces.

### Restricción de rango N (Modos C)

El usuario puede acotar el número de raids con `n_min` y `n_max`:

| Combinación | Comportamiento |
|---|---|
| `(null, null)` | El optimizador decide libremente |
| `(X, null)` | Mínimo X raids — alternativas que no alcancen X quedan penalizadas al fondo del ranking |
| `(null, X)` | Como máximo X raids; las tropas no consumidas aparecen en "sobrantes" |
| `(X, X)` | Exactamente X raids |

Si el inventario no permite alcanzar `n_min`, la alternativa se devuelve igualmente (para transparencia) pero con una penalización infinita en el score.

### Garantía de resultado no vacío

El optimizador **siempre devuelve alternativas**, incluso si ninguna gana la batalla. En ese caso devuelve las mejores no-ganadoras (las que más se aproximan a ganar, por mayor ratio o menores pérdidas) y marca `has_winning_combination: false` con un mensaje explicativo.

---

## 5. Qué decide el usuario con el optimizador

- Cuál de las combinaciones del frente Pareto encaja mejor con sus prioridades del día.
- Si tiene suficientes tropas para atacar el oasis rentablemente.
- Cuántas veces puede repetir la oleada elegida (Modo C) antes de agotar el inventario.
- Si vale la pena cambiar la composición de tropas para maximizar el neto de recursos.

---

## 6. Valor para el negocio

El Modo C es la clave de valor diferencial frente al simulador: en Travian se farmea el mismo oasis varias veces al día. Un jugador que optimiza una sola oleada y la repite 20 veces obtiene mucho más que uno que envía de forma intuitiva. El optimizador cuantifica exactamente esa diferencia.

---

## 7. Casos límite

| Situación | Comportamiento |
|---|---|
| Modo A + tropas NATURE como atacante | Permitido técnicamente, warning en el response ("resultado no representativo") |
| Troop_types y village_troops simultáneos | 422 (son mutuamente excluyentes por diseño) |
| N natural < n_min | Alternativa incluida con penalización +inf, aparece al fondo del ranking, y se emite warning |
| Modo A sin ninguna tropa seleccionada | 422 "El ejército atacante no tiene tropas activas" |
| 1 solo tipo de tropa activo | `balance_score = 0` (sin stdev definida para 1 elemento) |
| pymoo no disponible | Fallback por muestreo en dos fases (gruesa ~10% + fina paso 1) + fase dirigida por rango N |

---

## 8. Divergencias código / spec detectadas (2026-06-04)

| Referencia | Spec dice | Código real |
|---|---|---|
| `_balance_score` — fuente de datos | Spec §3.3 dice usar `ev["troops_sent"]` (TroopResult) | Código usa `ev["troop_entries"]` (lista de TroopEntry con `quantity` = enviadas). Semántica idéntica; la desviación está documentada en el propio registro de implementación del spec. No es un error. |
| Labels de los modos en UI | Spec: "A", "B", "C" / radio buttons | UI real: "Multi-tropa", "Simulador ejército", "Multi-raid" — labels más descriptivos que los del spec. No es un bug, es mejora UX. |
| Modos A y B sin `scoring_mode` visible | Spec RN-04 describe `scoring_mode` como parámetro de request | La UI envía `scoring_mode="single"` para B y `scoring_mode="aggregate"` para C automáticamente — el usuario no lo configura manualmente. El spec describe el contrato de API, no necesariamente cada control de UI. |

🔖 Última revisión: 2026-06-04
