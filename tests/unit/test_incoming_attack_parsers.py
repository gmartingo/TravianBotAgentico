"""
Tests del radar de ataques entrantes — parsers y modelo de datos.

Cubre:
  Componente A — IncomingAttackSidebarParser:
    UT-RA01..UT-RA08 (parser del sidebar)

  Componente B — Dorf1IncomingParser:
    UT-RB01..UT-RB06 (parser de dorf1)

  Modelo de datos / BD (integración SQLite en memoria):
    UT-RD01..UT-RD07

Ver spec docs/specs/radar-ataques-entrantes.md §12.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent

import aiosqlite
import pytest

from adapters.browser.parsers.incoming_attack_sidebar_parser import (
    IncomingAttackSidebarParser,
)
from adapters.browser.parsers._common import parse_coord as _parse_coord
from adapters.browser.parsers.dorf1_incoming_parser import Dorf1IncomingParser
from adapters.db.incoming_attack_sqlite_adapter import IncomingAttackSQLiteAdapter
from core.dtos.incoming_attack_dto import VillageUnderAttackDTO, Dorf1AttackDTO
from core.ports.incoming_attack_db_port import IncomingAttackRecord

# ---------------------------------------------------------------------------
# Rutas a los fixtures
# ---------------------------------------------------------------------------

_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "incoming_attacks"
)

_SIDEBAR_WITH_ATTACK    = _FIXTURES_DIR / "sidebar_with_attack.html"
_SIDEBAR_WITHOUT_ATTACK = _FIXTURES_DIR / "sidebar_without_attack.html"
_DORF1_WITH_INCOMING    = _FIXTURES_DIR / "dorf1_with_incoming.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ===========================================================================
# COMPONENTE A — IncomingAttackSidebarParser
# ===========================================================================

class TestSidebarParser:

    # UT-RA01: detecta data-did=27322, nombre "07", coords (-68, 73)
    def test_ra01_detects_attacked_village(self):
        html = _read(_SIDEBAR_WITH_ATTACK)
        results = IncomingAttackSidebarParser.parse(html)
        assert len(results) == 1
        dto = results[0]
        assert dto.village_game_id == 27322
        assert dto.village_name == "07"
        assert dto.coord_x == -68
        assert dto.coord_y == 73

    # UT-RA02: NO detecta data-did=24341 (clase "listEntry village active", sin "attack")
    def test_ra02_does_not_detect_active_without_attack_class(self):
        html = _read(_SIDEBAR_WITH_ATTACK)
        results = IncomingAttackSidebarParser.parse(html)
        game_ids = [d.village_game_id for d in results]
        assert 24341 not in game_ids

    # UT-RA03: con sidebar sin-ataque → lista vacía aunque TODAS tengan svg.attack
    def test_ra03_no_attacks_when_no_attack_class_on_div(self):
        html = _read(_SIDEBAR_WITHOUT_ATTACK)
        results = IncomingAttackSidebarParser.parse(html)
        assert results == []

    # UT-RA04: HTML sin #sidebarBoxVillageList → lista vacía sin excepción
    def test_ra04_no_sidebar_element_returns_empty(self):
        html = "<html><body><p>Página de login</p></body></html>"
        results = IncomingAttackSidebarParser.parse(html)
        assert results == []

    # UT-RA05: div.listEntry.village.attack sin data-did → lista vacía (+ WARNING en log)
    def test_ra05_attack_div_without_data_did_is_skipped(self):
        html = dedent("""
            <div id="sidebarBoxVillageList">
              <div class="listEntry village attack">
                <span class="name">SinDid</span>
                <span class="coordinateX">(5</span>
                <span class="coordinateY">10)</span>
              </div>
            </div>
        """)
        results = IncomingAttackSidebarParser.parse(html)
        assert results == []

    # UT-RA06: span.coordinateX con texto "(−63" (guion unicode) → coord_x = -63
    def test_ra06_unicode_minus_in_coord_parses_correctly(self):
        html = dedent("""
            <div id="sidebarBoxVillageList">
              <div class="listEntry village attack" data-did="999">
                <span class="name">Test</span>
                <span class="coordinateX">(−63</span>
                <span class="coordinateY">25)</span>
              </div>
            </div>
        """)
        results = IncomingAttackSidebarParser.parse(html)
        assert len(results) == 1
        assert results[0].coord_x == -63
        assert results[0].coord_y == 25

    # UT-RA07: SEÑUELO — svg.attack en span.incomingTroops presente en TODAS las entradas
    # pero solo una tiene clase "attack" en div.listEntry → solo esa se detecta
    def test_ra07_svg_attack_decoy_does_not_generate_false_positive(self):
        """
        El señuelo svg.attack dentro de span.incomingTroops está presente en TODAS
        las entradas (confirmado GAP-01). Solo la que tiene clase 'attack' en el
        div.listEntry debe detectarse. Las demás, aunque tengan el señuelo, NO.
        """
        html = dedent("""
            <div id="sidebarBoxVillageList">

              <!-- Atacada: clase 'attack' en div.listEntry -->
              <div class="listEntry village attack" data-did="100">
                <span class="name">Attacked</span>
                <span class="coordinateX">(1</span>
                <span class="coordinateY">2)</span>
                <span class="incomingTroops">
                  <svg class="attack"></svg>
                </span>
              </div>

              <!-- No atacada: sin clase 'attack' en div.listEntry, pero con señuelo -->
              <div class="listEntry village" data-did="200">
                <span class="name">Safe1</span>
                <span class="coordinateX">(3</span>
                <span class="coordinateY">4)</span>
                <span class="incomingTroops">
                  <svg class="attack"></svg>
                </span>
              </div>

              <!-- No atacada: activa, sin clase 'attack' en div.listEntry, con señuelo -->
              <div class="listEntry village active" data-did="300">
                <span class="name">Safe2</span>
                <span class="coordinateX">(5</span>
                <span class="coordinateY">6)</span>
                <span class="incomingTroops">
                  <svg class="attack"></svg>
                </span>
              </div>

            </div>
        """)
        results = IncomingAttackSidebarParser.parse(html)
        assert len(results) == 1
        assert results[0].village_game_id == 100
        # Confirmar que los señuelos no generaron falsos positivos
        game_ids = [d.village_game_id for d in results]
        assert 200 not in game_ids
        assert 300 not in game_ids

    # UT-RA08: svg.handle (drag-handle presente en todas) → NO genera falso positivo
    def test_ra08_svg_handle_does_not_generate_false_positive(self):
        """
        El svg.handle (drag-handle en div.dragAndDrop) está en TODAS las entradas.
        Ninguna tiene clase 'attack' en div.listEntry → lista vacía.
        """
        html = dedent("""
            <div id="sidebarBoxVillageList">

              <div class="listEntry village" data-did="10">
                <div class="dragAndDrop">
                  <svg class="handle"></svg>
                </div>
                <span class="name">A</span>
                <span class="coordinateX">(1</span>
                <span class="coordinateY">2)</span>
              </div>

              <div class="listEntry village active" data-did="20">
                <div class="dragAndDrop">
                  <svg class="handle"></svg>
                </div>
                <span class="name">B</span>
                <span class="coordinateX">(3</span>
                <span class="coordinateY">4)</span>
              </div>

            </div>
        """)
        results = IncomingAttackSidebarParser.parse(html)
        assert results == []

    # Test auxiliar: _parse_coord funciona con texto sin coordenada
    def test_parse_coord_returns_zero_for_none_element(self):
        assert _parse_coord(None) == 0

    # Test auxiliar: _parse_coord con texto sin dígitos
    def test_parse_coord_returns_zero_when_no_digits(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<span>abc</span>", "html.parser")
        el = soup.select_one("span")
        assert _parse_coord(el) == 0


# ===========================================================================
# COMPONENTE B — Dorf1IncomingParser
# ===========================================================================

class TestDorf1Parser:

    # UT-RB01: detecta 1 ataque, attack_count=1, seconds_to_impact=1818
    def test_rb01_detects_one_incoming_attack(self):
        html = _read(_DORF1_WITH_INCOMING)
        results = Dorf1IncomingParser.parse(html)
        assert len(results) == 1
        dto = results[0]
        assert dto.attack_count == 1
        assert dto.seconds_to_impact == 1818

    # UT-RB02: NO detecta el ataque saliente (img.att2)
    def test_rb02_ignores_outgoing_attack(self):
        html = _read(_DORF1_WITH_INCOMING)
        results = Dorf1IncomingParser.parse(html)
        # Solo debe haber 1 resultado (el entrante), no 2
        assert len(results) == 1

    # UT-RB01 bis: rally_point_href contiene 'gid=16'
    def test_rb01_rally_point_href_contains_gid16(self):
        html = _read(_DORF1_WITH_INCOMING)
        results = Dorf1IncomingParser.parse(html)
        assert len(results) == 1
        assert "gid=16" in results[0].rally_point_href

    # UT-RB03: sin bloque troopMovements → lista vacía
    def test_rb03_no_movements_returns_empty(self):
        html = "<html><body><div id='content'></div></body></html>"
        results = Dorf1IncomingParser.parse(html)
        assert results == []

    # UT-RB04: span.timer sin value ni data-value → lista vacía + loggea WARNING
    def test_rb04_timer_without_value_attributes_is_skipped(self):
        html = dedent("""
            <html><body>
            <table>
              <tbody>
                <tr>
                  <td><a href="build.php?gid=16&tt=1">
                    <img class="att1">
                  </a></td>
                </tr>
                <tr>
                  <td><span class="timer">30:00</span></td>
                  <td><span class="a1">1 Attack</span></td>
                </tr>
              </tbody>
            </table>
            </body></html>
        """)
        results = Dorf1IncomingParser.parse(html)
        assert results == []

    # UT-RB05: span.a1 con texto "114 Attacks" → attack_count=114
    def test_rb05_attack_count_parses_from_span_a1(self):
        html = dedent("""
            <html><body>
            <table>
              <tbody>
                <tr>
                  <td><a href="build.php?gid=16&tt=1">
                    <img class="att1">
                  </a></td>
                </tr>
                <tr>
                  <td><span class="timer" value="500" data-value="500">8:20</span></td>
                  <td><span class="a1">114 Attacks</span></td>
                </tr>
              </tbody>
            </table>
            </body></html>
        """)
        results = Dorf1IncomingParser.parse(html)
        assert len(results) == 1
        assert results[0].attack_count == 114

    # UT-RB06: span.a1 con texto no numérico → attack_count=1 (fallback)
    def test_rb06_attack_count_fallback_when_no_digits(self):
        html = dedent("""
            <html><body>
            <table>
              <tbody>
                <tr>
                  <td><a href="build.php?gid=16&tt=1">
                    <img class="att1">
                  </a></td>
                </tr>
                <tr>
                  <td><span class="timer" value="300" data-value="300">5:00</span></td>
                  <td><span class="a1">Ataques</span></td>
                </tr>
              </tbody>
            </table>
            </body></html>
        """)
        results = Dorf1IncomingParser.parse(html)
        assert len(results) == 1
        assert results[0].attack_count == 1

    # Extra: data-value como fallback cuando value no está
    def test_rb_data_value_fallback(self):
        html = dedent("""
            <html><body>
            <table>
              <tbody>
                <tr>
                  <td><a href="build.php?gid=16&tt=1">
                    <img class="att1">
                  </a></td>
                </tr>
                <tr>
                  <td><span class="timer" data-value="999">16:39</span></td>
                  <td><span class="a1">1 Attack</span></td>
                </tr>
              </tbody>
            </table>
            </body></html>
        """)
        results = Dorf1IncomingParser.parse(html)
        assert len(results) == 1
        assert results[0].seconds_to_impact == 999


# ===========================================================================
# MODELO DE DATOS / BD — IncomingAttackSQLiteAdapter (integración, SQLite en memoria)
# ===========================================================================

async def _make_adapter() -> tuple[IncomingAttackSQLiteAdapter, aiosqlite.Connection]:
    """Crea un adaptador con BD en memoria y las tablas necesarias."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    # Habilitar FK enforcement (necesario para ON DELETE CASCADE)
    await conn.execute("PRAGMA foreign_keys = ON")
    # Crear la tabla worlds (FK requerida por incoming_attacks)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS worlds (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL DEFAULT 1,
            server     TEXT    NOT NULL DEFAULT 'ts1.travian.es',
            created_at TEXT    NOT NULL DEFAULT '2026-01-01T00:00:00'
        )
    """)
    await conn.execute("INSERT INTO worlds (id, account_id, server, created_at) VALUES (1, 1, 'ts1.travian.es', '2026-01-01')")
    await conn.commit()

    adapter = IncomingAttackSQLiteAdapter(conn)
    await adapter.ensure_tables()
    return adapter, conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _future_iso(seconds: int = 1818) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _past_iso(seconds: int = 100) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


class TestIncomingAttackSQLiteAdapter:

    # UT-RD01: upsert con datos mínimos → inserción OK, id devuelto
    def test_rd01_upsert_minimal_inserts_ok(self):
        async def _run():
            adapter, conn = await _make_adapter()
            try:
                now = _now_iso()
                record = IncomingAttackRecord(
                    world_id=1,
                    village_game_id=27322,
                    source="sidebar",
                    detected_at=now,
                    updated_at=now,
                    impact_at=None,
                )
                row_id = await adapter.upsert_attack(record)
                assert isinstance(row_id, int)
                assert row_id > 0
            finally:
                await conn.close()
        asyncio.run(_run())

    # UT-RD02: segundo upsert con misma clave → actualización, no duplicado
    def test_rd02_duplicate_upsert_updates_not_inserts(self):
        async def _run():
            adapter, conn = await _make_adapter()
            try:
                now = _now_iso()
                future = _future_iso(1818)
                record1 = IncomingAttackRecord(
                    world_id=1,
                    village_game_id=27322,
                    source="sidebar",
                    detected_at=now,
                    updated_at=now,
                    impact_at=future,
                    attack_count=1,
                )
                await adapter.upsert_attack(record1)

                # Segundo upsert con la misma clave pero attack_count=5
                record2 = IncomingAttackRecord(
                    world_id=1,
                    village_game_id=27322,
                    source="dorf1",
                    detected_at=now,
                    updated_at=now,
                    impact_at=future,
                    attack_count=5,
                )
                await adapter.upsert_attack(record2)

                # Verificar que solo hay 1 fila
                result = await adapter.list_attacks(world_id=1, include_past=True)
                assert result["total"] == 1
                assert result["items"][0]["attack_count"] == 5
            finally:
                await conn.close()
        asyncio.run(_run())

    # UT-RD03: list_attacks(include_past=False) → solo impact_at > now()
    def test_rd03_list_attacks_pending_only(self):
        async def _run():
            adapter, conn = await _make_adapter()
            try:
                now = _now_iso()
                future = _future_iso(1818)
                past = _past_iso(100)

                # Ataque futuro (pendiente)
                r1 = IncomingAttackRecord(
                    world_id=1, village_game_id=100,
                    impact_at=future, source="dorf1",
                    detected_at=now, updated_at=now,
                )
                await adapter.upsert_attack(r1)

                # Ataque pasado (ya impactó)
                r2 = IncomingAttackRecord(
                    world_id=1, village_game_id=200,
                    impact_at=past, source="dorf1",
                    detected_at=now, updated_at=now,
                )
                await adapter.upsert_attack(r2)

                result = await adapter.list_attacks(world_id=1, include_past=False)
                assert result["total"] == 1
                assert result["items"][0]["village_game_id"] == 100
            finally:
                await conn.close()
        asyncio.run(_run())

    # UT-RD04: list_attacks(include_past=True) → incluye todas
    def test_rd04_list_attacks_include_past(self):
        async def _run():
            adapter, conn = await _make_adapter()
            try:
                now = _now_iso()
                r1 = IncomingAttackRecord(
                    world_id=1, village_game_id=100,
                    impact_at=_future_iso(), source="dorf1",
                    detected_at=now, updated_at=now,
                )
                r2 = IncomingAttackRecord(
                    world_id=1, village_game_id=200,
                    impact_at=_past_iso(), source="dorf1",
                    detected_at=now, updated_at=now,
                )
                await adapter.upsert_attack(r1)
                await adapter.upsert_attack(r2)

                result = await adapter.list_attacks(world_id=1, include_past=True)
                assert result["total"] == 2
            finally:
                await conn.close()
        asyncio.run(_run())

    # UT-RD05: borrar el mundo → CASCADE elimina incoming_attacks
    def test_rd05_cascade_delete_on_world_delete(self):
        async def _run():
            adapter, conn = await _make_adapter()
            try:
                now = _now_iso()
                r = IncomingAttackRecord(
                    world_id=1, village_game_id=27322,
                    source="sidebar", detected_at=now, updated_at=now,
                )
                await adapter.upsert_attack(r)

                # Verificar que hay 1 fila antes de borrar
                before = await adapter.list_attacks(world_id=1, include_past=True)
                assert before["total"] == 1

                # Borrar el mundo (FK ON DELETE CASCADE)
                await conn.execute("DELETE FROM worlds WHERE id = 1")
                await conn.commit()

                # La tabla debe quedar vacía
                async with conn.execute("SELECT COUNT(*) AS cnt FROM incoming_attacks") as cur:
                    row = await cur.fetchone()
                assert row["cnt"] == 0
            finally:
                await conn.close()
        asyncio.run(_run())

    # UT-RD06: list_attacks(village_game_id=X) → solo filas de esa aldea
    def test_rd06_filter_by_village_game_id(self):
        async def _run():
            adapter, conn = await _make_adapter()
            try:
                now = _now_iso()
                r1 = IncomingAttackRecord(
                    world_id=1, village_game_id=100,
                    impact_at=_future_iso(1000), source="dorf1",
                    detected_at=now, updated_at=now,
                )
                r2 = IncomingAttackRecord(
                    world_id=1, village_game_id=200,
                    impact_at=_future_iso(2000), source="dorf1",
                    detected_at=now, updated_at=now,
                )
                await adapter.upsert_attack(r1)
                await adapter.upsert_attack(r2)

                result = await adapter.list_attacks(world_id=1, village_game_id=100)
                assert result["total"] == 1
                assert result["items"][0]["village_game_id"] == 100
            finally:
                await conn.close()
        asyncio.run(_run())

    # UT-RD07: upsert con impact_at=None → inserción OK (campo nullable)
    def test_rd07_upsert_with_null_impact_at(self):
        async def _run():
            adapter, conn = await _make_adapter()
            try:
                now = _now_iso()
                record = IncomingAttackRecord(
                    world_id=1,
                    village_game_id=27322,
                    source="sidebar",
                    detected_at=now,
                    updated_at=now,
                    impact_at=None,  # sidebar no tiene timer
                )
                row_id = await adapter.upsert_attack(record)
                assert row_id > 0

                # Verificar que impact_at es NULL en BD
                result = await adapter.list_attacks(world_id=1, include_past=True)
                assert result["total"] == 1
                assert result["items"][0]["impact_at"] is None
            finally:
                await conn.close()
        asyncio.run(_run())

    # UT-RD07 bis: filas con impact_at=None se muestran como "pendientes" (RT-05)
    def test_rd07b_null_impact_at_included_in_pending_list(self):
        async def _run():
            adapter, conn = await _make_adapter()
            try:
                now = _now_iso()
                record = IncomingAttackRecord(
                    world_id=1, village_game_id=27322,
                    source="sidebar", detected_at=now, updated_at=now,
                    impact_at=None,
                )
                await adapter.upsert_attack(record)

                # include_past=False debe mostrar las filas sin timer (postura conservadora)
                result = await adapter.list_attacks(world_id=1, include_past=False)
                assert result["total"] == 1
            finally:
                await conn.close()
        asyncio.run(_run())


# ===========================================================================
# Use case — _calc_seconds_remaining
# ===========================================================================

class TestCalcSecondsRemaining:

    def test_none_impact_at_returns_none(self):
        from core.use_cases.incoming_attack_use_cases import _calc_seconds_remaining
        assert _calc_seconds_remaining(None) is None

    def test_future_impact_at_returns_positive(self):
        from core.use_cases.incoming_attack_use_cases import _calc_seconds_remaining
        future = (datetime.now(timezone.utc) + timedelta(seconds=1818)).isoformat()
        result = _calc_seconds_remaining(future)
        assert result is not None
        assert result > 0
        assert result <= 1818

    def test_past_impact_at_returns_zero(self):
        from core.use_cases.incoming_attack_use_cases import _calc_seconds_remaining
        past = (datetime.now(timezone.utc) - timedelta(seconds=100)).isoformat()
        result = _calc_seconds_remaining(past)
        assert result == 0

    def test_invalid_iso_returns_none(self):
        from core.use_cases.incoming_attack_use_cases import _calc_seconds_remaining
        result = _calc_seconds_remaining("not-a-date")
        assert result is None


# ===========================================================================
# WorldAgent — invocación del hook tras tarea de browser (§9.5, RN-21)
# ===========================================================================

class TestWorldAgentPageHookWiring:
    """
    Verifica que _post_page_hook se invoca desde _execute tras cada tarea de
    browser post-login (SEND_FARM_LIST_GROUP, NOISE_NAVIGATION) y que NO se
    invoca tras CHECK_INCOMING_ATTACK_DETAIL (evita re-entrada del radar).

    El WorldAgent se construye con stubs mínimos:
      - browser / db: objetos con los métodos mínimos que usa el agente.
      - page_html_provider: async callable que devuelve un HTML de prueba.
      - sidebar_attack_hook: async callable espiado para verificar invocaciones.

    No toca la BD, no toca el browser real, no hay asyncio.run de bucles.
    """

    def _make_agent(self, hook_calls: list, provider_html: str | None = "<html/>"):
        """
        Construye un WorldAgent con stubs para tests de invocación de hook.

        hook_calls — lista mutable donde se acumularán los HTML recibidos por
                     el sidebar_attack_hook (permite aserciones fuera del async).
        provider_html — HTML que devuelve el page_html_provider.
        """
        from unittest.mock import AsyncMock, MagicMock

        from core.scheduling.world_agent import WorldAgent
        from core.entities.task import Task, TaskType

        # Stub de FarmListBrowserPort y FarmListDbPort
        browser_mock = AsyncMock()
        db_mock = AsyncMock()

        # Stub del SendSchedulerGroupUseCase usado internamente por WorldAgent
        # Necesitamos que _send_group.execute no falle.
        send_group_mock = AsyncMock()

        # page_html_provider — devuelve un HTML fijo
        async def _provider():
            return provider_html

        # sidebar_attack_hook espiado — registra llamadas y devuelve []
        async def _hook(html, world_id, db_port):
            hook_calls.append(html)
            return []

        # incoming_db stub mínimo para que _post_page_hook no haga early return
        incoming_db_mock = MagicMock()

        agent = WorldAgent(
            world_id=1,
            browser=browser_mock,
            db=db_mock,
            incoming_db=incoming_db_mock,
            sidebar_attack_hook=_hook,
            page_html_provider=_provider,
        )
        # Reemplazar _send_group con el mock para que execute no falle
        agent._send_group = send_group_mock
        return agent

    def test_hook_invoked_after_send_farm_list_group(self):
        """
        Tras SEND_FARM_LIST_GROUP el hook se invoca UNA VEZ con el HTML del provider.
        """
        from core.entities.task import Task, TaskType

        async def _run():
            calls = []
            agent = self._make_agent(calls, provider_html="<html>farm page</html>")
            task = Task(
                task_type=TaskType.SEND_FARM_LIST_GROUP,
                world_id=1,
                execute_at=datetime.now(),
                priority=1,
                payload={"scheduler_id": 42, "scheduler_type": "farm"},
                recurring=False,
                source_scheduler_id=42,
            )
            await agent._execute(task)
            assert len(calls) == 1
            assert calls[0] == "<html>farm page</html>"

        asyncio.run(_run())

    def test_hook_not_invoked_after_check_incoming_attack_detail(self):
        """
        CHECK_INCOMING_ATTACK_DETAIL NO debe invocar el hook (evita re-entrada).
        """
        from core.entities.task import Task, TaskType

        async def _run():
            calls = []
            agent = self._make_agent(calls, provider_html="<html>dorf1</html>")
            # incoming_db y dorf1_attack_reader ausentes → _handle_check retorna inmediatamente
            agent._dorf1_attack_reader = None

            task = Task(
                task_type=TaskType.CHECK_INCOMING_ATTACK_DETAIL,
                world_id=1,
                execute_at=datetime.now(),
                priority=0,
                payload={},
                recurring=False,
                source_scheduler_id=None,
            )
            await agent._execute(task)
            assert calls == [], (
                "El hook NO debe invocarse tras CHECK_INCOMING_ATTACK_DETAIL "
                "(previene re-entrada del radar)"
            )

        asyncio.run(_run())

    def test_hook_not_invoked_when_provider_is_none(self):
        """
        Sin page_html_provider, el hook nunca se llama aunque sidebar_attack_hook esté.
        """
        from unittest.mock import AsyncMock, MagicMock
        from core.scheduling.world_agent import WorldAgent
        from core.entities.task import Task, TaskType

        async def _run():
            calls = []

            async def _hook(html, world_id, db_port):
                calls.append(html)
                return []

            browser_mock = AsyncMock()
            db_mock = AsyncMock()
            send_group_mock = AsyncMock()
            incoming_db_mock = MagicMock()

            agent = WorldAgent(
                world_id=1,
                browser=browser_mock,
                db=db_mock,
                incoming_db=incoming_db_mock,
                sidebar_attack_hook=_hook,
                page_html_provider=None,   # NO hay provider
            )
            agent._send_group = send_group_mock

            task = Task(
                task_type=TaskType.SEND_FARM_LIST_GROUP,
                world_id=1,
                execute_at=datetime.now(),
                priority=1,
                payload={"scheduler_id": 1, "scheduler_type": "farm"},
                recurring=False,
                source_scheduler_id=1,
            )
            await agent._execute(task)
            assert calls == []

        asyncio.run(_run())

    def test_hook_provider_exception_does_not_crash_task(self):
        """
        Si page_html_provider lanza, la tarea principal debe completarse igualmente.
        """
        from unittest.mock import AsyncMock, MagicMock
        from core.scheduling.world_agent import WorldAgent
        from core.entities.task import Task, TaskType

        async def _run():
            async def _failing_provider():
                raise RuntimeError("tab caído")

            browser_mock = AsyncMock()
            db_mock = AsyncMock()
            send_group_mock = AsyncMock()
            incoming_db_mock = MagicMock()

            agent = WorldAgent(
                world_id=1,
                browser=browser_mock,
                db=db_mock,
                incoming_db=incoming_db_mock,
                sidebar_attack_hook=None,
                page_html_provider=_failing_provider,
            )
            agent._send_group = send_group_mock

            task = Task(
                task_type=TaskType.SEND_FARM_LIST_GROUP,
                world_id=1,
                execute_at=datetime.now(),
                priority=1,
                payload={"scheduler_id": 1, "scheduler_type": "farm"},
                recurring=False,
                source_scheduler_id=1,
            )
            # No debe lanzar — el provider falla pero la tarea termina OK
            await agent._execute(task)
            # Si llegamos aquí sin excepción, la tarea no fue tumbada

        asyncio.run(_run())
