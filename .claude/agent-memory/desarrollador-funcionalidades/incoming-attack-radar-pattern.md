---
name: incoming-attack-radar-pattern
description: Patrón radar ataques entrantes: parsers puros sidebar+dorf1, hook transversal, SQLite datetime gotcha, frontera hexagonal con imports diferidos
metadata:
  type: project
---

## Patrón radar ataques entrantes (feature radar-ataques-entrantes, 2026-06-05)

### Discriminador Componente A
`div.listEntry.village.attack` es el ÚNICO indicador de ataque. `svg.attack` dentro de `span.incomingTroops` es señuelo permanente en TODAS las entradas — no usarlo como discriminador o genera falsos positivos en todas las aldeas.

### SQLite datetime gotcha
Los timestamps ISO-8601 Python (`2026-06-05T14:30:18+00:00`) NO son comparables directamente con `datetime('now')` en SQLite (que usa espacio `T`→` ` y no tiene zona). Usar `datetime(impact_at) > datetime('now')` para normalizar correctamente.

**Why:** La `T` vs espacio hace que el comparador de strings falle.
**How to apply:** Siempre en filtros WHERE de fechas ISO-8601 con zona en SQLite.

### Frontera hexagonal con imports diferidos (P5)
`WorldAgent` está en `core/` pero necesita importar `adapters/`. Patrón: import diferido dentro del método con `# noqa: PLC0415`. Esto NO añade entradas a `.importlinter`. Verificar con grep antes de cerrar:
```bash
grep -rn "^from adapters\|^import adapters" core/
```
Debe dar cero resultados.

### SQLite FK CASCADE en tests
Para probar ON DELETE CASCADE en tests SQLite en memoria, activar FK enforcement:
```python
await conn.execute("PRAGMA foreign_keys = ON")
```
Sin esto, el CASCADE no funciona aunque esté en el DDL.

### Patrón de inyección en use cases (frontera hexagonal)
Use cases en `core/` no pueden importar parsers de `adapters/`. Solución: reciben un callable inyectado que devuelve DTOs ya parseados. Ejemplo: `CheckIncomingAttackUseCase` recibe `fetch_dorf1_attacks: Callable[[int], Awaitable[list[Dorf1AttackDTO]]]`.

### Fallos preexistentes en la suite
`test_execute_invalid_token_raises_login_failed` y `test_post_session_invalid_token` fallan en develop (preexistentes). No son regresiones de esta feature.

### WorldAgent — parámetro opcional para nuevos ports (P4)
Seguir el patrón de `noise_db`: parámetro `incoming_db=None` en el constructor. El WorldAgent funciona sin el port inyectado (modo degradado silencioso).

Ver: [[noise-navigation-pattern]], [[session-registry-pattern]]
