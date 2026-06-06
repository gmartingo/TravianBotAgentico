"""
Adaptador SQLite para el catálogo maestro de Plantillas de Rutas (RouteTemplateDbPort).

Tablas gestionadas (DDL inline, idempotente):
  - route_templates       — plantillas globales de rutas de ruido
  - route_template_paths  — rutas dentro de una plantilla (sin destination_id)
  - route_template_steps  — pasos de una ruta de plantilla (misma estructura que noise_navigation_steps)

Decisiones de diseño:
  - FK CASCADE en paths → template y steps → path para borrado limpio.
  - UNIQUE(slug) en route_templates.
  - UNIQUE(template_path_id, step_order) en route_template_steps.
  - La migración M-RT01 (ADD COLUMN template_id a noise_destinations) se ejecuta aquí,
    después de crear route_templates (la FK requiere que la tabla origen exista).
  - seed_route_templates() lee seeds/route_templates.json e inserta por slug (idempotente),
    con 2 pasadas: raíces primero, hijas después (resolviendo origin_slug → id).

Migraciones:
  M-RT01 (v1): ADD COLUMN template_id a noise_destinations
  M-RT02 (v2): ADD COLUMN origin_template_id a route_templates
  M-RT03 (v2 rev.2): DROP COLUMN navigation_weight de route_templates

NOTA (v2 rev.2): navigation_weight eliminado del DDL y del CRUD.
  El peso vive en NoiseDestination.frequency_weight (por-mundo). Ver §v2-PESO.

Spec route-templates-developer-portal.md §7.2, §7.3-bis, §9.4, §14 Paso 3 y 8,
     §v2.2.1, §v2.2.5, §v2.14 Pasos v2-1 y v2-5.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from aiosqlite import OperationalError

from core.entities.noise import (
    NoiseAction,
    NoiseCategory,
    NavigationStep,
    RouteTemplate,
    RouteTemplatePath,
)
from core.ports.route_template_db_port import RouteTemplateDbPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL — 3 tablas (v2: sin navigation_weight, con origin_template_id)
# ---------------------------------------------------------------------------

_CREATE_ROUTE_TEMPLATES = """
CREATE TABLE IF NOT EXISTS route_templates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    slug                TEXT    NOT NULL UNIQUE,
    label               TEXT    NOT NULL,
    category            TEXT    NOT NULL,
    url_pattern         TEXT    NOT NULL,
    is_safe             INTEGER NOT NULL DEFAULT 1,
    origin_template_id  INTEGER DEFAULT NULL
                                REFERENCES route_templates(id) ON DELETE SET NULL,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);
"""

_CREATE_IDX_ROUTE_TEMPLATES_SLUG = """
CREATE INDEX IF NOT EXISTS idx_route_templates_slug
    ON route_templates(slug);
"""

_CREATE_IDX_ROUTE_TEMPLATES_CATEGORY = """
CREATE INDEX IF NOT EXISTS idx_route_templates_category
    ON route_templates(category);
"""

_CREATE_IDX_ROUTE_TEMPLATES_ORIGIN = """
CREATE INDEX IF NOT EXISTS idx_route_templates_origin
    ON route_templates(origin_template_id);
"""

_CREATE_ROUTE_TEMPLATE_PATHS = """
CREATE TABLE IF NOT EXISTS route_template_paths (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES route_templates(id) ON DELETE CASCADE,
    origin      TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1
);
"""

_CREATE_IDX_ROUTE_TEMPLATE_PATHS = """
CREATE INDEX IF NOT EXISTS idx_route_template_paths_template
    ON route_template_paths(template_id);
"""

_CREATE_ROUTE_TEMPLATE_STEPS = """
CREATE TABLE IF NOT EXISTS route_template_steps (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    template_path_id         INTEGER NOT NULL
                                     REFERENCES route_template_paths(id) ON DELETE CASCADE,
    step_order               INTEGER NOT NULL,
    action                   TEXT    NOT NULL
                                     CHECK (action IN (
                                         'CLICK','WAIT_FOR_SELECTOR','SCROLL_TO','HOVER'
                                     )),
    selector                 TEXT    NOT NULL,
    value                    TEXT    NOT NULL DEFAULT '',
    delay_min_ms             INTEGER NOT NULL DEFAULT 500,
    delay_max_ms             INTEGER NOT NULL DEFAULT 900,
    expected_url_after_click TEXT    DEFAULT NULL,
    UNIQUE (template_path_id, step_order)
);
"""

_CREATE_IDX_ROUTE_TEMPLATE_STEPS = """
CREATE INDEX IF NOT EXISTS idx_route_template_steps_path
    ON route_template_steps(template_path_id, step_order);
"""


# ---------------------------------------------------------------------------
# Migraciones idempotentes
# ---------------------------------------------------------------------------

async def _migrate_m_rt01(conn: aiosqlite.Connection) -> None:
    """
    M-RT01 (v1): ADD COLUMN template_id a noise_destinations.
    FK nullable a route_templates.id con ON DELETE SET NULL.
    Solo se aplica si noise_destinations existe (puede no existir en tests aislados).
    Idempotente: OperationalError ignorado si la columna ya existe.

    Spec §7.3.
    """
    rows = await conn.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='noise_destinations'"
    )
    if not rows:
        return  # noise_destinations no existe aún; se aplicará cuando se cree

    try:
        await conn.execute(
            "ALTER TABLE noise_destinations"
            " ADD COLUMN template_id INTEGER DEFAULT NULL"
            " REFERENCES route_templates(id) ON DELETE SET NULL"
        )
        await conn.commit()
        logger.info("M-RT01 completada: template_id añadida a noise_destinations")
    except OperationalError:
        pass  # columna ya existe

    try:
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_noise_destinations_template"
            " ON noise_destinations(template_id)"
        )
        await conn.commit()
    except Exception:
        pass


async def _migrate_m_rt02(conn: aiosqlite.Connection) -> None:
    """
    M-RT02 (v2): ADD COLUMN origin_template_id a route_templates.
    FK nullable a route_templates.id (auto-referencia) con ON DELETE SET NULL.
    Idempotente: OperationalError ignorado si la columna ya existe.

    Spec §v2.2.1, §v2.14 Paso v2-1.
    """
    try:
        await conn.execute(
            "ALTER TABLE route_templates"
            " ADD COLUMN origin_template_id INTEGER DEFAULT NULL"
            " REFERENCES route_templates(id) ON DELETE SET NULL"
        )
        await conn.commit()
        logger.info("M-RT02 completada: origin_template_id añadida a route_templates")
    except OperationalError:
        pass  # columna ya existe

    try:
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_route_templates_origin"
            " ON route_templates(origin_template_id)"
        )
        await conn.commit()
    except Exception:
        pass


async def _migrate_m_rt03(conn: aiosqlite.Connection) -> None:
    """
    M-RT03 (v2 rev.2): DROP COLUMN navigation_weight de route_templates.
    El catálogo está vacío en todos los entornos donde se aplica esta migración.
    Requiere SQLite >= 3.35 (2021). Idempotente: OperationalError ignorado si
    la columna ya no existe.

    Spec §7.3-bis, §v2-PESO.
    """
    try:
        await conn.execute(
            "ALTER TABLE route_templates DROP COLUMN navigation_weight"
        )
        await conn.commit()
        logger.info("M-RT03 completada: navigation_weight eliminada de route_templates")
    except OperationalError:
        pass  # columna ya eliminada en una ejecución anterior


async def _migrate_m_rt04(conn: aiosqlite.Connection) -> None:
    """
    M-RT04: Elimina el CHECK constraint de category en route_templates,
    convirtiendo category en texto libre (≤ 50 chars).

    Motivación: el enum cerrado de 7 valores impide crear categorías nuevas
    (p.ej. "Estadísticas", "Top 10") sin tocar el código. La validación de
    longitud/no-vacío se hace en la entidad core y en los modelos Pydantic;
    la BD solo garantiza TEXT NOT NULL.

    SQLite no permite quitar un CHECK con ALTER TABLE; la única vía correcta
    es reconstruir la tabla:
      1. Crear route_templates_new SIN el CHECK.
      2. Copiar todos los datos (preserva origin_template_id self-FK).
      3. Borrar la vieja con PRAGMA foreign_keys=OFF para no romper FKs hijas
         (route_template_paths → route_templates), que se actualizan en el paso 4.
      4. Renombrar la nueva a route_templates.
      5. La FK hija (route_template_paths.template_id) ya apunta al mismo nombre;
         SQLite la acepta porque las FKs son por nombre de tabla, no por OID.

    Idempotente: detecta si el CHECK ya no existe (buscando la cadena 'CHECK'
    en el sql de sqlite_master). Si no hay CHECK → no-op.

    Spec: nuevo — categoría libre, fuera del spec original.
    """
    rows = await conn.execute_fetchall(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='route_templates'"
    )
    if not rows:
        return  # tabla no existe aún — no-op

    current_sql: str = rows[0]["sql"] or ""
    # Detectar si el CHECK de category sigue presente
    # (M-RT04 ya aplicada si no aparece 'MAP','OASIS_INFO' en el CHECK)
    if "CHECK (category IN" not in current_sql and "CHECK(category IN" not in current_sql:
        return  # ya sin CHECK — idempotente

    await conn.execute("PRAGMA foreign_keys = OFF")
    try:
        # 1. Crear tabla nueva sin el CHECK de category
        await conn.execute("""
            CREATE TABLE route_templates_new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                slug                TEXT    NOT NULL UNIQUE,
                label               TEXT    NOT NULL,
                category            TEXT    NOT NULL,
                url_pattern         TEXT    NOT NULL,
                is_safe             INTEGER NOT NULL DEFAULT 1,
                origin_template_id  INTEGER DEFAULT NULL
                                            REFERENCES route_templates_new(id) ON DELETE SET NULL,
                created_at          TEXT    NOT NULL,
                updated_at          TEXT    NOT NULL
            )
        """)

        # 2. Copiar todos los datos
        await conn.execute("""
            INSERT INTO route_templates_new
              (id, slug, label, category, url_pattern, is_safe,
               origin_template_id, created_at, updated_at)
            SELECT id, slug, label, category, url_pattern, is_safe,
                   origin_template_id, created_at, updated_at
              FROM route_templates
        """)

        # 3. Borrar la tabla vieja
        await conn.execute("DROP TABLE route_templates")

        # 4. Renombrar la nueva
        await conn.execute("ALTER TABLE route_templates_new RENAME TO route_templates")

        await conn.commit()
        logger.info("M-RT04 completada: CHECK constraint de category eliminado de route_templates")
    except Exception:
        await conn.execute("PRAGMA foreign_keys = ON")
        raise
    finally:
        await conn.execute("PRAGMA foreign_keys = ON")


# ---------------------------------------------------------------------------
# Helpers de conversión fila → entidad
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_template_step(row: aiosqlite.Row) -> NavigationStep:
    row_dict = dict(row)
    return NavigationStep(
        id=row_dict["id"],
        path_id=row_dict["template_path_id"],
        step_order=row_dict["step_order"],
        action=NoiseAction(row_dict["action"]),
        selector=row_dict["selector"],
        value=row_dict.get("value", ""),
        delay_min_ms=row_dict["delay_min_ms"],
        delay_max_ms=row_dict["delay_max_ms"],
        expected_url_after_click=row_dict.get("expected_url_after_click"),
    )


def _row_to_template_path(row: aiosqlite.Row, steps: list[NavigationStep]) -> RouteTemplatePath:
    row_dict = dict(row)
    return RouteTemplatePath(
        id=row_dict["id"],
        template_id=row_dict["template_id"],
        origin=row_dict["origin"],
        label=row_dict["label"],
        is_active=bool(row_dict["is_active"]),
        steps=steps,
    )


def _row_to_template(row: aiosqlite.Row, paths: list[RouteTemplatePath]) -> RouteTemplate:
    row_dict = dict(row)
    return RouteTemplate(
        id=row_dict["id"],
        slug=row_dict["slug"],
        label=row_dict["label"],
        category=row_dict["category"],   # texto libre — no instanciar NoiseCategory
        url_pattern=row_dict["url_pattern"],
        is_safe=bool(row_dict["is_safe"]),
        origin_template_id=row_dict.get("origin_template_id"),  # v2 — puede ser None
        paths=paths,
        created_at=datetime.fromisoformat(row_dict["created_at"]) if row_dict["created_at"] else None,
        updated_at=datetime.fromisoformat(row_dict["updated_at"]) if row_dict["updated_at"] else None,
    )


# ---------------------------------------------------------------------------
# Función de seed (sep de concerns: leer JSON → llamar a create_template)
# ---------------------------------------------------------------------------

async def seed_route_templates(adapter: "RouteTemplateSQLiteAdapter") -> int:
    """
    Carga el seed de plantillas desde seeds/route_templates.json.
    Idempotente por slug: si la plantilla ya existe, no la modifica
    (respeta ediciones posteriores del desarrollador).

    El seed puede estar vacío ([]) — en ese caso no inserta nada y devuelve 0.
    Esto es el estado inicial v2 (el catálogo se puebla manualmente o con
    plantillas atómicas encadenadas).

    Algoritmo de 2 pasadas para resolver origin_slug → origin_template_id:
      Pasada 1: insertar todas las plantillas raíz (sin origin_slug o origin_slug=null).
      Pasada 2: insertar las que tienen origin_slug, resolviendo el slug del origen
                al ID real ya insertado.

    Spec route-templates-developer-portal.md §9.4, §v2.2.5.
    """
    seed_path = Path(__file__).parent.parent.parent / "seeds" / "route_templates.json"
    if not seed_path.exists():
        logger.warning("seed_route_templates: fichero %s no encontrado, seed omitido", seed_path)
        return 0

    raw: list[dict] = json.loads(seed_path.read_text(encoding="utf-8"))
    if not raw:
        logger.debug("seed_route_templates: seed vacío, nada que insertar")
        return 0

    inserted = 0
    slug_to_id: dict[str, int] = {}

    # ---- Pasada 1: raíces (sin origin_slug) ----
    for item in raw:
        if item.get("origin_slug") is not None:
            continue  # se procesará en la pasada 2
        tpl = await _build_and_insert_seed_item(adapter, item, origin_id=None)
        if tpl is not None:
            slug_to_id[tpl.slug] = tpl.id  # type: ignore[arg-type]
            inserted += 1

    # Cargar también slugs de plantillas ya existentes (para resolver dependencias)
    for item in raw:
        slug = item["slug"]
        if slug not in slug_to_id:
            existing = await adapter.get_template_by_slug(slug)
            if existing is not None and existing.id is not None:
                slug_to_id[slug] = existing.id

    # ---- Pasada 2: hijas (con origin_slug) ----
    for item in raw:
        origin_slug = item.get("origin_slug")
        if origin_slug is None:
            continue  # ya procesado en pasada 1
        origin_id = slug_to_id.get(origin_slug)
        if origin_id is None:
            logger.warning(
                "seed_route_templates: origin_slug '%s' no encontrado para '%s', omitido",
                origin_slug,
                item["slug"],
            )
            continue
        tpl = await _build_and_insert_seed_item(adapter, item, origin_id=origin_id)
        if tpl is not None:
            slug_to_id[tpl.slug] = tpl.id  # type: ignore[arg-type]
            inserted += 1

    logger.info(
        "seed_route_templates: %d plantillas insertadas (de %d en el fichero)",
        inserted, len(raw),
    )
    return inserted


async def _build_and_insert_seed_item(
    adapter: "RouteTemplateSQLiteAdapter",
    item: dict,
    origin_id: int | None,
) -> RouteTemplate | None:
    """
    Construye y persiste una plantilla desde un ítem del seed JSON.
    Devuelve la plantilla creada, o None si ya existe (idempotente).
    """
    existing = await adapter.get_template_by_slug(item["slug"])
    if existing is not None:
        return None  # idempotente: no modificar

    paths: list[RouteTemplatePath] = []
    for p_data in item.get("paths", []):
        steps: list[NavigationStep] = []
        for s_data in p_data.get("steps", []):
            steps.append(NavigationStep(
                id=None,
                path_id=None,
                step_order=s_data["step_order"],
                action=NoiseAction(s_data["action"]),
                selector=s_data["selector"],
                value=s_data.get("value", ""),
                delay_min_ms=s_data.get("delay_min_ms", 500),
                delay_max_ms=s_data.get("delay_max_ms", 900),
                expected_url_after_click=s_data.get("expected_url_after_click"),
            ))
        paths.append(RouteTemplatePath(
            id=None,
            template_id=None,
            origin=p_data["origin"],
            label=p_data["label"],
            is_active=p_data.get("is_active", True),
            steps=steps,
        ))

    tpl = RouteTemplate(
        id=None,
        slug=item["slug"],
        label=item["label"],
        category=item["category"],  # texto libre — acepta valores históricos y nuevos
        url_pattern=item["url_pattern"],
        is_safe=item.get("is_safe", True),
        origin_template_id=origin_id,
        paths=paths,
    )
    return await adapter.create_template(tpl)


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------

class RouteTemplateSQLiteAdapter(RouteTemplateDbPort):
    """
    Implementa RouteTemplateDbPort con aiosqlite.
    Comparte la misma conexión SQLite (WAL) que el resto de adaptadores.

    PRAGMA foreign_keys = ON se activa en ensure_tables() para que las FKs
    ON DELETE SET NULL y ON DELETE CASCADE actúen en SQLite.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def ensure_tables(self) -> None:
        """
        Crea las 3 tablas de plantillas si no existen y ejecuta las migraciones.
        Idempotente (CREATE TABLE IF NOT EXISTS).

        Orden obligatorio:
          1. PRAGMA foreign_keys = ON (necesario para ON DELETE SET NULL / CASCADE).
          2. DDL de route_templates (necesario antes de M-RT01 que añade FK a esta tabla).
          3. DDL de route_template_paths y route_template_steps.
          4. M-RT01 (añade template_id a noise_destinations con FK a route_templates).
          5. M-RT02 (añade origin_template_id a route_templates — auto-referencia).
          6. M-RT03 (elimina navigation_weight de route_templates).

        Spec §14 Pasos 3, 4; §v2.14 Paso v2-1; §v2-PESO.
        """
        # PRAGMA foreign_keys obligatorio para que ON DELETE SET NULL actúe.
        await self._conn.execute("PRAGMA foreign_keys = ON")

        await self._conn.execute(_CREATE_ROUTE_TEMPLATES)
        await self._conn.execute(_CREATE_IDX_ROUTE_TEMPLATES_SLUG)
        await self._conn.execute(_CREATE_IDX_ROUTE_TEMPLATES_CATEGORY)
        await self._conn.execute(_CREATE_IDX_ROUTE_TEMPLATES_ORIGIN)
        await self._conn.execute(_CREATE_ROUTE_TEMPLATE_PATHS)
        await self._conn.execute(_CREATE_IDX_ROUTE_TEMPLATE_PATHS)
        await self._conn.execute(_CREATE_ROUTE_TEMPLATE_STEPS)
        await self._conn.execute(_CREATE_IDX_ROUTE_TEMPLATE_STEPS)
        await self._conn.commit()

        # Migraciones idempotentes en orden
        await _migrate_m_rt01(self._conn)
        await _migrate_m_rt02(self._conn)
        await _migrate_m_rt03(self._conn)
        await _migrate_m_rt04(self._conn)

        logger.debug("RouteTemplateSQLiteAdapter: tablas y migraciones aseguradas")

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    async def _fetch_steps_for_path(self, template_path_id: int) -> list[NavigationStep]:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, template_path_id, step_order, action, selector, value,
                   delay_min_ms, delay_max_ms, expected_url_after_click
              FROM route_template_steps
             WHERE template_path_id = ?
             ORDER BY step_order ASC
            """,
            (template_path_id,),
        )
        return [_row_to_template_step(r) for r in rows]

    async def _fetch_paths_for_template(self, template_id: int) -> list[RouteTemplatePath]:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, template_id, origin, label, is_active
              FROM route_template_paths
             WHERE template_id = ?
             ORDER BY id ASC
            """,
            (template_id,),
        )
        result = []
        for r in rows:
            steps = await self._fetch_steps_for_path(r["id"])
            result.append(_row_to_template_path(r, steps))
        return result

    async def _insert_paths_and_steps(
        self,
        template_id: int,
        paths: list[RouteTemplatePath],
    ) -> list[RouteTemplatePath]:
        """Inserta paths y steps de una plantilla. Devuelve los paths con IDs reales."""
        created_paths: list[RouteTemplatePath] = []
        for path in paths:
            cursor = await self._conn.execute(
                """
                INSERT INTO route_template_paths (template_id, origin, label, is_active)
                VALUES (?, ?, ?, ?)
                """,
                (template_id, path.origin, path.label, int(path.is_active)),
            )
            path_id = cursor.lastrowid

            for step in path.steps:
                await self._conn.execute(
                    """
                    INSERT INTO route_template_steps
                      (template_path_id, step_order, action, selector, value,
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

            created_steps = await self._fetch_steps_for_path(path_id)
            created_paths.append(RouteTemplatePath(
                id=path_id,
                template_id=template_id,
                origin=path.origin,
                label=path.label,
                is_active=path.is_active,
                steps=created_steps,
            ))
        return created_paths

    # ------------------------------------------------------------------
    # CRUD de plantillas
    # ------------------------------------------------------------------

    async def get_template(self, template_id: int) -> RouteTemplate | None:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, slug, label, category, url_pattern, is_safe,
                   origin_template_id, created_at, updated_at
              FROM route_templates
             WHERE id = ?
            """,
            (template_id,),
        )
        if not rows:
            return None
        paths = await self._fetch_paths_for_template(template_id)
        return _row_to_template(rows[0], paths)

    async def get_template_by_slug(self, slug: str) -> RouteTemplate | None:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, slug, label, category, url_pattern, is_safe,
                   origin_template_id, created_at, updated_at
              FROM route_templates
             WHERE slug = ?
            """,
            (slug,),
        )
        if not rows:
            return None
        template_id = rows[0]["id"]
        paths = await self._fetch_paths_for_template(template_id)
        return _row_to_template(rows[0], paths)

    async def list_templates(
        self,
        category: "NoiseCategory | str | None" = None,
        include_paths: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RouteTemplate]:
        query = """
            SELECT id, slug, label, category, url_pattern, is_safe,
                   origin_template_id, created_at, updated_at
              FROM route_templates
        """
        params: list[Any] = []
        if category is not None:
            query += " WHERE category = ?"
            # Normalizar: puede venir como NoiseCategory enum o como str libre
            params.append(category.value if isinstance(category, NoiseCategory) else str(category))
        query += " ORDER BY id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = await self._conn.execute_fetchall(query, params)
        result = []
        for r in rows:
            if include_paths:
                paths = await self._fetch_paths_for_template(r["id"])
            else:
                paths = []
            result.append(_row_to_template(r, paths))
        return result

    async def get_templates_by_origin(self, origin_template_id: int) -> list[RouteTemplate]:
        """
        Devuelve las plantillas hijas (origin_template_id = <id>).
        Sin paths cargados (uso principal: listar hijas, no ejecutar).

        Spec §v2.3, §v2.14 Paso v2-3.
        """
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, slug, label, category, url_pattern, is_safe,
                   origin_template_id, created_at, updated_at
              FROM route_templates
             WHERE origin_template_id = ?
             ORDER BY id ASC
            """,
            (origin_template_id,),
        )
        return [_row_to_template(r, []) for r in rows]

    async def create_template(self, template: RouteTemplate) -> RouteTemplate:
        now = _now_iso()
        try:
            cursor = await self._conn.execute(
                """
                INSERT INTO route_templates
                  (slug, label, category, url_pattern, is_safe,
                   origin_template_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template.slug,
                    template.label,
                    str(template.category),  # texto libre — no .value (podría ser str ya)
                    template.url_pattern,
                    int(template.is_safe),
                    template.origin_template_id,
                    now,
                    now,
                ),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError(
                    f"Ya existe una plantilla con slug '{template.slug}'."
                ) from exc
            raise

        template_id = cursor.lastrowid

        created_paths = await self._insert_paths_and_steps(template_id, template.paths)
        await self._conn.commit()

        return RouteTemplate(
            id=template_id,
            slug=template.slug,
            label=template.label,
            category=template.category,
            url_pattern=template.url_pattern,
            is_safe=template.is_safe,
            origin_template_id=template.origin_template_id,
            paths=created_paths,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
        )

    async def update_template(
        self,
        template_id: int,
        label: str | None = None,
        is_safe: bool | None = None,
        category: str | None = None,           # editable desde v2-cat-libre
        origin_template_id: int | None | type[...] = ...,  # Ellipsis = no cambiar
        paths: list[RouteTemplatePath] | None = None,
    ) -> RouteTemplate:
        """
        PATCH parcial de una plantilla.

        slug y url_pattern son inmutables (RN-RT02).
        category ahora es EDITABLE (texto libre ≤ 50 chars). Pasar None para no cambiarla.
        navigation_weight eliminado (v2 rev.2).
        origin_template_id:
          - Ellipsis (default): no cambiar el valor actual.
          - None: quitar el origen (plantilla pasa a raíz libre).
          - int: reasignar el origen.

        Spec §v2.3 (origin_template_id mutable), §v2 rev.2 (sin navigation_weight),
        v2-cat-libre (category editable).
        """
        existing = await self.get_template(template_id)
        if existing is None:
            raise ValueError(f"Plantilla {template_id} no encontrada.")

        new_label    = label    if label    is not None else existing.label
        new_safe     = is_safe  if is_safe  is not None else existing.is_safe
        new_category = str(category).strip() if category is not None else str(existing.category)
        # origin_template_id: solo actualizar si NO es Ellipsis
        if origin_template_id is ...:
            new_origin = existing.origin_template_id
        else:
            new_origin = origin_template_id  # type: ignore[assignment]

        now = _now_iso()
        await self._conn.execute(
            """
            UPDATE route_templates
               SET label = ?, is_safe = ?, category = ?, origin_template_id = ?, updated_at = ?
             WHERE id = ?
            """,
            (new_label, int(new_safe), new_category, new_origin, now, template_id),
        )

        # Reemplazo atómico de paths+steps si se pasan
        if paths is not None:
            await self._conn.execute(
                "DELETE FROM route_template_paths WHERE template_id = ?",
                (template_id,),
            )
            await self._insert_paths_and_steps(template_id, paths)

        await self._conn.commit()

        return await self.get_template(template_id)  # type: ignore[return-value]

    async def delete_template(self, template_id: int) -> None:
        """
        Borra la plantilla y en cascada sus paths y steps.

        Los noise_destinations clonados quedan con template_id=NULL (FK ON DELETE SET NULL).
        Las plantillas hijas quedan con origin_template_id=NULL (FK ON DELETE SET NULL en v2).
        Idempotente: no lanza si la plantilla no existe.

        Spec §RN-RT06, §v2.2.1.
        """
        await self._conn.execute(
            "DELETE FROM route_templates WHERE id = ?",
            (template_id,),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    async def list_paths_for_template(self, template_id: int) -> list[RouteTemplatePath]:
        return await self._fetch_paths_for_template(template_id)

    # ------------------------------------------------------------------
    # Seed
    # ------------------------------------------------------------------

    async def seed_templates(self, templates: list[RouteTemplate]) -> int:
        inserted = 0
        for template in templates:
            existing = await self.get_template_by_slug(template.slug)
            if existing is not None:
                continue
            await self.create_template(template)
            inserted += 1
        return inserted

    # ------------------------------------------------------------------
    # Conteo
    # ------------------------------------------------------------------

    async def count_paths_for_template(self, template_id: int) -> int:
        rows = await self._conn.execute_fetchall(
            "SELECT COUNT(*) AS cnt FROM route_template_paths WHERE template_id = ?",
            (template_id,),
        )
        return rows[0]["cnt"] if rows else 0
