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
  - La migración M-RT01 (ADD COLUMN template_id a noise_destinations) se ejecuta en
    NoiseSQLiteAdapter.ensure_tables(), no aquí; el adaptador de noise es el dueño
    de la tabla noise_destinations.
  - seed_route_templates() lee seeds/route_templates.json e inserta por slug (idempotente).

Spec route-templates-developer-portal.md §7.2, §9.4, §14 Paso 3 y 8.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

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
# DDL — 3 tablas nuevas
# ---------------------------------------------------------------------------

_CREATE_ROUTE_TEMPLATES = """
CREATE TABLE IF NOT EXISTS route_templates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    slug             TEXT    NOT NULL UNIQUE,
    label            TEXT    NOT NULL,
    category         TEXT    NOT NULL
                             CHECK (category IN (
                                 'MAP','OASIS_INFO','PLAYER_PROFILE',
                                 'MESSAGES','REPORTS','BUILDING_VIEW','OTHER'
                             )),
    url_pattern      TEXT    NOT NULL,
    navigation_weight REAL   NOT NULL DEFAULT 1.0
                             CHECK (navigation_weight >= 0.1 AND navigation_weight <= 5.0),
    is_safe          INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
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
        category=NoiseCategory(row_dict["category"]),
        url_pattern=row_dict["url_pattern"],
        navigation_weight=row_dict["navigation_weight"],
        is_safe=bool(row_dict["is_safe"]),
        paths=paths,
        created_at=datetime.fromisoformat(row_dict["created_at"]) if row_dict["created_at"] else None,
        updated_at=datetime.fromisoformat(row_dict["updated_at"]) if row_dict["updated_at"] else None,
    )


# ---------------------------------------------------------------------------
# Función de seed (sep de concerns: leer JSON → llamar a create_template)
# ---------------------------------------------------------------------------

async def seed_route_templates(adapter: "RouteTemplateSQLiteAdapter") -> int:
    """
    Carga el seed de ~20 plantillas desde seeds/route_templates.json.
    Idempotente por slug: si la plantilla ya existe, no la modifica
    (respeta ediciones posteriores del desarrollador).
    Devuelve el número de plantillas insertadas.

    Spec route-templates-developer-portal.md §9.4.
    """
    seed_path = Path(__file__).parent.parent.parent / "seeds" / "route_templates.json"
    if not seed_path.exists():
        logger.warning("seed_route_templates: fichero %s no encontrado, seed omitido", seed_path)
        return 0

    raw: list[dict] = json.loads(seed_path.read_text(encoding="utf-8"))
    inserted = 0
    for item in raw:
        existing = await adapter.get_template_by_slug(item["slug"])
        if existing is not None:
            continue  # ya existe — idempotente, no modificar

        # Deserializar paths y steps
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
            category=NoiseCategory(item["category"]),
            url_pattern=item["url_pattern"],
            navigation_weight=item.get("navigation_weight", 1.0),
            is_safe=item.get("is_safe", True),
            paths=paths,
        )
        await adapter.create_template(tpl)
        inserted += 1

    logger.info("seed_route_templates: %d plantillas insertadas (de %d en el fichero)", inserted, len(raw))
    return inserted


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------

class RouteTemplateSQLiteAdapter(RouteTemplateDbPort):
    """
    Implementa RouteTemplateDbPort con aiosqlite.
    Comparte la misma conexión SQLite (WAL) que el resto de adaptadores.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def ensure_tables(self) -> None:
        """
        Crea las 3 tablas de plantillas si no existen y ejecuta la migración M-RT01.
        Idempotente (CREATE TABLE IF NOT EXISTS).
        Llamar en el lifespan de la app DESPUÉS de NoiseSQLiteAdapter.ensure_tables().

        Migraciones:
          M-RT01: añade columna template_id (FK nullable a route_templates.id con
                  ON DELETE SET NULL) a noise_destinations. Se ejecuta aquí (después
                  de crear route_templates) para que la FK sea válida.
                  Idempotente: ALTER TABLE falla silenciosamente si la columna ya existe.

        Spec route-templates-developer-portal.md §14 Paso 3 y Paso 4.
        """
        await self._conn.execute(_CREATE_ROUTE_TEMPLATES)
        await self._conn.execute(_CREATE_IDX_ROUTE_TEMPLATES_SLUG)
        await self._conn.execute(_CREATE_IDX_ROUTE_TEMPLATES_CATEGORY)
        await self._conn.execute(_CREATE_ROUTE_TEMPLATE_PATHS)
        await self._conn.execute(_CREATE_IDX_ROUTE_TEMPLATE_PATHS)
        await self._conn.execute(_CREATE_ROUTE_TEMPLATE_STEPS)
        await self._conn.execute(_CREATE_IDX_ROUTE_TEMPLATE_STEPS)
        await self._conn.commit()

        # M-RT01: añadir template_id a noise_destinations (solo si noise_destinations existe)
        # La tabla noise_destinations puede no existir si los tests solo instancian
        # RouteTemplateSQLiteAdapter sin NoiseSQLiteAdapter (poco probable pero seguro).
        await self._migrate_m_rt01()

        logger.debug("RouteTemplateSQLiteAdapter: tablas y migración M-RT01 aseguradas")

    async def _migrate_m_rt01(self) -> None:
        """
        Migración M-RT01: añadir columna template_id a noise_destinations.

        La columna es FK nullable a route_templates.id con ON DELETE SET NULL.
        Si la tabla noise_destinations no existe, la migración se omite silenciosamente
        (se aplicará cuando se cree la tabla).

        Idempotente: ALTER TABLE falla silenciosamente si la columna ya existe.

        Spec route-templates-developer-portal.md §7.3, §14 Paso 4.
        """
        # Verificar si noise_destinations existe antes de intentar la migración
        rows = await self._conn.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='noise_destinations'",
        )
        if not rows:
            # noise_destinations no existe aún; la columna se añadirá cuando se cree
            return

        try:
            await self._conn.execute(
                "ALTER TABLE noise_destinations"
                " ADD COLUMN template_id INTEGER DEFAULT NULL"
                " REFERENCES route_templates(id) ON DELETE SET NULL"
            )
            await self._conn.commit()
            logger.info(
                "RouteTemplateSQLiteAdapter: migración M-RT01 completada "
                "(template_id añadida a noise_destinations)"
            )
        except OperationalError:
            pass  # columna ya existe — migración idempotente

        # Crear índice (idempotente)
        try:
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_noise_destinations_template"
                " ON noise_destinations(template_id)"
            )
            await self._conn.commit()
        except Exception:
            pass

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
            SELECT id, slug, label, category, url_pattern, navigation_weight,
                   is_safe, created_at, updated_at
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
            SELECT id, slug, label, category, url_pattern, navigation_weight,
                   is_safe, created_at, updated_at
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
        category: NoiseCategory | None = None,
        include_paths: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RouteTemplate]:
        query = """
            SELECT id, slug, label, category, url_pattern, navigation_weight,
                   is_safe, created_at, updated_at
              FROM route_templates
        """
        params: list = []
        if category is not None:
            query += " WHERE category = ?"
            params.append(category.value)
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

    async def create_template(self, template: RouteTemplate) -> RouteTemplate:
        now = _now_iso()
        try:
            cursor = await self._conn.execute(
                """
                INSERT INTO route_templates
                  (slug, label, category, url_pattern, navigation_weight, is_safe,
                   created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template.slug,
                    template.label,
                    template.category.value,
                    template.url_pattern,
                    template.navigation_weight,
                    int(template.is_safe),
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
            navigation_weight=template.navigation_weight,
            is_safe=template.is_safe,
            paths=created_paths,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
        )

    async def update_template(
        self,
        template_id: int,
        label: str | None = None,
        navigation_weight: float | None = None,
        is_safe: bool | None = None,
        paths: list[RouteTemplatePath] | None = None,
    ) -> RouteTemplate:
        existing = await self.get_template(template_id)
        if existing is None:
            raise ValueError(f"Plantilla {template_id} no encontrada.")

        new_label  = label             if label             is not None else existing.label
        new_weight = navigation_weight if navigation_weight is not None else existing.navigation_weight
        new_safe   = is_safe           if is_safe           is not None else existing.is_safe

        now = _now_iso()
        await self._conn.execute(
            """
            UPDATE route_templates
               SET label = ?, navigation_weight = ?, is_safe = ?, updated_at = ?
             WHERE id = ?
            """,
            (new_label, new_weight, int(new_safe), now, template_id),
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
        # FK CASCADE borra automáticamente route_template_paths y route_template_steps.
        # Los noise_destinations clonados quedan con template_id=NULL (FK ON DELETE SET NULL).
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
