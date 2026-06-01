# Referencia de API — TravianBot

> **FastAPI genera el OpenAPI automáticamente** en `http://localhost:8000/docs` (Swagger UI)
> y `http://localhost:8000/openapi.json`. Consultar esa URL para el contrato completo de
> los endpoints existentes (EP-01..EP-09). Este archivo documenta EP-10 como primer
> artefacto permanente; el resto se irá completando en futuras iteraciones.

## Índice

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/attack-reports/stats/oasis/comparison` | Comparativa de reaparición por oasis | No |

---

## EP-10 — Comparativa de tasas de reaparición por oasis

**`GET /attack-reports/stats/oasis/comparison`**

### Descripción de negocio

Devuelve, para todos los oasis conocidos en BD, la tasa bruta de reaparición de animales
(animales/hora por especie) y la proyección del número de animales acumulados en el
momento exacto de la petición. Permite al usuario comparar qué oasis regeneran más rápido
y decidir cuándo volver a atacar.

- La proyección es lineal: `floor(survived_último_ataque + tasa × horas_transcurridas)`.
- Si el último ataque fue una derrota (survived=null), la proyección de esa especie es null.
- Un oasis con un solo reporte no tiene intervalos válidos → `has_rates: false`, `species: []`.
- Un oasis donde nunca apareció la especie X **no la incluye en su `species[]`** (ausencia semántica, no cero).
- `species_columns` son las columnas dinámicas de la tabla UI: unión de todas las especies
  con tasa en algún oasis. La UI infiere "—" cuando un oasis no tiene la especie en su array.

### Request

```
GET /attack-reports/stats/oasis/comparison
```

Sin query params. Sin headers requeridos. Sin body.

### Response 200

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
        },
        {
          "animal_ordinal": 3,
          "animal_name": "Spider",
          "icon_url": "/static/icons/nature_3.png",
          "avg_regen_per_hour": 0.80,
          "valid_intervals": 4,
          "last_survived": null,
          "projected_now": null
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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `computed_at` | string ISO 8601 UTC | Momento en que se calculó la proyección |
| `species_columns` | array | Columnas dinámicas de la tabla (unión de especies con tasa) |
| `species_columns[].icon_url` | string | `/static/icons/nature_{ordinal}.png` |
| `oasis[].last_attack` | string ISO 8601 naive | Hora local de Travian (sin zona horaria) |
| `oasis[].hours_since_last_attack` | float ≥ 0 | Horas entre `last_attack` (ajustado a UTC) y `computed_at` |
| `oasis[].has_rates` | bool | True si ≥1 especie tiene tasa calculada |
| `species[].last_survived` | int \| null | Survived del último reporte; null si fue derrota |
| `species[].projected_now` | int \| null | `floor(last_survived + rate × hours)`, mínimo 0; null si `last_survived` es null |

### Response de error

| Código | Condición |
|--------|-----------|
| `200` | Siempre (incluso BD vacía: `oasis: []`) |
| `500` | Error inesperado de BD |

### Ejemplo curl

```bash
curl http://localhost:8000/attack-reports/stats/oasis/comparison
```

---

🔖 Última revisión: 2026-06-01
