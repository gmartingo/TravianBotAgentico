---
name: project-noise-frequency-weight
description: Frecuencia ruido por modo (MM:SS) y peso por destino (navigation_weight); decisiones cerradas del spec noise-frequency-and-destination-weight.md
metadata:
  type: project
---

Spec: `docs/specs/noise-frequency-and-destination-weight.md` — estado `ready-for-impl`, apis pendientes de gate.

**Decisiones cerradas:**

1. **Unidad = segundos en BD y API; MM:SS solo en UI.** El frontend convierte antes de enviar.
   Funciones `mmssToSeconds` / `secondsToMmss` en `frontend/src/utils/time.js`.

2. **Reemplaza `*_req_per_hour_*` por `*_interval_*_seconds`.** Los 4 campos deprecated se
   conservan en BD (sin borrar) para compatibilidad. La entidad `NoiseConfig` ya NO los tiene.

3. **Defaults (segundos):** HARDCORE 30-90 s; PASIVO 180-1200 s.

4. **Mínimo 5 s, sin máximo.** Validación en entidad y API.

5. **Eliminación del descuento de tráfico productivo** de `_calculate_next_noise_gap`.
   `recent_productive_traffic` ya no es parámetro. El intervalo directo lo hace innecesario.

6. **Cap del silence:** `[max(5, iv_min), min(7200, iv_max × 4)]` — se adapta al rango configurado.

7. **`navigation_weight` = alias semántico de `frequency_weight`** en el contrato de API
   (EP-N03/04/05). La BD y la entidad siguen usando `frequency_weight`. La lógica de
   selección ponderada (`random.choices` en `pick_random_safe_destination`) ya existe y no cambia.

8. **Rango UI recomendado para navigation_weight:** 0.1 – 10.0, step 0.1, default 1.0.

**Gates pendientes antes de implementar:**
- guardian-antideteccion: burst sub-intervalo, rango puntual (mín==máx), pesos extremos.
- desarrollador-apis: renombrado frequency_weight→navigation_weight en EP-N03/04/05; campos
  nuevos en EP-N01/02; validación cruzada PATCH parcial en EP-N02.

**Relación con specs previos:**
- `human-sessions.md §17` — sistema de ruido base (implementado).
- `noise-path-wizard.md` — anclas, wizard, derive-selector (implementado).
- `world_agent.py:787` — `_calculate_next_noise_gap` es el punto central de modificación.

**Why:** el usuario conceptualiza la frecuencia como tiempo-entre-eventos (MM:SS), no como
peticiones/hora. El weight permite variedad en las páginas visitadas sin cambiar la lógica
de selección ponderada ya existente.
