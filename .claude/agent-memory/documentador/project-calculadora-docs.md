---
name: project-calculadora-docs
description: calculadora de combate (simulador + optimizador multiraid) documentada 2026-06-04: rutas de archivos, 10 capturas usadas, divergencias detectadas
metadata:
  type: project
---

Documentación de la Calculadora de combate completada el 2026-06-04.

## Archivos creados / actualizados

| Archivo | Tipo | Estado |
|---|---|---|
| `documentacion/funcionalidades/simulador-combate.md` | Tipo 2 (negocio) | Ya existía — no tocado en esta sesión |
| `documentacion/funcionalidades/optimizador-balance-multiraid.md` | Tipo 2 (negocio) | Ya existía — no tocado en esta sesión |
| `documentacion/backend/simulador-combate.md` | Tipo 1 (código) | Ya existía — no tocado en esta sesión |
| `documentacion/manual-usuario/calculadora.html` | Tipo 3 (usuario) | **CREADO en esta sesión** |

## Capturas usadas en calculadora.html (10 de 20 disponibles)

| Archivo | Sección | Descripción real de la captura |
|---|---|---|
| calc-01-vista-inicial.png | Figura 1 | Vista inicial simulador, todos campos vacíos, botones RO + NA seleccionados |
| calc-03-tropas-atacante.png | Figura 2 | Simulador: atacante RO con 500 T1 + 200 T3 |
| calc-04-defensor-oasis.png | Figura 3 | Simulador: defensor NA con 15 arañas, muro 20×5 |
| calc-05-resultado-simulador.png | Figura 4 | Simulador tras clic Simular: badge "Atacante gana", Ratio 32.38 |
| calc-07-modo-ataque.png | Figura 5 | Simulador con modo Ataque activo |
| calc-07-optimizador-inicial.png | Figura 6 | Optimizador inicial modo Multi-tropa, defensa vacía |
| calc-09-modo-simulador-ejercito.png | Figura 8 | Optimizador modo Simulador ejército con campos cantidad+herrería |
| calc-10-modo-multi-raid.png | Figura 9 | Optimizador modo Multi-raid con sección Rango de raids |
| calc-11-resultado-optimizador.png | Figura 7 | Optimizador con resultado: T1=20 activo, 20 ratas, 3 combinaciones ganadoras |
| calc-12-detalle-alternativa.png | Figura 10 | Tabla de resultado con 3 alternativas: tropas, bajas, rec. ganados, neto |

## Capturas disponibles pero NO usadas (descartadas por duplicación visual)

calc-02-tribu-atacante.png, calc-02-tribu-seleccionada.png, calc-04-defensor-nature.png, calc-06-stats-recursos.png, calc-06-stats-tabla.png, calc-08-modo-b.png, calc-08-optimizador-multi-tropa.png, calc-09-modo-c.png, calc-10-resultado-optimizador.png, calc-11-tabla-alternativas.png

**Por qué descartadas**: muchas son visualmente idénticas o muestran el mismo estado con diferencias mínimas (mismo screenshot tomado dos veces). Se eligió la más representativa de cada estado.

## Divergencias código/spec ya documentadas en las fuentes

Ver `documentacion/funcionalidades/simulador-combate.md` §7 y `documentacion/funcionalidades/optimizador-balance-multiraid.md` §8:
- Drops Tigre/Elefante: código usa 240/300, spec dice 120/200 — código es el válido.
- `loot_potential` solo si atacante gana (spec no lo explicitaba).
- Labels de modos UI más descriptivos que el spec ("Multi-tropa" vs "A").
- `_balance_score` usa `troop_entries` no `troops_sent` — semántica idéntica, no es error.
- Gids de muro para HU/SP/VI: fallback aproximado con warning.

## Línea de índice sugerida para README y es/index.html

`- [Calculadora de combate](manual-usuario/calculadora.html) — Simulador de combate y optimizador de balance multiraid`

**Why:** primera feature de simulación táctica del bot; importante para el flujo de farmeo de oasis.
**How to apply:** si se actualiza la calculadora (nuevas tribus, nuevos modos), actualizar calculadora.html editando las secciones afectadas sin reescribir la página completa.
