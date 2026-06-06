"""
Adaptador SQLite para el catálogo dinámico de Categorías de Rutas (RouteCategoryDbPort).

Tablas gestionadas (DDL inline, idempotente):
  - route_categories  — catálogo global de categorías de rutas de ruido

Decisiones de diseño:
  - label_lower como columna explícita para UNIQUE CI (T3 del spec).
  - Sin FK hard desde route_templates / noise_destinations (T4 del spec).
  - Borrado atómico: UPDATE plantillas + UPDATE destinos + DELETE en una sola transacción.
  - slugify helper: lowercase + reemplazar no-alfanumérico por '-' + colapsar guiones.
  - Seed 'uncategorized' con INSERT OR IGNORE (M-CAT02, idempotente).
  - Reutiliza el patrón de SQL crudo + aiosqlite de AccountSQLiteAdapter.

Spec route-categories-dynamic.md §7.1, §9, §14 Pasos 1, 2, 5.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import aiosqlite

from core.entities.route_category import RouteCategory
from core.ports.route_category_db_port import UNSET, RouteCategoryDbPort, _UnsetType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_ROUTE_CATEGORIES = """
CREATE TABLE IF NOT EXISTS route_categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,
    label       TEXT    NOT NULL,
    label_lower TEXT    NOT NULL UNIQUE,
    color       TEXT,
    is_default  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);
"""

_CREATE_IDX_ROUTE_CATEGORIES_SLUG = """
CREATE INDEX IF NOT EXISTS idx_route_categories_slug ON route_categories(slug);
"""


# ---------------------------------------------------------------------------
# Helpers de conversión y utilidad
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_category(row: aiosqlite.Row) -> RouteCategory:
    row_dict = dict(row)
    return RouteCategory(
        slug=row_dict["slug"],
        label=row_dict["label"],
        color=row_dict.get("color"),
        is_default=bool(row_dict["is_default"]),
        created_at=(
            datetime.fromisoformat(row_dict["created_at"])
            if row_dict.get("created_at")
            else None
        ),
    )


def slugify(label: str) -> str:
    """
    Genera un slug kebab-case a partir de un label.

    Algoritmo (RN-CAT08):
    1. Strip + lowercase.
    2. Reemplazar cualquier secuencia de caracteres no alfanuméricos por '-'.
    3. Colapsar guiones múltiples (ya hecho por el regex).
    4. Eliminar guiones al inicio y al final.

    Ejemplos:
      "Mapa"         → "mapa"
      "Oasis Info"   → "oasis-info"
      "A  B--C"      → "a-b-c"
      "  hola  "     → "hola"
    """
    slug = label.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "categoria"


async def _ensure_unique_slug(
    conn: aiosqlite.Connection,
    base_slug: str,
) -> str:
    """
    Devuelve base_slug si no existe en route_categories;
    si existe, añade sufijo -2, -3, etc. hasta encontrar uno libre (EC-CAT04).
    """
    candidate = base_slug
    counter = 2
    while True:
        rows = await conn.execute_fetchall(
            "SELECT 1 FROM route_categories WHERE slug = ?",
            (candidate,),
        )
        if not rows:
            return candidate
        candidate = f"{base_slug}-{counter}"
        counter += 1


# ---------------------------------------------------------------------------
# Adaptador
# ---------------------------------------------------------------------------

class RouteCategorySQLiteAdapter(RouteCategoryDbPort):
    """
    Implementa RouteCategoryDbPort con aiosqlite.
    Comparte la misma conexión SQLite (WAL) que el resto de adaptadores.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def ensure_tables(self) -> None:
        """
        M-CAT01: Crea la tabla route_categories si no existe.
        M-CAT02: Inserta la categoría default 'uncategorized' si no existe.
        Idempotente (CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE).

        Spec route-categories-dynamic.md §9.1, §14 Paso 5.
        """
        await self._conn.execute(_CREATE_ROUTE_CATEGORIES)
        await self._conn.execute(_CREATE_IDX_ROUTE_CATEGORIES_SLUG)
        await self._conn.commit()

        # M-CAT02: seed de uncategorized
        await self._conn.execute(
            """
            INSERT OR IGNORE INTO route_categories
                (slug, label, label_lower, color, is_default, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("uncategorized", "Sin categoría", "sin categoría", None, 1, _now_iso()),
        )
        await self._conn.commit()
        logger.debug("RouteCategorySQLiteAdapter: tablas y seed 'uncategorized' asegurados")

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    async def list_categories(self) -> list[RouteCategory]:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, slug, label, color, is_default, created_at
              FROM route_categories
             ORDER BY is_default DESC, created_at ASC
            """
        )
        return [_row_to_category(r) for r in rows]

    async def get_category(self, slug: str) -> RouteCategory | None:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, slug, label, color, is_default, created_at
              FROM route_categories
             WHERE slug = ?
            """,
            (slug,),
        )
        if not rows:
            return None
        return _row_to_category(rows[0])

    async def get_category_by_label_lower(self, label_lower: str) -> RouteCategory | None:
        rows = await self._conn.execute_fetchall(
            """
            SELECT id, slug, label, color, is_default, created_at
              FROM route_categories
             WHERE label_lower = ?
            """,
            (label_lower,),
        )
        if not rows:
            return None
        return _row_to_category(rows[0])

    # ------------------------------------------------------------------
    # Creación
    # ------------------------------------------------------------------

    async def create_category(
        self,
        slug: str,
        label: str,
        label_lower: str,
        color: str | None,
        is_default: bool,
    ) -> RouteCategory:
        now = _now_iso()
        try:
            await self._conn.execute(
                """
                INSERT INTO route_categories
                    (slug, label, label_lower, color, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (slug, label, label_lower, color, int(is_default), now),
            )
            await self._conn.commit()
        except Exception as exc:
            exc_str = str(exc).upper()
            if "UNIQUE" in exc_str:
                raise ValueError(
                    "Ya existe una categoría con este slug o nombre."
                ) from exc
            raise

        cat = await self.get_category(slug)
        assert cat is not None  # acabamos de insertarla
        return cat

    # ------------------------------------------------------------------
    # Actualización
    # ------------------------------------------------------------------

    async def update_category(
        self,
        slug: str,
        label: str | None = None,
        label_lower: str | None = None,
        color: "_UnsetType | str | None" = UNSET,
    ) -> RouteCategory:
        existing = await self.get_category(slug)
        if existing is None:
            raise ValueError(f"Categoría '{slug}' no encontrada.")

        new_label = label if label is not None else existing.label
        new_label_lower = label_lower if label_lower is not None else existing.label.strip().lower()

        # Determinar nuevo color: UNSET → conservar actual; None → quitar; str → actualizar
        if isinstance(color, _UnsetType):
            new_color = existing.color
        else:
            new_color = color  # puede ser None (explícito) o str

        try:
            await self._conn.execute(
                """
                UPDATE route_categories
                   SET label = ?, label_lower = ?, color = ?
                 WHERE slug = ?
                """,
                (new_label, new_label_lower, new_color, slug),
            )
            await self._conn.commit()
        except Exception as exc:
            exc_str = str(exc).upper()
            if "UNIQUE" in exc_str:
                raise ValueError(
                    "Ya existe una categoría con este nombre."
                ) from exc
            raise

        updated = await self.get_category(slug)
        assert updated is not None
        return updated

    # ------------------------------------------------------------------
    # Borrado con reasignación atómica
    # ------------------------------------------------------------------

    async def delete_category_and_reassign(self, slug: str) -> tuple[str, int]:
        """
        Transacción atómica (EC-CAT06/EC-CAT07):
        1. Verificar que existe y no es default.
        2. UPDATE route_templates: category_slug → 'uncategorized'.
        3. UPDATE noise_destinations: category_slug → 'uncategorized'.
        4. DELETE route_categories.
        Devuelve (slug, n_reasignados).
        """
        cat = await self.get_category(slug)
        if cat is None:
            raise ValueError(f"Categoría '{slug}' no encontrada.")
        if cat.is_default:
            raise ValueError("La categoría por defecto no se puede borrar.")

        # Verificar si noise_destinations usa category_slug o category (retrocompat)
        nd_col = await self._get_noise_destinations_category_column()

        await self._conn.execute("BEGIN")
        try:
            # UPDATE route_templates
            cursor_rt = await self._conn.execute(
                "UPDATE route_templates SET category_slug = 'uncategorized' WHERE category_slug = ?",
                (slug,),
            )
            n_templates = cursor_rt.rowcount

            # UPDATE noise_destinations (columna puede variar)
            cursor_nd = await self._conn.execute(
                f"UPDATE noise_destinations SET {nd_col} = 'uncategorized' WHERE {nd_col} = ?",
                (slug,),
            )
            n_destinations = cursor_nd.rowcount

            # DELETE categoría
            await self._conn.execute(
                "DELETE FROM route_categories WHERE slug = ?",
                (slug,),
            )

            await self._conn.execute("COMMIT")
        except Exception:
            await self._conn.execute("ROLLBACK")
            raise

        return (slug, n_templates + n_destinations)

    async def _get_noise_destinations_category_column(self) -> str:
        """
        Devuelve 'category_slug' si noise_destinations ya fue migrada (M-CAT04),
        o 'category' si aún tiene el esquema viejo.
        Necesario para retrocompatibilidad durante la migración.
        """
        rows = await self._conn.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='noise_destinations'",
        )
        if not rows:
            return "category_slug"  # tabla no existe — no afecta al DELETE

        cursor = await self._conn.execute("PRAGMA table_info(noise_destinations)")
        cols = {row[1] for row in await cursor.fetchall()}
        return "category_slug" if "category_slug" in cols else "category"
