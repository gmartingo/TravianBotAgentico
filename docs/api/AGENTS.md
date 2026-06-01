# Referencia de APIs para agentes — TravianBot

## Convenciones globales

- **Base URL (desarrollo):** `http://localhost:8000`
- **Sin prefijo `/api`** — el proxy de Vite retira `/api` antes de redirigir a `:8000`.
  En producción la base URL es la misma (sin prefijo adicional).
- **Autenticación:** ninguno de los endpoints de `attack-reports` requiere auth.
- **Content-Type:** `application/json` en requests con body.
- **Accept-Language:** no requerido en el router `attack-reports` (datos numéricos + texto crudo).
  Obligatorio en endpoints de catálogo (`/catalog/*`).

## Formato de error estándar

```json
{
  "detail": "<mensaje legible>"
}
```

FastAPI usa `detail` por defecto. Los endpoints de attack-reports no devuelven stack traces.

---

## Endpoints documentados

### EP-10 — Comparativa de tasas de reaparición por oasis

**Endpoint:** `GET /attack-reports/stats/oasis/comparison`
Devuelve la tasa bruta de reaparición de animales y la proyección del número acumulado
en el momento de la petición, para todos los oasis conocidos en BD.

**Auth:** ninguna.

**Headers requeridos:** ninguno.

**Request:** sin body, sin query params.

**Response OK (200):**
```json
{
  "computed_at": "2026-06-01T12:34:56.789012+00:00",
  "species_columns": [
    { "animal_ordinal": 1, "animal_name": "Rat",    "icon_url": "/static/icons/nature_1.png" },
    { "animal_ordinal": 7, "animal_name": "Tiger",  "icon_url": "/static/icons/nature_7.png" }
  ],
  "oasis": [
    {
      "coord_x_dest": -70,
      "coord_y_dest": 73,
      "total_attacks": 8,
      "last_attack": "2026-05-30T20:15:00",
      "hours_since_last_attack": 16.3,
      "has_rates": true,
      "species": [
        {
          "animal_ordinal": 7,
          "animal_name": "Tiger",
          "icon_url": "/static/icons/nature_7.png",
          "avg_regen_per_hour": 1.25,
          "valid_intervals": 6,
          "last_survived": 3,
          "projected_now": 23
        }
      ]
    },
    {
      "coord_x_dest": 12,
      "coord_y_dest": -45,
      "total_attacks": 1,
      "last_attack": "2026-05-28T10:00:00",
      "hours_since_last_attack": 50.6,
      "has_rates": false,
      "species": []
    }
  ]
}
```

**Errores:**
- `500` → error inesperado de BD (detail genérico, sin stack trace).
- BD vacía → `200` con `oasis: []` y `species_columns: []` (no es un error).

**Reglas de negocio clave:**
- `species_columns`: unión de todas las especies con tasa en AL MENOS UN oasis. Orden por `animal_ordinal` ASC.
- `species[]` de cada oasis: solo especies con tasa válida. Si una especie no está, significa "—" (ausencia), NO cero.
- `projected_now = null` si `last_survived` es null (derrota en último reporte) o si `hours_since_last_attack < 0`.
- `projected_now = floor(last_survived + avg_regen_per_hour × hours_since_last_attack)`, mínimo 0.
- Oasis con `has_rates: true` aparecen antes; dentro del grupo, `last_attack DESC`.
- `last_attack` es hora local de Travian (naive, sin zona).
- `hours_since_last_attack` se calcula ajustando por `utc_offset` del último reporte; si es null, se asume UTC.

**Ejemplo:**
```bash
curl http://localhost:8000/attack-reports/stats/oasis/comparison
```

**Detalle:** `docs/api/openapi.yaml` → paths `/attack-reports/stats/oasis/comparison`

---

> Para el contrato de otros endpoints (EP-01..EP-09) ver los specs en `docs/specs/bd-ataques-oasis.md`
> y relacionados. Se documentarán aquí en futuras iteraciones del agente `desarrollador-apis`.
