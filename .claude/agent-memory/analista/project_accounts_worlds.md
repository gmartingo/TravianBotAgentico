---
name: project-accounts-worlds
description: Decisiones cerradas del diseño de registro de cuentas y mundos Travian (email-unicidad, Fernet, PlayableTribe, cascada, WorldRuntimePort)
metadata:
  type: project
---

## Decisiones del spec registro-cuentas-mundos (2026-05-25)

Unicidad de cuenta por EMAIL (no username) — modelo lobby Travian moderno. DuplicateAccountError recibe email (no username). Impacto: cambio de firma de la excepción existente, pero no hay lanzadores previos.

Contraseña cifrada con Fernet (reversible) — justificación: el bot necesita la password en claro para hacer login automatizado en Travian. bcrypt no sirve. Clave en TRAVIAN_BOT_SECRET_KEY (variable de entorno). Si falta al arrancar → RuntimeError, la app no inicia.

PLAYABLE_TRIBES = frozenset de 7 tribus {ROMANS, TEUTONS, GAULS, EGYPTIANS, HUNS, SPARTANS, VIKINGS}. NATURE y NATARS son NPC (is_playable=False). En la API se usa PlayableTribe (enum Pydantic con solo las 7 jugables) para que FastAPI devuelva 422 automáticamente con tribus NPC.

AccountSQLiteAdapter — nuevo adaptador que implementa DbPort extendido. Patrón: constantes DDL, ensure_tables() con PRAGMA foreign_keys=ON, UPSERT idempotente, helpers _row_to_X. Igual que GameDataSQLiteAdapter. La tabla villages se crea en esquema pero sin endpoints (VillageMapUseCase la populará).

WorldRuntimePort.is_active() no implementado aún. Degradación segura: asumir inactivo + WARNING en log. Se revisará cuando SessionRegistry esté implementado.

N+1 en list_accounts (una query de worlds por cuenta) — aceptado con la escala actual (1-10 cuentas). Si escala: resolver con JOIN.

IntegrityError de SQLite → mapear a DuplicateAccountError/DuplicateWorldError en el adaptador (UNIQUE constraint como red de seguridad ante race conditions).

Nuevas excepciones añadidas: DuplicateWorldError, ActiveSessionConflictError.
Nuevas entradas en error_codes.py: DUPLICATE_WORLD→409, ACTIVE_SESSION_CONFLICT→409.

Perfil de Chrome: profiles/account_{id}/ — convención documentada, no se crea en esta feature.

**Why:** El spec completo está en docs/specs/registro-cuentas-mundos.md.
**How to apply:** En futuros specs que toquen cuentas/mundos, partir de estas decisiones como base.

[[project-arch-conventions]]
