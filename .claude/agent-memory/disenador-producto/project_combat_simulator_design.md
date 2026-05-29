---
name: project-combat-simulator-design
description: Decisiones de diseño de la Calculadora (Simulador + Optimizador de combate) — spec ready-for-impl
metadata:
  type: project
---

Spec de diseño: docs/design/simulador-combate-ui.md (estado: ready-for-impl).
Mockup editable: frontend/mockups/simulador-combate.playground.html (pendiente aprobación usuario).
Spec funcional relacionado: docs/specs/simulador-combate.md.

La pestaña "Calculadora" vive en WorldSpacePage como nav item 'calc'. Para activarla:
quitar `disabled: true` y `soon: true` del nav item 'calc' en WorldSpacePage.jsx (líneas ~356-359).

Estructura de la pestaña:
- Segmento superior: "Simulador" / "Optimizador" (mismo patrón que mode-toggle de farm lists).
- Layout desktop (≥ lg): split horizontal — formulario fijo 420px izquierda / resultado flex:1 derecha.
- Layout móvil (< md): formulario arriba, resultado abajo. Cuando hay resultado, el formulario se colapsa en banner colapsable.

Decisiones clave de diseño:
- Todas las tropas de la tribu siempre visibles (nunca añadir/quitar) — tropas con qty=0 atenuadas al 45%.
- Tribu NATURE como defensor por defecto (caso oasis, job principal del usuario).
- Toggle Saqueo/Ataque: modo Saqueo por defecto (RN-13); los campos de catapultas/arietes aparecen solo en modo Ataque.
- Configuración avanzada (exponente, artefactos, pesos) en paneles colapsables cerrados por defecto.
- Badge de resultado como primer elemento visual P1: color (verde/rojo) + icono + texto (accesibilidad — nunca solo color).
- Recursos de animales muertos: desglose por tipo (madera/arcilla/hierro/trigo) con iconos de recurso. Nunca un total único.
- Pérdidas en recursos: panel colapsable P2, arranca cerrado.
- Daño estructural: solo visible cuando `structural_damage !== null` (solo modo Ataque).

Optimizador:
- Modo A (tipos libres): lista de tropas con checkbox + smithy (deshabilitado si no marcado).
- Modo B (tropas con cantidades): misma lista con input de disponible + smithy.
- 10 animales NATURE siempre fijos como defensa del oasis (sin añadir/quitar).
- Pesos de optimización: sliders min=0 max=2 step=0.1, colapsados P3.
- Tabla de alternativas: iconos de tropas apilados (máx 4 + "+N más"), badge gana/no gana, números mono.
- Detalle de alternativa: inline debajo de la tabla al hacer clic en fila (no modal).
- Banner "Sin combinación ganadora": solo cuando `has_winning_combination: false`.

Componentes nuevos principales a crear: CalcTab, ModeSegment, TribeSelector, TroopInputList, TroopResultTable, LootPanel, ResourceLossPanel, StructuralDamagePanel, WarningChips, AlternativeTable, AlternativeDetail, NatureDefenseInput, OptimizationWeightsPanel.

Componentes reutilizados: Spinner, showToast, ErrorBoundary, useI18n, api.getCatalogIcons, patrón FormField/inputBase.

**Why:** La Calculadora es una herramienta de decisión pre-ataque. El usuario llega con una pregunta concreta y necesita el resultado rápido. El split formulario/resultado en desktop permite iterar sin perder contexto.

**How to apply:** Al implementar, respetar el split 420px/flex. Las tablas de resultado usan el mismo patrón de tablas densas establecido en DESIGN.md §12 (hairline, sin zebra, font-mono tabular-nums). El resultado tiene `role="status" aria-live="polite"`.
