---
name: project-combat-simulator-design
description: Decisiones de diseño de la Calculadora (Simulador + Optimizador de combate) — spec ready-for-impl
metadata:
  type: project
---

Spec de diseño: docs/design/simulador-combate-ui.md (estado: ready-for-impl).
Mockup editable: frontend/mockups/simulador-combate.playground.html (pendiente aprobación usuario — vista 7 resincronizada 2026-05-30).
Spec funcional relacionado: docs/specs/simulador-combate.md.

La pestaña "Calculadora" vive en WorldSpacePage como nav item 'calc'. Para activarla:
quitar `disabled: true` y `soon: true` del nav item 'calc' en WorldSpacePage.jsx (líneas ~356-359).

**LAYOUT REAL DEL CÓDIGO (actualizado 2026-05-30):**
El código real usa columna única (maxWidth:720px, margin:0 auto, flexDirection:'column').
NO hay split formulario/resultado de 2 columnas. El spec original describía ese layout pero el
código implementó columna única. El mockup vista 7 ya refleja esto.

Estructura real de CombatCalculator.jsx:
- Cabecera: h2 "Calculadora de combate" + div[role=tablist] con 2 botones (Simulador/Optimizador)
  inline al lado del título — NO es un segmento separado.
- Modo simulador: ArmyPanel atacante → ArmyPanel defensor → ArmyPanel refuerzo(s) → btn "Añadir
  refuerzo" (dashed full-width) → btn "Simular" (primario full-width 40px) → CombatResult.
- Modo optimizador: OptimizerPanel → OptimizerResult.

**ArmyPanel.jsx — estructura real:**
- Header: icon SVG de rol (espada/escudo) + label UPPERCASE 13px + btn colapsar (chevron).
  Refuerzo añade btn papelera antes del chevron.
- Body: fila controles inline → bloque héroe expandible (opcional) → mods-card (ADD) →
  TribeBar (chips) → TroopGrid (horizontal).
- Controles atacante inline: AttackTypeToggle (pill Saqueo/Ataque, height 26px) +
  AllianceBonusSelect (select 26px) + ArtifactSelect (select 26px) + btn Héroe (expand).
- Controles defensor inline: escudo SVG + NumInput muro 42px + ⚒ + NumInput cantero 42px +
  AllianceBonusSelect + btn Héroe (expand).
- Héroe expandido (inline, no bloque aparte): flex-wrap con campos "Pts. ataque/defensa héroe"
  (70px) y "Bonus % héroe" (60px), fondo surface-2 padding 10px 12px.

**TribeBar.jsx — chips 44px:**
Chips circulares `width:44px height:44px border-radius:full`. Iniciales 2 letras mayúsculas.
Activo: border+outline 2px accent + fondo TRIBE_COLORS por tribu. NO dropdown.
Atacante: 7 tribus (sin Nature). Defensor/refuerzo: 8 tribus (Nature primero).

**TroopGrid.jsx — grid horizontal:**
overflow-x:auto. Columna de etiquetas (escudo SVG 14px + yunque SVG 14px) + N columnas tropa.
Cada columna: icono 28px / input qty 52×28px / input smithy 52×24px (transparent border).
qty=0 → opacity:0.45. Defensor no usa smithy (showSmithy siempre true en el código actual).

**TravianReport.jsx — resultado real:**
- Pill badge (winner) + ratio string font-mono.
- TroopBand "Tú": tabla table-layout:fixed, col "Tropa" 104px fixed + cols tropa reparto.
  thead: iconos. tbody: 3 filas (Enviadas / Pérdidas / Supervivientes). Scroll horizontal en overflow-x:auto.
- TroopBand "Defensor" (y refuerzos si los hay): misma estructura.
- StatsTable: tabla fuerza (inf/cav con GameIcon png + % col) + sub-tabla recursos
  (col lbl 180px + W/C/I/C + Σ 88px). Filas: Botín animales (verde) + Coste tropas (rojo) +
  Neto (verde/rojo/grey, negrita). Neto tiene background surface-2.
- Warnings: pills accent-subtle si result.warnings.length > 0.
- NO hay "Botín potencial", "Consumo trigo", ni "Pérdidas en recursos" colapsable.

**Addendum pendiente de implementar (no en código real):**
- morale% en héroe atacante.
- artifacts.diet (el bloque "Artefactos" no existe en ArmyPanel — ArtifactSelect solo maneja fast_troops).
- wall_tribe select en defensor (debajo de muro/cantero).
- strong_buildings en sub-bloque "Artefactos defensor".
- Bloque "Configuración" colapsable P3: server_speed + distance_fields.
- Bloque "Catapultas y arietes" colapsable (solo modo Ataque): rams + catapult_targets.
- mods-card reactiva debajo de controles en cada ArmyPanel.
- Bloque "Cadena de cálculo" colapsable en el resultado (entre TroopBands y StatsTable).

**Why:** La Calculadora es una herramienta de decisión pre-ataque. El usuario llega con pregunta
concreta y necesita el resultado rápido. El código optó por columna única (más simple, más responsive).

**How to apply:** Al implementar el addendum, respetar la composición real: los inputs nuevos van
dentro de la fila de controles inline de ArmyPanel o en los bloques específicos del panel.
No añadir secciones ni colapsables propios — aprovechar la estructura ya existente.
