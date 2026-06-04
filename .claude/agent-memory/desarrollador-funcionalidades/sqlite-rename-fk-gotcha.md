---
name: sqlite-rename-fk-gotcha
description: SQLite RENAME TABLE con FK hijas activas (legacy_alter_table=OFF) reescribe las FK hijas — patrón correcto de migración de tabla padre con foreign_keys=OFF
metadata:
  type: feedback
---

SQLite >= 3.25 con `legacy_alter_table=OFF` (default) reescribe automáticamente
las FK de las tablas hijas cuando se renombra la tabla padre. Esto corrompe la BD
si después se elimina la tabla con el nombre antiguo.

**Problema concreto (M-NP01):** `ALTER TABLE noise_navigation_paths RENAME TO
noise_navigation_paths_old` hizo que `noise_navigation_steps.path_id` pasara a
`REFERENCES "noise_navigation_paths_old"`. Al hacer `DROP TABLE
noise_navigation_paths_old`, esa FK quedó rota → 500 en `create_path`.

**Patrón correcto (procedimiento oficial SQLite §7 "12 pasos"):**
1. `PRAGMA foreign_keys=OFF`
2. `SAVEPOINT`
3. CREATE nueva tabla con nombre temporal (`_new`)
4. INSERT desde vieja
5. DROP vieja
6. RENAME `_new` → nombre definitivo (con FK OFF, SQLite NO reescribe nada)
7. Recrear índices
8. `PRAGMA foreign_key_check` (verificar antes de confirmar)
9. `RELEASE SAVEPOINT` (o `ROLLBACK TO` si falla)
10. `PRAGMA foreign_keys=ON` (en finally)

**Why:** Con `foreign_keys=OFF`, el paso 6 (RENAME) no dispara la reescritura
automática de FK en tablas hijas. Las FK de las hijas ya apuntaban al nombre
definitivo desde el principio (nunca se renombró la tabla original), así que
quedan correctas.

**How to apply:** Siempre que una migración necesite recrear una tabla que tiene
tablas hijas con FK, usar este patrón. NUNCA usar el patrón RENAME→CREATE→INSERT→DROP
con `foreign_keys=ON`.

**Auto-reparación idempotente (M-NP03):** Si la corrupción ya ocurrió,
detectarla inspeccionando `SELECT sql FROM sqlite_master WHERE
name='noise_navigation_steps'` buscando `noise_navigation_paths_old`. Si está,
recrear la tabla hija con el mismo procedimiento de 12 pasos.

Ref: https://www.sqlite.org/lang_altertable.html §7
