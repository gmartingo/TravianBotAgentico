---
name: farm-slots-schema-gotchas
description: Gotchas del esquema farm_slots/farm_lists/villages para tests de siembra SQL directa
metadata:
  type: feedback
---

farm_slots tiene PK compuesta (id, farm_list_id) SIN AUTOINCREMENT — el id debe proveerse explícitamente en INSERTs de test. NULL falla con NOT NULL constraint.

total_bounty fue eliminado de farm_slots por migración ALTER TABLE DROP COLUMN (farm_list_sqlite_adapter.py ~línea 348). El DDL en el código tiene la columna pero la BD real ya no la tiene. No incluir total_bounty en INSERTs de test.

villages requiere FK a worlds (world_id NOT NULL), que a su vez requiere accounts (account_id NOT NULL). Para sembrar villages en tests hay que insertar primero una cuenta y un mundo:
  accounts: (email, username, password BLOB, created_at, updated_at)
  worlds: (account_id, server, tribe, created_at, updated_at)
  villages: (world_id, data_id, name, x, y) + UNIQUE(world_id, data_id)
  farm_lists: (name, owner_village_id) — scheduler_id nullable
  farm_slots: (id, farm_list_id, target_name, x, y) — con todos los NOT NULL con defaults

Para FK huérfanas en tests: PRAGMA foreign_keys = OFF antes del INSERT, ON después.

La conexión del adaptador se obtiene con: app.state.attack_report_port._conn
Usar asyncio.run() para llamar corrutinas async desde helpers sync de test.

**Why:** implementación T-CITY-01..10 para inferencia híbrida de origin_villages en EP-SPAWN.
**How to apply:** cualquier test que necesite sembrar farm_slots/villages directamente.
