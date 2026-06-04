---
name: feedback-confirm-metric-before-stats-change
description: "Antes de implementar un cambio en una métrica/estadística, confirmar QUÉ métrica y QUÉ pantalla exactas; no saltar a un encuadre técnico"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c1acc212-8aad-434f-8af0-4d2d7bfa3a21
---

Cuando el usuario pide cambiar "los cálculos de X" en una vista con varias métricas (tasas, %, conteos), confirmar PRIMERO cuál métrica concreta y en qué pantalla, y la definición exacta del denominador/numerador, antes de especificar e implementar.

**Why:** En la feature de reportes-oasis interpreté "que solo cuenten los reportes con esa tropa" como un arreglo de la TASA de regeneración por-animal (gap por-animal en EP-06/09/10), lo implementé entero con spec+API+tests, y el usuario respondió "no me has entendido": el pedido real era el **% de aparición GLOBAL** (denominador = reportes de oasis donde ese animal apareció alguna vez; la vista de oasis individual cuenta todos). Hubo que descartar todo lo anterior.

**How to apply:** Ante un pedido sobre estadísticas, hacer 1-2 preguntas que distingan métrica/pantalla/denominador con un ejemplo numérico ANTES de lanzar analista/implementación. Mis preguntas con AskUserQuestion fueron útiles pero partían de un encuadre ya equivocado; primero validar el encuadre. Relacionado con [[features-split-across-unmerged-branches]] (el WIP de reportes-oasis vive sin commitear).
