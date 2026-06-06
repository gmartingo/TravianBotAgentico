"""
Adaptador SQLite para el subsistema de Ruido Humano de Navegación (NoiseDbPort).

Tablas gestionadas (DDL inline, idempotente):
  - noise_destinations       — destinos de navegación de ruido
  - noise_navigation_paths   — rutas hacia destinos (origin + pasos)
  - noise_navigation_steps   — pasos individuales de una ruta
  - world_noise_config       — configuración de ruido por mundo

Decisiones de diseño:
  - FK CASCADE en paths → destination y steps → path para borrado limpio.
  - UNIQUE (world_id, url_pattern) en noise_destinations.
  - UNIQUE (path_id, step_order) en noise_navigation_steps.
  - Una fila por world_id en world_noise_config (creada con defaults en get_or_create).
  - La validación de URL ocurre en create_destination antes de tocar BD.
  - El dominio de la URL se valida contra el server del mundo leído de la tabla worlds.
  - steps=[] en update_path lanza ValueError (ruta sin pasos no es válida).

Spec human-sessions.md §7 (v2.2 — Ruido Humano de Navegación).
"""
from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import aiosqlite

from core.entities.noise import (
    NavigationOrigin,
    NavigationPath,
    NavigationStep,
    NoiseAction,
    NoiseConfig,
    NoiseDestination,
)
from core.ports.noise_db_port import NoiseDbPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_NOISE_DESTINATIONS = """
CREATE TABLE IF NOT EXISTS noise_destinations (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id                  INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    url_pattern               TEXT    NOT NULL,
    label                     TEXT    NOT NULL,
    category_slug             TEXT    NOT NULL DEFAULT 'uncategorized',
    frequency_weight          REAL    NOT NULL DEFAULT 1.0
                                      CHECK (frequency_weight >= 0.1 AND frequency_weight <= 5.0),
    is_safe                   INTEGER NOT NULL DEFAULT 1,
    is_dead                   INTEGER NOT NULL DEFAULT 0,
    consecutive_failures_count INTEGER NOT NULL DEFAULT 0,
    created_at                TEXT    NOT NULL,
    last_used_at              TEXT,
    UNIQUE (world_id, url_pattern)
);
"""

_CREATE_IDX_NOISE_DESTINATIONS_WORLD = """
CREATE INDEX IF NOT EXISTS idx_noise_destinations_world
    ON noise_destinations(world_id, is_dead, is_safe);
"""

_CREATE_NOISE_NAVIGATION_PATHS = """
CREATE TABLE IF NOT EXISTS noise_navigation_paths (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    destination_id              INTEGER NOT NULL
                                        REFERENCES noise_destinations(id) ON DELETE CASCADE,
    origin                      TEXT    NOT NULL,
    label                       TEXT    NOT NULL,
    is_active                   INTEGER NOT NULL DEFAULT 1,
    is_dead                     INTEGER NOT NULL DEFAULT 0,
    consecutive_failures_count  INTEGER NOT NULL DEFAULT 0
);
"""
# Sin CHECK en origin: admite valores dinámicos "VILLAGE_<data_id>".
# La validación de origin se hace en la capa de aplicación (_validate_origin).
# Spec noise-path-wizard.md §7.2 y §14 Paso 1.

_CREATE_IDX_NOISE_PATHS_DEST = """
CREATE INDEX IF NOT EXISTS idx_noise_paths_destination
    ON noise_navigation_paths(destination_id);
"""

_CREATE_NOISE_NAVIGATION_STEPS = """
CREATE TABLE IF NOT EXISTS noise_navigation_steps (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    path_id                     INTEGER NOT NULL
                                        REFERENCES noise_navigation_paths(id) ON DELETE CASCADE,
    step_order                  INTEGER NOT NULL,
    action                      TEXT    NOT NULL
                                        CHECK (action IN (
                                            'CLICK','WAIT_FOR_SELECTOR','SCROLL_TO','HOVER'
                                        )),
    selector                    TEXT    NOT NULL,
    value                       TEXT    NOT NULL DEFAULT '',
    delay_min_ms                INTEGER NOT NULL DEFAULT 500,
    delay_max_ms                INTEGER NOT NULL DEFAULT 900,
    expected_url_after_click    TEXT    DEFAULT NULL,
    UNIQUE (path_id, step_order)
);
"""

_CREATE_IDX_NOISE_STEPS_PATH = """
CREATE INDEX IF NOT EXISTS idx_noise_steps_path
    ON noise_navigation_steps(path_id, step_order);
"""

_CREATE_WORLD_NOISE_CONFIG = """
CREATE TABLE IF NOT EXISTS world_noise_config (
    world_id                         INTEGER PRIMARY KEY
                                             REFERENCES worlds(id) ON DELETE CASCADE,
    noise_enabled                    INTEGER NOT NULL DEFAULT 1,
    hardcore_total_req_per_hour_min  INTEGER NOT NULL DEFAULT 80,   -- deprecated: ver hardcore_interval_min_seconds
    hardcore_total_req_per_hour_max  INTEGER NOT NULL DEFAULT 150,  -- deprecated: ver hardcore_interval_max_seconds
    passive_total_req_per_hour_min   INTEGER NOT NULL DEFAULT 15,   -- deprecated: ver passive_interval_min_seconds
    passive_total_req_per_hour_max   INTEGER NOT NULL DEFAULT 40,   -- deprecated: ver passive_interval_max_seconds
    dwell_min_seconds                REAL    NOT NULL DEFAULT 2.0,
    dwell_max_seconds                REAL    NOT NULL DEFAULT 30.0,
    hardcore_interval_min_seconds    INTEGER DEFAULT NULL,
    hardcore_interval_max_seconds    INTEGER DEFAULT NULL,
    passive_interval_min_seconds     INTEGER DEFAULT NULL,
    passive_interval_max_seconds     INTEGER DEFAULT NULL
);
"""


# ---------------------------------------------------------------------------
# Migraciones incrementales (spec noise-path-wizard.md §14 Paso 1)
# ---------------------------------------------------------------------------

async def _migrate_noise_paths_add_is_dead_and_failures(
    conn: aiosqlite.Connection,
) -> None:
    """
    Migración M-NP01: recrear noise_navigation_paths eliminando el CHECK de origin
    y añadiendo consecutive_failures_count + is_dead.

    Estrategia (SQLite no soporta ALTER COLUMN ni DROP CONSTRAINT):
      1. Verificar si ya tiene las columnas nuevas (idempotente).
      2. Si faltan: procedimiento oficial SQLite de 12 pasos con foreign_keys=OFF:
         a. foreign_keys=OFF + SAVEPOINT
         b. CREATE nueva tabla con nombre temporal
         c. INSERT desde la vieja
         d. DROP vieja
         e. RENAME temporal → nombre definitivo
         f. Recrear índice
         g. PRAGMA foreign_key_check
         h. RELEASE SAVEPOINT + foreign_keys=ON

    Por qué NOT usar RENAME→DROP: SQLite ≥ 3.25 con legacy_alter_table=OFF
    reescribe automáticamente las FK de las tablas hijas al renombrar la tabla
    padre. Así noise_navigation_steps.path_id quedaría apuntando a
    "noise_navigation_paths_old" y al hacer DROP esa FK quedaría rota.
    El procedimiento oficial con foreign_keys=OFF evita completamente ese
    problema porque SQLite no reescribe nada si las FK están desactivadas.

    Referencia: https://www.sqlite.org/lang_altertable.html §7 "Making Other
    Kinds Of Table Schema Changes" (12 pasos).

    Seguridad de datos: los valores de origin existentes (DORF1, DORF2, MAP, ANY)
    son todos válidos en el nuevo esquema sin CHECK. No se pierde ningún dato.

    Spec noise-path-wizard.md §14 Paso 1b + EC-NP13.
    """
    # Comprobar si la tabla ya tiene las columnas nuevas (migración idempotente)
    cursor = await conn.execute("PRAGMA table_info(noise_navigation_paths)")
    columns = {row[1] for row in await cursor.fetchall()}

    needs_migration = "consecutive_failures_count" not in columns or "is_dead" not in columns

    if not needs_migration:
        return

    logger.info(
        "NoiseSQLiteAdapter: migrando noise_navigation_paths "
        "(añadir is_dead + consecutive_failures_count, eliminar CHECK de origin)"
    )

    # Procedimiento oficial SQLite de 12 pasos para cambiar esquema de tabla
    # cuando hay tablas hijas con FK. foreign_keys=OFF es IMPRESCINDIBLE para
    # que SQLite NO reescriba las FK de noise_navigation_steps al hacer RENAME.
    await conn.execute("PRAGMA foreign_keys=OFF")
    await conn.execute("SAVEPOINT m_np01")

    try:
        # 1. Crear la nueva tabla con nombre temporal (sin CHECK en origin,
        #    con is_dead y consecutive_failures_count)
        await conn.execute("""
            CREATE TABLE noise_navigation_paths_new (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                destination_id              INTEGER NOT NULL
                                                    REFERENCES noise_destinations(id) ON DELETE CASCADE,
                origin                      TEXT    NOT NULL,
                label                       TEXT    NOT NULL,
                is_active                   INTEGER NOT NULL DEFAULT 1,
                is_dead                     INTEGER NOT NULL DEFAULT 0,
                consecutive_failures_count  INTEGER NOT NULL DEFAULT 0
            )
        """)

        # 2. Copiar datos. consecutive_failures_count=0 para todos (era nueva columna).
        #    is_dead=0 para todos.
        await conn.execute("""
            INSERT INTO noise_navigation_paths_new
                   (id, destination_id, origin, label, is_active, is_dead, consecutive_failures_count)
            SELECT  id, destination_id, origin, label, is_active, 0, 0
              FROM  noise_navigation_paths
        """)

        # 3. Borrar la tabla vieja
        await conn.execute("DROP TABLE noise_navigation_paths")

        # 4. Renombrar la nueva al nombre definitivo.
        #    Con foreign_keys=OFF SQLite NO reescribe la FK de noise_navigation_steps,
        #    que ya apuntaba a "noise_navigation_paths" y sigue apuntando a ese nombre.
        await conn.execute(
            "ALTER TABLE noise_navigation_paths_new RENAME TO noise_navigation_paths"
        )

        # 5. Recrear el índice
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_noise_paths_destination
                ON noise_navigation_paths(destination_id)
        """)

        # 6. Verificar integridad de FK antes de confirmar
        await conn.execute("PRAGMA foreign_key_check")

        await conn.execute("RELEASE SAVEPOINT m_np01")

    except Exception:
        await conn.execute("ROLLBACK TO SAVEPOINT m_np01")
        await conn.execute("RELEASE SAVEPOINT m_np01")
        raise

    finally:
        # Restaurar foreign_keys=ON siempre, aunque haya habido excepción
        await conn.execute("PRAGMA foreign_keys=ON")

    await conn.commit()
    logger.info("NoiseSQLiteAdapter: migración M-NP01 completada")


async def _migrate_noise_steps_add_expected_url(
    conn: aiosqlite.Connection,
) -> None:
    """
    Migración M-NP02: añadir columna expected_url_after_click a noise_navigation_steps.

    Idempotente: si la columna ya existe, el ALTER TABLE falla silenciosamente.
    Los pasos existentes quedan con NULL (sin verificación de URL) — EC-NP12.

    Spec noise-path-wizard.md §14 Paso 1a + §7.3.
    """
    try:
        await conn.execute(
            "ALTER TABLE noise_navigation_steps"
            " ADD COLUMN expected_url_after_click TEXT DEFAULT NULL"
        )
        await conn.commit()
        logger.info("NoiseSQLiteAdapter: migración M-NP02 completada (expected_url_after_click añadida)")
    except aiosqlite.OperationalError:
        pass  # columna ya existe — migración ya corrió antes


async def _migrate_noise_config_add_interval_fields(
    conn: aiosqlite.Connection,
) -> None:
    """
    Migración M-FW01: añadir cuatro columnas de intervalo (en segundos) a world_noise_config.

    Los campos *_req_per_hour_* se conservan como deprecated para compatibilidad hacia atrás.
    Los nuevos campos se añaden con DEFAULT NULL; la migración lazy en get_or_create_noise_config
    los inicializa con los defaults de NoiseConfig si son NULL.

    Idempotente: ALTER TABLE falla silenciosamente si la columna ya existe.

    Spec noise-frequency-and-destination-weight.md §7.2, §14 Paso 1.
    """
    for col in [
        "hardcore_interval_min_seconds",
        "hardcore_interval_max_seconds",
        "passive_interval_min_seconds",
        "passive_interval_max_seconds",
    ]:
        try:
            await conn.execute(
                f"ALTER TABLE world_noise_config ADD COLUMN {col} INTEGER DEFAULT NULL"
            )
        except aiosqlite.OperationalError:
            pass  # columna ya existe — migración idempotente

    await conn.commit()
    logger.debug("NoiseSQLiteAdapter: migración M-FW01 asegurada (interval fields)")


async def _migrate_noise_destinations_add_template_id(
    conn: aiosqlite.Connection,
) -> None:
    """
    Migración M-RT01: añadir columna template_id a noise_destinations.

    La columna es FK nullable a route_templates.id con ON DELETE SET NULL:
    si la plantilla origen se borra, los destinos clonados quedan intactos
    con template_id=NULL (RN-RT06).

    Idempotente: ALTER TABLE falla silenciosamente si la columna ya existe.

    Spec route-templates-developer-portal.md §7.3, §14 Paso 4.
    """
    try:
        await conn.execute(
            "ALTER TABLE noise_destinations"
            " ADD COLUMN template_id INTEGER DEFAULT NULL"
            " REFERENCES route_templates(id) ON DELETE SET NULL"
        )
        await conn.commit()
        logger.info(
            "NoiseSQLiteAdapter: migración M-RT01 completada (template_id añadida a noise_destinations)"
        )
    except aiosqlite.OperationalError:
        pass  # columna ya existe — migración idempotente

    # Crear índice independientemente (CREATE INDEX IF NOT EXISTS es idempotente)
    try:
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_noise_destinations_template"
            " ON noise_destinations(template_id)"
        )
        await conn.commit()
    except Exception:
        pass  # tolerar si la columna aún no existe en instancias muy antiguas


async def _migrate_noise_destinations_tighten_weight_check(
    conn: aiosqlite.Connection,
) -> None:
    """
    Migración M-FW04: endurecer el CHECK de frequency_weight en noise_destinations
    de `> 0` a `>= 0.1 AND <= 5.0` (requisito guardian RN-FW07).

    SQLite no soporta ALTER COLUMN ni DROP CONSTRAINT, así que se usa el
    procedimiento oficial de 12 pasos con foreign_keys=OFF.

    Idempotente: si el CHECK ya es `>= 0.1 AND <= 5.0`, no toca nada.

    Spec noise-frequency-and-destination-weight.md §7.3, RN-FW07 (GUARDIAN).
    """
    # Leer el DDL actual de noise_destinations
    rows = await conn.execute_fetchall(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='noise_destinations'",
    )
    if not rows:
        # La tabla no existe aún; ensure_tables la creará con el CHECK correcto
        return

    current_sql: str = rows[0]["sql"] or ""

    # Si ya tiene el CHECK endurecido, nada que hacer
    if "frequency_weight >= 0.1" in current_sql or "frequency_weight >= 0.10" in current_sql:
        return

    logger.info(
        "NoiseSQLiteAdapter: migrando noise_destinations — endureciendo CHECK de frequency_weight"
    )

    await conn.execute("PRAGMA foreign_keys=OFF")
    await conn.execute("SAVEPOINT m_fw04")

    try:
        await conn.execute("""
            CREATE TABLE noise_destinations_new (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id                  INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
                url_pattern               TEXT    NOT NULL,
                label                     TEXT    NOT NULL,
                category                  TEXT    NOT NULL
                                                  CHECK (category IN (
                                                      'MAP','OASIS_INFO','PLAYER_PROFILE',
                                                      'MESSAGES','REPORTS','BUILDING_VIEW','OTHER'
                                                  )),
                frequency_weight          REAL    NOT NULL DEFAULT 1.0
                                                  CHECK (frequency_weight >= 0.1 AND frequency_weight <= 5.0),
                is_safe                   INTEGER NOT NULL DEFAULT 1,
                is_dead                   INTEGER NOT NULL DEFAULT 0,
                consecutive_failures_count INTEGER NOT NULL DEFAULT 0,
                created_at                TEXT    NOT NULL,
                last_used_at              TEXT,
                UNIQUE (world_id, url_pattern)
            )
        """)

        # Copiar datos, clampando el peso al nuevo rango [0.1, 5.0]
        await conn.execute("""
            INSERT INTO noise_destinations_new
                   (id, world_id, url_pattern, label, category, frequency_weight,
                    is_safe, is_dead, consecutive_failures_count, created_at, last_used_at)
            SELECT  id, world_id, url_pattern, label, category,
                    MAX(0.1, MIN(5.0, frequency_weight)),
                    is_safe, is_dead, consecutive_failures_count, created_at, last_used_at
              FROM  noise_destinations
        """)

        await conn.execute("DROP TABLE noise_destinations")
        await conn.execute(
            "ALTER TABLE noise_destinations_new RENAME TO noise_destinations"
        )

        # Recrear índice
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_noise_destinations_world
                ON noise_destinations(world_id, is_dead, is_safe)
        """)

        await conn.execute("PRAGMA foreign_key_check")
        await conn.execute("RELEASE SAVEPOINT m_fw04")

    except Exception:
        await conn.execute("ROLLBACK TO SAVEPOINT m_fw04")
        await conn.execute("RELEASE SAVEPOINT m_fw04")
        raise

    finally:
        await conn.execute("PRAGMA foreign_keys=ON")

    await conn.commit()
    logger.info("NoiseSQLiteAdapter: migración M-FW04 completada (CHECK frequency_weight endurecido)")


async def _repair_noise_steps_broken_fk(
    conn: aiosqlite.Connection,
) -> None:
    """
    Migración M-NP03: auto-reparación de FK rota en noise_navigation_steps.

    Problema: la migración M-NP01 original (pre-fix) usaba RENAME→DROP y SQLite
    ≥ 3.25 con legacy_alter_table=OFF reescribió la FK de noise_navigation_steps
    de REFERENCES noise_navigation_paths(id) a
    REFERENCES "noise_navigation_paths_old"(id). Al eliminar la tabla _old, la FK
    quedó apuntando a una tabla inexistente, causando error 500 en create_path
    con foreign_keys=ON.

    Esta migración:
      1. Lee el SQL de CREATE TABLE de noise_navigation_steps en sqlite_master.
      2. Si detecta "noise_navigation_paths_old" en el SQL (FK rota), recrea la
         tabla con la FK correcta a noise_navigation_paths(id) ON DELETE CASCADE.
      3. Preserva todos los datos existentes y la columna expected_url_after_click.
      4. Recrea el índice y la restricción UNIQUE (path_id, step_order).
      5. Es idempotente: si la FK ya apunta a noise_navigation_paths, no toca nada.
      6. Usa foreign_keys=OFF para que la recreación no falle por FK pendientes
         durante el proceso, y PRAGMA foreign_key_check al final para verificar.

    Referencia: https://www.sqlite.org/lang_altertable.html §7 (12 pasos).
    """
    # Leer el DDL actual de noise_navigation_steps
    rows = await conn.execute_fetchall(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='noise_navigation_steps'",
    )
    if not rows:
        # La tabla no existe aún; nada que reparar (ensure_tables la creará correctamente)
        return

    current_sql: str = rows[0]["sql"] or ""

    # Detectar si la FK está rota: apunta a noise_navigation_paths_old o a una
    # referencia que no sea la tabla correcta
    if "noise_navigation_paths_old" not in current_sql:
        # FK ya correcta — migración idempotente, no hacer nada
        return

    logger.warning(
        "NoiseSQLiteAdapter: FK rota detectada en noise_navigation_steps "
        "(apunta a noise_navigation_paths_old). Iniciando auto-reparación M-NP03."
    )

    await conn.execute("PRAGMA foreign_keys=OFF")
    await conn.execute("SAVEPOINT m_np03")

    try:
        # Crear tabla de reparación con la FK correcta y todas las columnas
        # actuales (incluyendo expected_url_after_click de M-NP02)
        await conn.execute("""
            CREATE TABLE noise_navigation_steps_repair (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                path_id                     INTEGER NOT NULL
                                                    REFERENCES noise_navigation_paths(id) ON DELETE CASCADE,
                step_order                  INTEGER NOT NULL,
                action                      TEXT    NOT NULL
                                                    CHECK (action IN (
                                                        'CLICK','WAIT_FOR_SELECTOR','SCROLL_TO','HOVER'
                                                    )),
                selector                    TEXT    NOT NULL,
                value                       TEXT    NOT NULL DEFAULT '',
                delay_min_ms                INTEGER NOT NULL DEFAULT 500,
                delay_max_ms                INTEGER NOT NULL DEFAULT 900,
                expected_url_after_click    TEXT    DEFAULT NULL,
                UNIQUE (path_id, step_order)
            )
        """)

        # Copiar todos los pasos existentes (si los hay)
        await conn.execute("""
            INSERT INTO noise_navigation_steps_repair
                   (id, path_id, step_order, action, selector, value,
                    delay_min_ms, delay_max_ms, expected_url_after_click)
            SELECT  id, path_id, step_order, action, selector, value,
                    delay_min_ms, delay_max_ms, expected_url_after_click
              FROM  noise_navigation_steps
        """)

        # Eliminar la tabla rota
        await conn.execute("DROP TABLE noise_navigation_steps")

        # Renombrar la tabla de reparación al nombre definitivo
        await conn.execute(
            "ALTER TABLE noise_navigation_steps_repair RENAME TO noise_navigation_steps"
        )

        # Recrear el índice
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_noise_steps_path
                ON noise_navigation_steps(path_id, step_order)
        """)

        # Verificar integridad de FK antes de confirmar
        await conn.execute("PRAGMA foreign_key_check")

        await conn.execute("RELEASE SAVEPOINT m_np03")

    except Exception:
        await conn.execute("ROLLBACK TO SAVEPOINT m_np03")
        await conn.execute("RELEASE SAVEPOINT m_np03")
        raise

    finally:
        await conn.execute("PRAGMA foreign_keys=ON")

    await conn.commit()
    logger.info(
        "NoiseSQLiteAdapter: auto-reparación M-NP03 completada — FK de "
        "noise_navigation_steps ahora apunta correctamente a noise_navigation_paths."
    )


# ---------------------------------------------------------------------------
# Validación de origin (spec noise-path-wizard.md §7.2 y §10)
# ---------------------------------------------------------------------------

from core.entities.noise import NavigationOrigin as _NavigationOrigin  # noqa: E402

_VALID_GENERIC_ORIGINS: frozenset[str] = frozenset(
    o.value for o in _NavigationOrigin
)


def _validate_origin(origin: str, village_data_ids: list[int]) -> None:
    """
    Valida que origin sea:
      - Un valor del enum NavigationOrigin, O
      - Una cadena "VILLAGE_<data_id>" donde data_id está en village_data_ids.

    Lanza ValueError con mensaje descriptivo si no es válido.
    Spec noise-path-wizard.md §7.2, RN-NP02, EC-NP05.
    """
    if origin in _VALID_GENERIC_ORIGINS:
        return
    if origin.startswith("VILLAGE_"):
        suffix = origin[8:]
        try:
            data_id = int(suffix)
        except ValueError:
            raise ValueError(
                f"origin '{origin}' no es un origen válido: "
                f"el sufijo '{suffix}' no es un entero."
            )
        if data_id not in village_data_ids:
            raise ValueError(
                f"Aldea con data_id={data_id} no encontrada para este mundo."
            )
        return
    raise ValueError(
        f"origin '{origin}' no es un valor válido. "
        f"Valores aceptados: {sorted(_VALID_GENERIC_ORIGINS)} "
        f"o 'VILLAGE_<data_id>'."
    )


# ---------------------------------------------------------------------------
# Validación de URL (RN-HS23 endurecida por guardian)
# ---------------------------------------------------------------------------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f]")
_DANGEROUS_SCHEMES = {"javascript", "data", "file", "vbscript", "about"}


def _validate_url_pattern(url_pattern: str, world_server: str) -> None:
    """
    Valida url_pattern según RN-HS23 (guardian v2.2.1):

    1. Sin caracteres de control (\\x00-\\x1f).
    2. Sin protocol-relative (//...).
    3. Si es absoluta (contiene ://): solo http/https; dominio debe pertenecer al world_server.
    4. Si es relativa: debe comenzar por '/'.
    5. Schemes peligrosos: javascript:, data:, file:, vbscript:, about: rechazados.

    Lanza ValueError con mensaje descriptivo en caso de violación.
    """
    if not url_pattern or not url_pattern.strip():
        raise ValueError("url_pattern no puede estar vacío.")

    # 1. Sin caracteres de control
    if _CONTROL_CHAR_RE.search(url_pattern):
        raise ValueError(
            "url_pattern contiene caracteres de control no permitidos."
        )

    # 2. Sin protocol-relative
    if url_pattern.startswith("//"):
        raise ValueError(
            "url_pattern no puede ser una URL protocol-relative (//...). "
            "Usa http:// o https:// explícito, o una ruta relativa que comience por '/'."
        )

    # 3. Detectar scheme peligroso antes del parseo (p. ej. "javascript:alert(1)")
    lower = url_pattern.lower().strip()
    for scheme in _DANGEROUS_SCHEMES:
        if lower.startswith(scheme + ":"):
            raise ValueError(
                f"url_pattern con scheme '{scheme}:' no está permitido. "
                "Solo se admiten http://, https:// o rutas relativas."
            )

    # 4. Absoluta vs relativa
    if "://" in url_pattern:
        parsed = urlparse(url_pattern)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"url_pattern con scheme '{parsed.scheme}' no está permitido. "
                "Solo http y https son válidos para URLs absolutas."
            )
        # Validar que el dominio pertenece al world_server
        server_parsed = urlparse(world_server if "://" in world_server else f"https://{world_server}")
        server_host = server_parsed.hostname or ""
        url_host = parsed.hostname or ""
        if not url_host or not _same_or_subdomain(url_host, server_host):
            raise ValueError(
                f"url_pattern '{url_pattern}' no pertenece al dominio del servidor "
                f"'{server_host}'. Solo se permiten URLs del mismo servidor."
            )
    else:
        # Relativa: debe comenzar con '/'
        if not url_pattern.startswith("/"):
            raise ValueError(
                "url_pattern relativo debe comenzar por '/'. "
                "Ejemplo: '/karte.php', '/nachrichten.php'."
            )


def _same_or_subdomain(host: str, server_host: str) -> bool:
    """True si host == server_host o host es subdominio de server_host."""
    host = host.lower()
    server_host = server_host.lower()
    return host == server_host or host.endswith("." + server_host)


# ---------------------------------------------------------------------------
# Helpers de conversión fila → entidad
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_destination(row: aiosqlite.Row) -> NoiseDestination:
    row_dict = dict(row)
    # Retrocompat: columna puede llamarse 'category_slug' (post-M-CAT04) o 'category' (pre-migración)
    category_slug = row_dict.get("category_slug") or row_dict.get("category") or "uncategorized"
    return NoiseDestination(
        id=row_dict["id"],
        world_id=row_dict["world_id"],
        url_pattern=row_dict["url_pattern"],
        label=row_dict["label"],
        category_slug=category_slug,
        frequency_weight=row_dict["frequency_weight"],
        is_safe=bool(row_dict["is_safe"]),
        is_dead=bool(row_dict["is_dead"]),
        consecutive_failures_count=row_dict["consecutive_failures_count"],
        created_at=datetime.fromisoformat(row_dict["created_at"]) if row_dict["created_at"] else None,
        last_used_at=datetime.fromisoformat(row_dict["last_used_at"]) if row_dict["last_used_at"] else None,
        template_id=row_dict.get("template_id"),  # M-RT01: None en BDs antiguas antes de la migración
    )


def _row_to_step(row: aiosqlite.Row) -> NavigationStep:
    # Guard para expected_url_after_click: la columna puede no existir en BD antiguas.
    # dict(row) o row[key] lanza IndexError si la columna no existe; usamos .get() con fallback.
    row_dict = dict(row)
    return NavigationStep(
        id=row_dict["id"],
        path_id=row_dict["path_id"],
        step_order=row_dict["step_order"],
        action=NoiseAction(row_dict["action"]),
        selector=row_dict["selector"],
        value=row_dict["value"],
        delay_min_ms=row_dict["delay_min_ms"],
        delay_max_ms=row_dict["delay_max_ms"],
        expected_url_after_click=row_dict.get("expected_url_after_click"),  # None si la col no existe
    )


def _row_to_path(row: aiosqlite.Row, steps: list[NavigationStep]) -> NavigationPath:
    # Guard de compatibilidad: origin se almacena como TEXT en BD.
    # Puede ser un valor del enum NavigationOrigin (legacy) o "VILLAGE_<data_id>" (nuevo).
    # La entidad NavigationPath.origin es str desde noise-path-wizard.md §7.5.
    row_dict = dict(row)
    raw_origin: str = row_dict["origin"]
    try:
        origin_val: str = NavigationOrigin(raw_origin).value
    except ValueError:
        origin_val = raw_origin  # p.ej. "VILLAGE_12345"
    return NavigationPath(
        id=row_dict["id"],
        destination_id=row_dict["destination_id"],
        origin=origin_val,
        label=row_dict["label"],
        is_active=bool(row_dict["is_active"]),
        is_dead=bool(row_dict.get("is_dead", 0)),
        consecutive_failures_count=row_dict.get("consecutive_failures_count", 0),
        steps=steps,
    )


def _row_to_config(row: aiosqlite.Row) -> NoiseConfig:
    """
    Convierte una fila de world_noise_config a NoiseConfig (v2 — campos interval).
    Los campos deprecated *_req_per_hour_* no se leen.

    Spec noise-frequency-and-destination-weight.md §7.1, §9.1.
    """
    row_dict = dict(row)
    defaults = NoiseConfig(world_id=row_dict["world_id"])

    hc_min = row_dict.get("hardcore_interval_min_seconds")
    hc_max = row_dict.get("hardcore_interval_max_seconds")
    pa_min = row_dict.get("passive_interval_min_seconds")
    pa_max = row_dict.get("passive_interval_max_seconds")

    return NoiseConfig(
        world_id=row_dict["world_id"],
        noise_enabled=bool(row_dict["noise_enabled"]),
        hardcore_interval_min_seconds=hc_min if hc_min is not None else defaults.hardcore_interval_min_seconds,
        hardcore_interval_max_seconds=hc_max if hc_max is not None else defaults.hardcore_interval_max_seconds,
        passive_interval_min_seconds=pa_min if pa_min is not None else defaults.passive_interval_min_seconds,
        passive_interval_max_seconds=pa_max if pa_max is not None else defaults.passive_interval_max_seconds,
        dwell_min_seconds=row_dict["dwell_min_seconds"],
        dwell_max_seconds=row_dict["dwell_max_seconds"],
    )


async def _migrate_noise_destinations_free_category(
    conn: aiosqlite.Connection,
) -> None:
    """
    M-ND02: Elimina el CHECK constraint de category en noise_destinations,
    convirtiendo category en texto libre (≤ 50 chars validados en la entidad).

    Motivación: cuando se clona una RouteTemplate con categoría libre
    (p.ej. "Estadísticas") al mundo, create_destination llama con esa categoría
    como str. El CHECK IN (...7 valores...) rechaza cualquier valor fuera del
    enum original y lanza IntegrityError 500. La solución es TEXT NOT NULL sin CHECK.

    Técnica: reconstrucción de tabla (SQLite no permite DROP CONSTRAINT).
    Preserva: id, world_id, url_pattern, label, category, frequency_weight,
              is_safe, is_dead, consecutive_failures_count, created_at,
              last_used_at, template_id (M-RT01), UNIQUE(world_id, url_pattern),
              FK worlds ON DELETE CASCADE, FK route_templates ON DELETE SET NULL.
    No toca noise_navigation_paths (su FK destination_id apunta al mismo nombre
    de tabla; SQLite la respeta tras el RENAME sin necesidad de recrearla).

    Idempotente: detecta si el CHECK de category sigue presente en sqlite_master.
    """
    rows = await conn.execute_fetchall(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='noise_destinations'",
    )
    if not rows:
        return  # tabla no existe aún — no-op

    current_sql: str = rows[0]["sql"] or ""
    if "CHECK (category IN" not in current_sql and "CHECK(category IN" not in current_sql:
        return  # ya sin CHECK de category — idempotente

    logger.info(
        "NoiseSQLiteAdapter: migrando noise_destinations — eliminando CHECK de category (M-ND02)"
    )

    await conn.execute("PRAGMA foreign_keys=OFF")
    await conn.execute("SAVEPOINT m_nd02")

    try:
        # Detectar si la columna template_id ya existe (M-RT01 puede haberse aplicado antes)
        pragma_rows = await conn.execute_fetchall(
            "PRAGMA table_info(noise_destinations)"
        )
        col_names = [r["name"] for r in pragma_rows]
        has_template_id = "template_id" in col_names

        # DDL de la tabla nueva sin CHECK de category
        template_id_col = (
            ",\n    template_id               INTEGER DEFAULT NULL"
            " REFERENCES route_templates(id) ON DELETE SET NULL"
            if has_template_id else ""
        )

        await conn.execute(f"""
            CREATE TABLE noise_destinations_nd02 (
                id                         INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id                   INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
                url_pattern                TEXT    NOT NULL,
                label                      TEXT    NOT NULL,
                category                   TEXT    NOT NULL,
                frequency_weight           REAL    NOT NULL DEFAULT 1.0
                                                   CHECK (frequency_weight >= 0.1 AND frequency_weight <= 5.0),
                is_safe                    INTEGER NOT NULL DEFAULT 1,
                is_dead                    INTEGER NOT NULL DEFAULT 0,
                consecutive_failures_count INTEGER NOT NULL DEFAULT 0,
                created_at                 TEXT    NOT NULL,
                last_used_at               TEXT{template_id_col},
                UNIQUE (world_id, url_pattern)
            )
        """)

        # Copiar datos
        if has_template_id:
            await conn.execute("""
                INSERT INTO noise_destinations_nd02
                       (id, world_id, url_pattern, label, category, frequency_weight,
                        is_safe, is_dead, consecutive_failures_count,
                        created_at, last_used_at, template_id)
                SELECT  id, world_id, url_pattern, label, category, frequency_weight,
                        is_safe, is_dead, consecutive_failures_count,
                        created_at, last_used_at, template_id
                  FROM  noise_destinations
            """)
        else:
            await conn.execute("""
                INSERT INTO noise_destinations_nd02
                       (id, world_id, url_pattern, label, category, frequency_weight,
                        is_safe, is_dead, consecutive_failures_count,
                        created_at, last_used_at)
                SELECT  id, world_id, url_pattern, label, category, frequency_weight,
                        is_safe, is_dead, consecutive_failures_count,
                        created_at, last_used_at
                  FROM  noise_destinations
            """)

        await conn.execute("DROP TABLE noise_destinations")
        await conn.execute(
            "ALTER TABLE noise_destinations_nd02 RENAME TO noise_destinations"
        )

        # Recrear índices
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_noise_destinations_world
                ON noise_destinations(world_id, is_dead, is_safe)
        """)
        if has_template_id:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_noise_destinations_template
                    ON noise_destinations(template_id)
            """)

        await conn.execute("PRAGMA foreign_key_check")
        await conn.execute("RELEASE SAVEPOINT m_nd02")

    except Exception:
        await conn.execute("ROLLBACK TO SAVEPOINT m_nd02")
        await conn.execute("RELEASE SAVEPOINT m_nd02")
        raise

    finally:
        await conn.execute("PRAGMA foreign_keys=ON")

    await conn.commit()
    logger.info(
        "NoiseSQLiteAdapter: migración M-ND02 completada (CHECK category eliminado de noise_destinations)"
    )


# ---------------------------------------------------------------------------
# Migración M-CAT04 — eliminar CHECK de category en noise_destinations
# ---------------------------------------------------------------------------

async def _migrate_noise_destinations_remove_check(
    conn: aiosqlite.Connection,
) -> None:
    """
    Migración M-CAT04: recrear noise_destinations sin el CHECK de 7 valores en category,
    renombrando la columna 'category' a 'category_slug' y mapeando todos los valores
    existentes a 'uncategorized'.

    Idempotente: si la columna ya se llama 'category_slug', omite la migración.
    Estrategia: procedimiento oficial SQLite de 12 pasos con foreign_keys=OFF.

    IMPORTANTE: ejecutar ANTES de _migrate_noise_destinations_tighten_weight_check
    y DESPUÉS de que la tabla exista (se crea antes con _CREATE_NOISE_DESTINATIONS).

    Spec route-categories-dynamic.md §7.4 (M-CAT04) y §7.3.
    """
    # Verificar si la tabla existe
    rows = await conn.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='noise_destinations'",
    )
    if not rows:
        # Tabla no existe; ensure_tables la creará con el DDL correcto
        return

    # Comprobar si ya fue migrada: verificar si columna 'category_slug' existe
    cursor = await conn.execute("PRAGMA table_info(noise_destinations)")
    columns = {row[1] for row in await cursor.fetchall()}

    if "category_slug" in columns:
        # Ya migrada — idempotente
        return

    if "category" not in columns:
        # Columna category tampoco existe (tabla creada con DDL nuevo) — nada que hacer
        return

    logger.info(
        "NoiseSQLiteAdapter: migrando noise_destinations "
        "(eliminar CHECK de category, renombrar a category_slug)"
    )

    # Leer si template_id ya existe (para preservarla en la copia)
    has_template_id = "template_id" in columns

    await conn.execute("PRAGMA foreign_keys=OFF")
    await conn.execute("SAVEPOINT m_cat04")

    try:
        # Construir DDL de la tabla nueva (con o sin template_id)
        template_id_col = (
            ",\n    template_id               INTEGER DEFAULT NULL"
            " REFERENCES route_templates(id) ON DELETE SET NULL"
            if has_template_id else ""
        )
        await conn.execute(f"""
            CREATE TABLE noise_destinations_new (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id                  INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
                url_pattern               TEXT    NOT NULL,
                label                     TEXT    NOT NULL,
                category_slug             TEXT    NOT NULL DEFAULT 'uncategorized',
                frequency_weight          REAL    NOT NULL DEFAULT 1.0
                                                  CHECK (frequency_weight >= 0.1 AND frequency_weight <= 5.0),
                is_safe                   INTEGER NOT NULL DEFAULT 1,
                is_dead                   INTEGER NOT NULL DEFAULT 0,
                consecutive_failures_count INTEGER NOT NULL DEFAULT 0,
                created_at                TEXT    NOT NULL,
                last_used_at              TEXT{template_id_col},
                UNIQUE (world_id, url_pattern)
            )
        """)

        if has_template_id:
            await conn.execute("""
                INSERT INTO noise_destinations_new
                    (id, world_id, url_pattern, label, category_slug, frequency_weight,
                     is_safe, is_dead, consecutive_failures_count, created_at, last_used_at, template_id)
                SELECT id, world_id, url_pattern, label, 'uncategorized',
                       MAX(0.1, MIN(5.0, frequency_weight)),
                       is_safe, is_dead, consecutive_failures_count, created_at, last_used_at, template_id
                  FROM noise_destinations
            """)
        else:
            await conn.execute("""
                INSERT INTO noise_destinations_new
                    (id, world_id, url_pattern, label, category_slug, frequency_weight,
                     is_safe, is_dead, consecutive_failures_count, created_at, last_used_at)
                SELECT id, world_id, url_pattern, label, 'uncategorized',
                       MAX(0.1, MIN(5.0, frequency_weight)),
                       is_safe, is_dead, consecutive_failures_count, created_at, last_used_at
                  FROM noise_destinations
            """)

        await conn.execute("DROP TABLE noise_destinations")
        await conn.execute(
            "ALTER TABLE noise_destinations_new RENAME TO noise_destinations"
        )

        # Recrear índices
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_noise_destinations_world
                ON noise_destinations(world_id, is_dead, is_safe)
        """)
        if has_template_id:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_noise_destinations_template
                    ON noise_destinations(template_id)
            """)

        await conn.execute("PRAGMA foreign_key_check")
        await conn.execute("RELEASE SAVEPOINT m_cat04")

    except Exception:
        await conn.execute("ROLLBACK TO SAVEPOINT m_cat04")
        await conn.execute("RELEASE SAVEPOINT m_cat04")
        raise

    finally:
        await conn.execute("PRAGMA foreign_keys=ON")

    await conn.commit()
    logger.info("NoiseSQLiteAdapter: migración M-CAT04 completada")


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------

class NoiseSQLiteAdapter(NoiseDbPort):
    """
    Implementa NoiseDbPort con aiosqlite.
    Comparte la misma conexión SQLite (WAL) que el resto de adaptadores.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def ensure_tables(self) -> None:
        """
        Crea las tablas de ruido si no existen y ejecuta las migraciones incrementales.
        Llamar en el lifespan de la app DESPUÉS de AccountSQLiteAdapter.ensure_tables().

        Migraciones (idempotentes):
          M-NP01: añade is_dead + consecutive_failures_count a noise_navigation_paths,
                  elimina CHECK de origin (spec noise-path-wizard.md §14 Paso 1b).
                  Usa el procedimiento oficial SQLite de 12 pasos con foreign_keys=OFF
                  para NO corromper la FK de noise_navigation_steps.
          M-NP02: añade expected_url_after_click a noise_navigation_steps
                  (spec noise-path-wizard.md §14 Paso 1a).
          M-NP03: auto-reparación de FK rota en noise_navigation_steps.
                  Detecta y corrige el daño causado por la versión pre-fix de M-NP01
                  (REFERENCES noise_navigation_paths_old → REFERENCES noise_navigation_paths).
                  Idempotente y segura si la FK ya está bien.
        """
        # PRAGMA foreign_keys = ON: necesario para que las FK ON DELETE SET NULL y
        # ON DELETE CASCADE actúen en SQLite (por defecto están desactivadas).
        # Se activa aquí porque NoiseSQLiteAdapter es el dueño de noise_destinations,
        # que tiene FKs hacia route_templates (template_id ON DELETE SET NULL).
        # Spec route-templates-developer-portal.md §v2.13 — riesgo #6.
        await self._conn.execute("PRAGMA foreign_keys = ON")

        # M-CAT04: migrar noise_destinations (eliminar CHECK de category, renombrar a
        # category_slug). DEBE ejecutarse ANTES de crear la tabla con el DDL nuevo,
        # por si la tabla ya existe con el esquema viejo (con CHECK enum).
        await _migrate_noise_destinations_remove_check(self._conn)

        # Crear tablas nuevas / instalaciones nuevas
        await self._conn.execute(_CREATE_NOISE_DESTINATIONS)
        await self._conn.execute(_CREATE_IDX_NOISE_DESTINATIONS_WORLD)
        await self._conn.execute(_CREATE_NOISE_NAVIGATION_PATHS)
        await self._conn.execute(_CREATE_IDX_NOISE_PATHS_DEST)
        await self._conn.execute(_CREATE_NOISE_NAVIGATION_STEPS)
        await self._conn.execute(_CREATE_IDX_NOISE_STEPS_PATH)
        await self._conn.execute(_CREATE_WORLD_NOISE_CONFIG)
        await self._conn.commit()

        # Migraciones incrementales para instalaciones existentes
        await _migrate_noise_paths_add_is_dead_and_failures(self._conn)
        await _migrate_noise_steps_add_expected_url(self._conn)
        # M-NP03: auto-reparación de FK rota (debe correr después de M-NP01 y M-NP02)
        await _repair_noise_steps_broken_fk(self._conn)
        # M-FW01: añadir campos de intervalo a world_noise_config
        await _migrate_noise_config_add_interval_fields(self._conn)
        # M-FW04: endurecer CHECK de frequency_weight en noise_destinations
        # (ya no aplica: M-CAT04 recrea la tabla con el CHECK correcto directamente;
        # esta migración es idempotente si la tabla ya tiene el CHECK endurecido)
        await _migrate_noise_destinations_tighten_weight_check(self._conn)
        # NOTA (merge A+B): la migración de "categoría libre" de B (M-ND02) se sustituye
        # por M-CAT04 (_migrate_noise_destinations_remove_check), que además renombra
        # category → category_slug. Por eso aquí ya no se llama a M-ND02.

        logger.debug("NoiseSQLiteAdapter: tablas y migraciones aseguradas (incl. M-CAT04)")

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    async def _get_world_server(self, world_id: int) -> str:
        """Lee el campo server del mundo. Lanza ValueError si el mundo no existe."""
        rows = await self._conn.execute_fetchall(
            "SELECT server FROM worlds WHERE id = ?",
            (world_id,),
        )
        if not rows:
            raise ValueError(f"Mundo {world_id} no encontrado.")
        return rows[0]["server"]

    async def _fetch_steps_for_path(self, path_id: int) -> list[NavigationStep]:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, path_id, step_order, action, selector, value,
                   delay_min_ms, delay_max_ms,
                   expected_url_after_click
              FROM noise_navigation_steps
             WHERE path_id = ?
             ORDER BY step_order ASC
            """,
            (path_id,),
        )
        return [_row_to_step(r) for r in rows]

    # ------------------------------------------------------------------
    # Configuración de ruido
    # ------------------------------------------------------------------

    async def get_or_create_noise_config(self, world_id: int) -> NoiseConfig:
        """
        Lee (o crea con defaults) la configuración de ruido del mundo.

        Migración lazy (EC-FW01, §9.1): si los campos *_interval_*_seconds son NULL
        (BD antigua), los inicializa con los defaults de NoiseConfig y los persiste.

        Spec noise-frequency-and-destination-weight.md §9.1.
        """
        rows = await self._conn.execute_fetchall(
            """
            SELECT world_id, noise_enabled,
                   dwell_min_seconds, dwell_max_seconds,
                   hardcore_interval_min_seconds, hardcore_interval_max_seconds,
                   passive_interval_min_seconds,  passive_interval_max_seconds
              FROM world_noise_config
             WHERE world_id = ?
            """,
            (world_id,),
        )
        if rows:
            row = rows[0]
            row_dict = dict(row)

            hc_min = row_dict.get("hardcore_interval_min_seconds")
            hc_max = row_dict.get("hardcore_interval_max_seconds")
            pa_min = row_dict.get("passive_interval_min_seconds")
            pa_max = row_dict.get("passive_interval_max_seconds")

            # Migración lazy: si algún campo es NULL, inicializar con defaults y persistir
            if any(v is None for v in [hc_min, hc_max, pa_min, pa_max]):
                defaults = NoiseConfig(world_id=world_id)
                hc_min = hc_min if hc_min is not None else defaults.hardcore_interval_min_seconds
                hc_max = hc_max if hc_max is not None else defaults.hardcore_interval_max_seconds
                pa_min = pa_min if pa_min is not None else defaults.passive_interval_min_seconds
                pa_max = pa_max if pa_max is not None else defaults.passive_interval_max_seconds
                await self._conn.execute(
                    """
                    UPDATE world_noise_config
                       SET hardcore_interval_min_seconds = ?,
                           hardcore_interval_max_seconds = ?,
                           passive_interval_min_seconds  = ?,
                           passive_interval_max_seconds  = ?
                     WHERE world_id = ?
                    """,
                    (hc_min, hc_max, pa_min, pa_max, world_id),
                )
                await self._conn.commit()

            return NoiseConfig(
                world_id=world_id,
                noise_enabled=bool(row_dict["noise_enabled"]),
                hardcore_interval_min_seconds=hc_min,
                hardcore_interval_max_seconds=hc_max,
                passive_interval_min_seconds=pa_min,
                passive_interval_max_seconds=pa_max,
                dwell_min_seconds=row_dict["dwell_min_seconds"],
                dwell_max_seconds=row_dict["dwell_max_seconds"],
            )

        # Nueva instalación: crear con todos los defaults
        config = NoiseConfig(world_id=world_id)
        await self._conn.execute(
            """
            INSERT INTO world_noise_config
              (world_id, noise_enabled,
               hardcore_interval_min_seconds, hardcore_interval_max_seconds,
               passive_interval_min_seconds,  passive_interval_max_seconds,
               dwell_min_seconds, dwell_max_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                world_id,
                int(config.noise_enabled),
                config.hardcore_interval_min_seconds,
                config.hardcore_interval_max_seconds,
                config.passive_interval_min_seconds,
                config.passive_interval_max_seconds,
                config.dwell_min_seconds,
                config.dwell_max_seconds,
            ),
        )
        await self._conn.commit()
        return config

    async def update_noise_config(self, config: NoiseConfig) -> NoiseConfig:
        """
        Persiste la configuración de ruido (campos interval v2).

        Asegura que la fila existe primero (get_or_create).
        Solo actualiza los campos *_interval_*_seconds y los campos comunes;
        los campos deprecated *_req_per_hour_* no se tocan.

        Spec noise-frequency-and-destination-weight.md §14 Paso 3.
        """
        # Asegurarse de que existe; si no, get_or_create la crea con defaults
        await self.get_or_create_noise_config(config.world_id)

        # Aplicar PATCH: solo campos v2
        await self._conn.execute(
            """
            UPDATE world_noise_config
               SET noise_enabled = ?,
                   hardcore_interval_min_seconds = ?,
                   hardcore_interval_max_seconds = ?,
                   passive_interval_min_seconds  = ?,
                   passive_interval_max_seconds  = ?,
                   dwell_min_seconds = ?,
                   dwell_max_seconds = ?
             WHERE world_id = ?
            """,
            (
                int(config.noise_enabled),
                config.hardcore_interval_min_seconds,
                config.hardcore_interval_max_seconds,
                config.passive_interval_min_seconds,
                config.passive_interval_max_seconds,
                config.dwell_min_seconds,
                config.dwell_max_seconds,
                config.world_id,
            ),
        )
        await self._conn.commit()
        return config

    # ------------------------------------------------------------------
    # Destinos
    # ------------------------------------------------------------------

    async def list_destinations(
        self,
        world_id: int,
        category_slug: str | None = None,
        include_dead: bool = False,
        include_unsafe: bool = False,
    ) -> list[NoiseDestination]:
        has_tid = await self._has_template_id_column()
        tid_col = ", template_id" if has_tid else ""
        cat_col = await self._get_category_column()
        query = f"""
            SELECT id, world_id, url_pattern, label, {cat_col}, frequency_weight,
                   is_safe, is_dead, consecutive_failures_count, created_at, last_used_at{tid_col}
              FROM noise_destinations
             WHERE world_id = ?
        """
        params: list = [world_id]

        if not include_dead:
            query += " AND is_dead = 0"
        if not include_unsafe:
            query += " AND is_safe = 1"
        if category_slug is not None:
            query += f" AND {cat_col} = ?"
            params.append(category_slug)

        query += " ORDER BY id ASC"

        rows = await self._conn.execute_fetchall(query, params)
        return [_row_to_destination(r) for r in rows]

    async def get_destination(self, dest_id: int) -> NoiseDestination | None:
        has_tid = await self._has_template_id_column()
        tid_col = ", template_id" if has_tid else ""
        cat_col = await self._get_category_column()
        rows = await self._conn.execute_fetchall(
            f"""
            SELECT id, world_id, url_pattern, label, {cat_col}, frequency_weight,
                   is_safe, is_dead, consecutive_failures_count, created_at, last_used_at{tid_col}
              FROM noise_destinations
             WHERE id = ?
            """,
            (dest_id,),
        )
        if not rows:
            return None
        return _row_to_destination(rows[0])

    async def _has_template_id_column(self) -> bool:
        """
        Comprueba si noise_destinations tiene la columna template_id (M-RT01).
        Necesario para retrocompatibilidad: los tests que no instancian
        RouteTemplateSQLiteAdapter no ejecutan M-RT01 y la columna puede no existir.
        Cachea el resultado en _template_id_col para evitar PRAGMA por cada SELECT.
        """
        if not hasattr(self, "_template_id_col"):
            cursor = await self._conn.execute("PRAGMA table_info(noise_destinations)")
            cols = {row[1] for row in await cursor.fetchall()}
            self._template_id_col = "template_id" in cols  # type: ignore[attr-defined]
        return self._template_id_col  # type: ignore[attr-defined]

    async def _get_category_column(self) -> str:
        """
        Devuelve 'category_slug' si noise_destinations ya fue migrada (M-CAT04),
        o 'category' si aún tiene el esquema viejo (retrocompatibilidad).
        Cachea el resultado para evitar PRAGMA por cada SELECT.
        """
        if not hasattr(self, "_cat_col_name"):
            cursor = await self._conn.execute("PRAGMA table_info(noise_destinations)")
            cols = {row[1] for row in await cursor.fetchall()}
            self._cat_col_name = "category_slug" if "category_slug" in cols else "category"  # type: ignore[attr-defined]
        return self._cat_col_name  # type: ignore[attr-defined]

    async def create_destination(
        self,
        world_id: int,
        url_pattern: str,
        label: str,
        category_slug: str = "uncategorized",
        frequency_weight: float = 1.0,
        is_safe: bool = True,
        template_id: int | None = None,
        # Alias retrocompat: 'category' era el parámetro anterior (NoiseCategory enum)
        category: "str | None" = None,
    ) -> NoiseDestination:
        # Alias retrocompat: si llegan con 'category' (NoiseCategory enum o str), usarlo
        # como category_slug. El código antiguo pasaba category=NoiseCategory.MAP.
        if category is not None and category_slug == "uncategorized":
            # category puede ser NoiseCategory enum o str; extraer el valor
            if hasattr(category, "value"):
                category_slug = category.value  # type: ignore[union-attr]
            else:
                category_slug = str(category)

        # Validar frequency_weight — la entidad también lo valida, pero defensa en profundidad
        if not (0.1 <= frequency_weight <= 5.0):
            raise ValueError(
                f"navigation_weight debe estar entre 0.1 y 5.0 "
                f"(anti-detección: pesos extremos hacen el ruido predecible)."
            )

        # Obtener world_server para validación de dominio
        world_server = await self._get_world_server(world_id)

        # Validar URL (RN-HS23 endurecida)
        _validate_url_pattern(url_pattern, world_server)

        now = _now_iso()

        # Guard M-RT01: solo incluir template_id en el INSERT si la columna existe.
        # Necesario para retrocompatibilidad con tests que no instancian RouteTemplateSQLiteAdapter.
        has_template_col = await self._has_template_id_column()
        cat_col = await self._get_category_column()

        try:
            if has_template_col:
                cursor = await self._conn.execute(
                    f"""
                    INSERT INTO noise_destinations
                      (world_id, url_pattern, label, {cat_col}, frequency_weight,
                       is_safe, is_dead, consecutive_failures_count, created_at, last_used_at,
                       template_id)
                    VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, NULL, ?)
                    """,
                    (world_id, url_pattern, label, category_slug, frequency_weight,
                     int(is_safe), now, template_id),
                )
            else:
                cursor = await self._conn.execute(
                    f"""
                    INSERT INTO noise_destinations
                      (world_id, url_pattern, label, {cat_col}, frequency_weight,
                       is_safe, is_dead, consecutive_failures_count, created_at, last_used_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, NULL)
                    """,
                    (world_id, url_pattern, label, category_slug, frequency_weight,
                     int(is_safe), now),
                )
            await self._conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError(
                    f"Ya existe un destino con url_pattern '{url_pattern}' para el mundo {world_id}."
                ) from exc
            raise

        dest_id = cursor.lastrowid
        return NoiseDestination(
            id=dest_id,
            world_id=world_id,
            url_pattern=url_pattern,
            label=label,
            category_slug=category_slug,
            frequency_weight=frequency_weight,
            is_safe=is_safe,
            is_dead=False,
            consecutive_failures_count=0,
            created_at=datetime.fromisoformat(now),
            last_used_at=None,
            template_id=template_id if has_template_col else None,
        )

    async def update_destination(
        self,
        dest_id: int,
        label: str | None = None,
        frequency_weight: float | None = None,
        is_safe: bool | None = None,
        category_slug: str | None = None,
    ) -> NoiseDestination:
        # Verificar existencia
        existing = await self.get_destination(dest_id)
        if existing is None:
            raise ValueError(f"Destino {dest_id} no encontrado.")

        # Aplicar PATCH
        new_label    = label             if label             is not None else existing.label
        new_fw       = frequency_weight  if frequency_weight  is not None else existing.frequency_weight
        new_safe     = is_safe           if is_safe           is not None else existing.is_safe
        new_cat_slug = category_slug     if category_slug     is not None else existing.category_slug

        if not (0.1 <= new_fw <= 5.0):
            raise ValueError(
                f"navigation_weight debe estar entre 0.1 y 5.0 "
                f"(anti-detección: pesos extremos hacen el ruido predecible)."
            )

        cat_col = await self._get_category_column()
        await self._conn.execute(
            f"""
            UPDATE noise_destinations
               SET label = ?, frequency_weight = ?, is_safe = ?, {cat_col} = ?
             WHERE id = ?
            """,
            (new_label, new_fw, int(new_safe), new_cat_slug, dest_id),
        )
        await self._conn.commit()

        existing.label = new_label
        existing.frequency_weight = new_fw
        existing.is_safe = new_safe
        existing.category_slug = new_cat_slug
        return existing

    async def delete_destination(self, dest_id: int) -> None:
        # FK CASCADE maneja paths y steps automáticamente
        await self._conn.execute(
            "DELETE FROM noise_destinations WHERE id = ?",
            (dest_id,),
        )
        await self._conn.commit()

    async def mark_destination_dead(self, dest_id: int) -> None:
        await self._conn.execute(
            "UPDATE noise_destinations SET is_dead = 1 WHERE id = ?",
            (dest_id,),
        )
        await self._conn.commit()

    async def bump_destination_failures(self, dest_id: int) -> int:
        await self._conn.execute(
            """
            UPDATE noise_destinations
               SET consecutive_failures_count = consecutive_failures_count + 1
             WHERE id = ?
            """,
            (dest_id,),
        )
        await self._conn.commit()
        rows = await self._conn.execute_fetchall(
            "SELECT consecutive_failures_count FROM noise_destinations WHERE id = ?",
            (dest_id,),
        )
        return rows[0]["consecutive_failures_count"] if rows else 0

    async def reset_destination_failures(self, dest_id: int) -> None:
        await self._conn.execute(
            "UPDATE noise_destinations SET consecutive_failures_count = 0 WHERE id = ?",
            (dest_id,),
        )
        await self._conn.commit()

    async def touch_last_used_at(self, dest_id: int, now) -> None:
        """Actualiza last_used_at del destino a now. Idempotente."""
        await self._conn.execute(
            "UPDATE noise_destinations SET last_used_at = ? WHERE id = ?",
            (now.isoformat(), dest_id),
        )
        await self._conn.commit()

    async def find_destination_by_url(
        self, world_id: int, url_pattern: str
    ) -> "NoiseDestination | None":
        """
        Devuelve el primer NoiseDestination de ese mundo con esa url_pattern,
        o None si no existe.

        Usado para detectar colisiones UNIQUE(world_id, url_pattern) antes de
        clonar una plantilla (RN-RT05, §9.1).

        Spec route-templates-developer-portal.md §14 Paso 4.
        """
        cat_col = await self._get_category_column()
        has_tid = await self._has_template_id_column()
        tid_col = ", template_id" if has_tid else ""
        rows = await self._conn.execute_fetchall(
            f"""
            SELECT id, world_id, url_pattern, label, {cat_col}, frequency_weight,
                   is_safe, is_dead, consecutive_failures_count, created_at, last_used_at{tid_col}
              FROM noise_destinations
             WHERE world_id = ? AND url_pattern = ?
             LIMIT 1
            """,
            (world_id, url_pattern),
        )
        if not rows:
            return None
        return _row_to_destination(rows[0])

    async def find_destination_by_template(
        self, world_id: int, template_id: int
    ) -> "NoiseDestination | None":
        """
        Devuelve el NoiseDestination de ese mundo cuyo template_id coincide,
        o None si no existe.

        Usado por EP-RT09 (sync) para localizar la instancia a re-sincronizar (§9.2).

        Spec route-templates-developer-portal.md §14 Paso 4.
        """
        cat_col = await self._get_category_column()
        rows = await self._conn.execute_fetchall(
            f"""
            SELECT id, world_id, url_pattern, label, {cat_col}, frequency_weight,
                   is_safe, is_dead, consecutive_failures_count, created_at, last_used_at,
                   template_id
              FROM noise_destinations
             WHERE world_id = ? AND template_id = ?
             LIMIT 1
            """,
            (world_id, template_id),
        )
        if not rows:
            return None
        return _row_to_destination(rows[0])

    async def pick_random_safe_destination(
        self, world_id: int
    ) -> NoiseDestination | None:
        """
        Selección ponderada por frequency_weight entre destinos seguros y activos.
        Excluye is_dead=True y is_safe=False.
        Devuelve None si no hay candidatos.

        GUARDIAN (RN-FW07) — CONDICIÓN NO NEGOCIABLE:
        Cuando hay 2+ destinos elegibles, aplica un clamp de probabilidad efectiva
        al 60% por destino para que ningún destino capture la mayoría aplastante
        de las visitas aunque tenga el peso máximo (5.0) y los demás el mínimo (0.1).

        Ejemplo peor caso: pesos [5.0, 0.1, 0.1, 0.1, 0.1]
          - Probabilidad cruda dominante: 5/(5+0.4) ≈ 93% → inaceptable
          - Tras clamp a 60%: dominante=60%, exceso (33%) redistribuido proporcionalmente

        Con un único destino elegible: siempre va a él (no es una firma — no hay elección).
        """
        destinations = await self.list_destinations(
            world_id, include_dead=False, include_unsafe=False
        )
        if not destinations:
            return None

        # Con un solo destino no hay sorteo posible
        if len(destinations) == 1:
            return destinations[0]

        # Construir pesos normalizados
        raw_weights = [d.frequency_weight for d in destinations]
        total = sum(raw_weights)
        probs = [w / total for w in raw_weights]

        # GUARDIAN: clamp de probabilidad efectiva al 60%
        _MAX_PROB = 0.60
        changed = True
        while changed:
            changed = False
            over = [(i, p) for i, p in enumerate(probs) if p > _MAX_PROB]
            if not over:
                break
            for idx, p in over:
                excess = p - _MAX_PROB
                probs[idx] = _MAX_PROB
                # Redistribuir el exceso proporcionalmente al resto
                rest_total = sum(probs[j] for j in range(len(probs)) if j != idx)
                if rest_total > 0:
                    for j in range(len(probs)):
                        if j != idx:
                            probs[j] += excess * (probs[j] / rest_total)
                changed = True

        # Asegurar suma == 1 (corrección de errores de punto flotante)
        s = sum(probs)
        if s > 0:
            probs = [p / s for p in probs]

        selected = random.choices(destinations, weights=probs, k=1)[0]
        return selected

    # ------------------------------------------------------------------
    # Rutas (NavigationPath con pasos anidados)
    # ------------------------------------------------------------------

    async def list_paths(self, dest_id: int) -> list[NavigationPath]:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, destination_id, origin, label, is_active,
                   COALESCE(is_dead, 0)                    AS is_dead,
                   COALESCE(consecutive_failures_count, 0) AS consecutive_failures_count
              FROM noise_navigation_paths
             WHERE destination_id = ?
             ORDER BY id ASC
            """,
            (dest_id,),
        )
        result = []
        for r in rows:
            steps = await self._fetch_steps_for_path(r["id"])
            result.append(_row_to_path(r, steps))
        return result

    async def get_path(self, path_id: int) -> NavigationPath | None:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, destination_id, origin, label, is_active,
                   COALESCE(is_dead, 0)                    AS is_dead,
                   COALESCE(consecutive_failures_count, 0) AS consecutive_failures_count
              FROM noise_navigation_paths
             WHERE id = ?
            """,
            (path_id,),
        )
        if not rows:
            return None
        steps = await self._fetch_steps_for_path(path_id)
        return _row_to_path(rows[0], steps)

    async def create_path(
        self,
        dest_id: int,
        origin: NavigationOrigin | str,  # acepta enum (legacy) o str (nuevo: "VILLAGE_<n>")
        label: str,
        steps: list[NavigationStep],
    ) -> NavigationPath:
        if not steps:
            raise ValueError("Una ruta debe tener al menos un paso (steps no puede estar vacío).")

        # Verificar que el destino existe
        dest = await self.get_destination(dest_id)
        if dest is None:
            raise ValueError(f"Destino {dest_id} no encontrado.")

        # Guard str/enum: si es enum, extraer el valor string; si ya es str, usarlo directamente
        origin_str: str = origin if isinstance(origin, str) else origin.value

        # Validar origin en la capa de aplicación (spec §7.2, RN-NP02, EC-NP05)
        villages = await self.get_villages_for_world(dest.world_id)
        _validate_origin(origin_str, [v.data_id for v in villages])

        async with self._conn.execute("BEGIN"):
            cursor = await self._conn.execute(
                """
                INSERT INTO noise_navigation_paths
                  (destination_id, origin, label, is_active, is_dead, consecutive_failures_count)
                VALUES (?, ?, ?, 1, 0, 0)
                """,
                (dest_id, origin_str, label),
            )
            path_id = cursor.lastrowid

            for step in steps:
                await self._conn.execute(
                    """
                    INSERT INTO noise_navigation_steps
                      (path_id, step_order, action, selector, value,
                       delay_min_ms, delay_max_ms, expected_url_after_click)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        path_id,
                        step.step_order,
                        step.action.value,
                        step.selector,
                        step.value,
                        step.delay_min_ms,
                        step.delay_max_ms,
                        step.expected_url_after_click,
                    ),
                )
        await self._conn.commit()

        # Leer los pasos creados con IDs reales
        created_steps = await self._fetch_steps_for_path(path_id)
        return NavigationPath(
            id=path_id,
            destination_id=dest_id,
            origin=origin_str,
            label=label,
            is_active=True,
            is_dead=False,
            consecutive_failures_count=0,
            steps=created_steps,
        )

    async def update_path(
        self,
        path_id: int,
        label: str | None = None,
        is_active: bool | None = None,
        steps: list[NavigationStep] | None = None,
    ) -> NavigationPath:
        # steps=[] es un error (ruta sin pasos no válida)
        if steps is not None and len(steps) == 0:
            raise ValueError(
                "steps=[] no está permitido. Una ruta debe tener al menos un paso. "
                "Para eliminar la ruta, usa DELETE /noise/paths/{path_id}."
            )

        existing = await self.get_path(path_id)
        if existing is None:
            raise ValueError(f"Ruta {path_id} no encontrada.")

        # PATCH de metadatos
        new_label     = label     if label     is not None else existing.label
        new_is_active = is_active if is_active is not None else existing.is_active

        # CA-NP25 / spec §10: si is_active pasa de False a True, resetear contadores
        # (is_dead + consecutive_failures_count) para que la ruta reactivada
        # no quede muerta inmediatamente en el primer fallo.
        reactivating = (
            is_active is True and not existing.is_active
        ) or (
            is_active is True and existing.is_dead
        )

        async with self._conn.execute("BEGIN"):
            if reactivating:
                await self._conn.execute(
                    """
                    UPDATE noise_navigation_paths
                       SET label = ?, is_active = ?, is_dead = 0, consecutive_failures_count = 0
                     WHERE id = ?
                    """,
                    (new_label, int(new_is_active), path_id),
                )
            else:
                await self._conn.execute(
                    """
                    UPDATE noise_navigation_paths
                       SET label = ?, is_active = ?
                     WHERE id = ?
                    """,
                    (new_label, int(new_is_active), path_id),
                )

            # Reemplazo atómico de steps si se pasan
            if steps is not None:
                await self._conn.execute(
                    "DELETE FROM noise_navigation_steps WHERE path_id = ?",
                    (path_id,),
                )
                for step in steps:
                    await self._conn.execute(
                        """
                        INSERT INTO noise_navigation_steps
                          (path_id, step_order, action, selector, value,
                           delay_min_ms, delay_max_ms, expected_url_after_click)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            path_id,
                            step.step_order,
                            step.action.value,
                            step.selector,
                            step.value,
                            step.delay_min_ms,
                            step.delay_max_ms,
                            step.expected_url_after_click,
                        ),
                    )
        await self._conn.commit()

        # Devolver estado actualizado
        updated = await self.get_path(path_id)
        return updated  # type: ignore[return-value]  # exists because we just checked

    async def delete_path(self, path_id: int) -> None:
        # FK CASCADE maneja steps automáticamente
        await self._conn.execute(
            "DELETE FROM noise_navigation_paths WHERE id = ?",
            (path_id,),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Path failures (spec noise-path-wizard.md §7.6 + RN-NP07)
    # ------------------------------------------------------------------

    async def mark_path_dead(self, path_id: int) -> None:
        """
        Marca la ruta como muerta (is_dead=True). Idempotente.
        Spec noise-path-wizard.md RN-NP07, CA-NP31.
        """
        await self._conn.execute(
            "UPDATE noise_navigation_paths SET is_dead = 1 WHERE id = ?",
            (path_id,),
        )
        await self._conn.commit()

    async def increment_path_failures(self, path_id: int) -> int:
        """
        Incrementa consecutive_failures_count en 1.
        Devuelve el nuevo valor del contador.
        Spec noise-path-wizard.md RN-NP07, CA-NP30.
        """
        await self._conn.execute(
            """
            UPDATE noise_navigation_paths
               SET consecutive_failures_count = consecutive_failures_count + 1
             WHERE id = ?
            """,
            (path_id,),
        )
        await self._conn.commit()
        rows = await self._conn.execute_fetchall(
            "SELECT consecutive_failures_count FROM noise_navigation_paths WHERE id = ?",
            (path_id,),
        )
        return rows[0]["consecutive_failures_count"] if rows else 0

    async def reset_path_failures(self, path_id: int) -> None:
        """
        Resetea consecutive_failures_count a 0. Idempotente.
        Spec noise-path-wizard.md RN-NP07, CA-NP32.
        """
        await self._conn.execute(
            "UPDATE noise_navigation_paths SET consecutive_failures_count = 0 WHERE id = ?",
            (path_id,),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Villages (spec noise-path-wizard.md §7.6 — Opción A)
    # ------------------------------------------------------------------

    async def get_villages_for_world(self, world_id: int) -> list:
        """
        Devuelve todas las aldeas de la tabla villages para el mundo dado.
        Se usa para construir la lista de anclas por-aldea y para validar
        origin=VILLAGE_N.

        Devuelve lista de Village (importado a nivel de módulo para evitar
        importaciones circulares en el adaptador de noise).
        Spec noise-path-wizard.md §7.6 (Opción A).
        """
        from core.entities.village import Village  # import local para no crear ciclo

        rows = await self._conn.execute_fetchall(
            """
            SELECT id, world_id, data_id, name, x, y
              FROM villages
             WHERE world_id = ?
             ORDER BY data_id ASC
            """,
            (world_id,),
        )
        return [
            Village(
                id=r["id"],
                world_id=r["world_id"],
                data_id=r["data_id"],
                name=r["name"],
                x=r["x"],
                y=r["y"],
            )
            for r in rows
        ]

    async def upsert_village(self, village) -> object:
        """
        UPSERT de una aldea en la tabla villages.
        Usada por el parser del village-switcher (EP-N13).

        Si la aldea ya existe (UNIQUE world_id+data_id), actualiza name, x, y.
        Devuelve la Village con su id de BD.
        Spec noise-path-wizard.md §7.6, RN-NP03.
        """
        from core.entities.village import Village  # import local para no crear ciclo

        await self._conn.execute(
            """
            INSERT INTO villages (world_id, data_id, name, x, y)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(world_id, data_id) DO UPDATE
               SET name = excluded.name,
                   x    = excluded.x,
                   y    = excluded.y
            """,
            (village.world_id, village.data_id, village.name, village.x, village.y),
        )
        await self._conn.commit()

        rows = await self._conn.execute_fetchall(
            "SELECT id FROM villages WHERE world_id = ? AND data_id = ?",
            (village.world_id, village.data_id),
        )
        db_id = rows[0]["id"] if rows else village.id
        return Village(
            id=db_id,
            world_id=village.world_id,
            data_id=village.data_id,
            name=village.name,
            x=village.x,
            y=village.y,
        )
