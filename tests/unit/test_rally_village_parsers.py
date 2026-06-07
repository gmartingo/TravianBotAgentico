"""
Tests del radar de ataques entrantes — Componentes C y D.

Cubre:
  Componente C — RallyPointParser:
    UT-RC01..UT-RC09 (parser del rally point)

  Componente D — VillageProfileParser:
    UT-RD01P..UT-RD08P (parser de la ficha de aldea)

  Mapeo tribu por uNN (RN-26):
    Pruebas de unit_class_to_tribe_ordinal para las unidades del fixture.

  Métodos adicionales de BD (§9.11):
    UT-RDB01..UT-RDB03 (get_attack_by_id, update_snapshot, summary_by_world)

Ver spec docs/specs/radar-ataques-entrantes.md §12.
GAP-02 y GAP-03 cerrados — fixtures reales disponibles (v4, 2026-06-07).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import aiosqlite
import pytest

from adapters.browser.parsers.rally_point_parser import (
    RallyPointParser,
    TRIBE_BY_VILLAGE_CLASS,
)
from adapters.browser.parsers.village_profile_parser import VillageProfileParser
from adapters.db.incoming_attack_sqlite_adapter import IncomingAttackSQLiteAdapter
from core.dtos.incoming_attack_dto import RallyPointAttackDTO, VillageProfileDTO
from core.ports.incoming_attack_db_port import IncomingAttackRecord
from core.utils.units import unit_class_to_tribe_ordinal

# ---------------------------------------------------------------------------
# Rutas a los fixtures
# ---------------------------------------------------------------------------

_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "incoming_attacks"
)

_TROOP_DETAILS = _FIXTURES_DIR / "troop_details_in_attack.html"
_KARTE_TILE    = _FIXTURES_DIR / "karte_tile_attacker_dialog.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ===========================================================================
# COMPONENTE C — RallyPointParser
# ===========================================================================

class TestRallyPointParser:
    """Tests UT-RC01..UT-RC09 del parser del rally point."""

    def setup_method(self):
        """Parsea el fixture real una sola vez por clase de test."""
        self._html = _read(_TROOP_DETAILS)
        self._results = RallyPointParser.parse(self._html)
        assert len(self._results) == 1, "El fixture debe tener exactamente 1 tabla inAttack"
        self._dto: RallyPointAttackDTO = self._results[0]

    # UT-RC01: attacker_name y origin_village_href
    def test_rc01_attacker_name_and_href(self):
        assert self._dto.attacker_name == "GonnaDie"
        assert self._dto.origin_village_href == "/karte.php?d=49454"

    # UT-RC02: timer y hora display
    def test_rc02_timer_and_display(self):
        assert self._dto.seconds_to_impact == 2258
        assert self._dto.impact_at_display is not None
        assert "09:31:38" in self._dto.impact_at_display

    # UT-RC03: tribu derivada de u22 (primera unidad con count>0 es u22 → GAULS)
    def test_rc03_tribe_gauls_from_u22(self):
        # u21 tiene count=0, u22 tiene count=2 → primera con count>0 es u22 → gauls
        assert self._dto.tribe == "gauls"

    # UT-RC04: troops dict — u22=2, u21=0
    def test_rc04_troops_dict(self):
        assert self._dto.troops.get("u22") == 2
        assert self._dto.troops.get("u21") == 0

    # UT-RC05: operation_type=attack para tropas no-spy
    def test_rc05_operation_type_attack(self):
        assert self._dto.operation_type == "attack"

    # UT-RC06: operation_type=spy si SOLO hay explorador (u3 ordinal 3 en romans)
    def test_rc06_spy_operation_type(self):
        html = dedent("""
            <table class="troop_details inAttack">
              <thead>
                <tr>
                  <td class="role"><a href="/karte.php?d=50664">01</a></td>
                  <td class="troopHeadline">
                    <a href="/karte.php?d=99999">Scout attacks 02</a>
                  </td>
                </tr>
              </thead>
              <tbody class="units">
                <tr>
                  <th class="coords">
                    <span class="coordinates coordinatesWrapper">
                      <span class="coordinateX">(10</span>
                      <span class="coordinateY">20)</span>
                    </span>
                  </th>
                  <td class="uniticon"><a><img class="unit u1" alt="Legionnaire"></a></td>
                  <td class="uniticon"><a><img class="unit u2" alt="Praetorian"></a></td>
                  <td class="uniticon"><a><img class="unit u3" alt="Imperian"></a></td>
                </tr>
              </tbody>
              <tbody class="units last">
                <tr>
                  <th>Troops</th>
                  <td class="unit none">0</td>
                  <td class="unit none">0</td>
                  <td class="unit">5</td>
                </tr>
              </tbody>
              <tbody class="infos">
                <tr>
                  <th>Arrival</th>
                  <td colspan="3">
                    <div class="in"><span class="timer" value="1000" data-value="1000">0:16:40</span></div>
                    <div class="at"><span>at 10:00:00</span></div>
                  </td>
                </tr>
              </tbody>
            </table>
        """)
        results = RallyPointParser.parse(html)
        assert len(results) == 1
        assert results[0].operation_type == "spy"

    # UT-RC07: HTML sin tabla → lista vacía (EC-11)
    def test_rc07_no_table_returns_empty(self):
        results = RallyPointParser.parse("<html><body>sin tabla</body></html>")
        assert results == []

    # UT-RC08: tabla sin troopHeadline <a> → lista vacía
    def test_rc08_table_without_headline_returns_empty(self):
        html = dedent("""
            <table class="troop_details inAttack">
              <thead>
                <tr>
                  <td class="role">sin_atacante</td>
                  <td class="troopHeadline">sin_link</td>
                </tr>
              </thead>
              <tbody class="units"><tr><th class="coords"></th></tr></tbody>
              <tbody class="units last"><tr><th>Troops</th></tr></tbody>
              <tbody class="infos"></tbody>
            </table>
        """)
        results = RallyPointParser.parse(html)
        assert results == []

    # UT-RC09: coordenadas de origen extraídas correctamente
    def test_rc09_origin_coords(self):
        assert self._dto.origin_village_coord_x == -63
        assert self._dto.origin_village_coord_y == 74


# ===========================================================================
# COMPONENTE D — VillageProfileParser
# ===========================================================================

class TestVillageProfileParser:
    """Tests UT-RD01P..UT-RD08P del parser de la ficha de aldea."""

    def setup_method(self):
        """Parsea el fixture real una sola vez por clase de test."""
        self._html = _read(_KARTE_TILE)
        self._dto: VillageProfileDTO | None = VillageProfileParser.parse(self._html)
        assert self._dto is not None, "El fixture debe dar un DTO válido"

    # UT-RD01P: nombre de aldea y coordenadas
    def test_rd01p_village_name_and_coords(self):
        assert self._dto.village_name == "01"
        assert self._dto.coord_x == -63
        assert self._dto.coord_y == 74

    # UT-RD02P: propietario (player_name y player_href)
    def test_rd02p_player_name_and_href(self):
        assert self._dto.player_name == "GonnaDie"
        assert self._dto.player_href == "/profile/392"

    # UT-RD03P: alianza (alliance_name y alliance_href)
    def test_rd03p_alliance_name_and_href(self):
        assert self._dto.alliance_name == "Storm"
        assert self._dto.alliance_href == "/alliance/4"

    # UT-RD04P: población
    def test_rd04p_population(self):
        assert self._dto.population == 692

    # UT-RD05P: tribu extraída de village-6 → TRIBE_BY_VILLAGE_CLASS
    def test_rd05p_tribe_from_village_class(self):
        # village-6 está en el fixture → debe mapear a algún valor de TRIBE_BY_VILLAGE_CLASS
        assert self._dto.tribe is not None
        assert self._dto.tribe == TRIBE_BY_VILLAGE_CLASS[6]

    # UT-RD06P: HTML sin div#tileDetails → retorna None (EC-12)
    def test_rd06p_no_tile_details_returns_none(self):
        result = VillageProfileParser.parse("<html><body>sin tileDetails</body></html>")
        assert result is None

    # UT-RD07P: div#tileDetails sin #village_info → nombre y coords del h1, resto None (EC-22)
    def test_rd07p_tile_without_village_info(self):
        html = dedent("""
            <div id="tileDetails" class="village village-3">
              <h1 class="titleInHeader">
                MiAldea
                <span class="coordinates coordinatesWrapper">
                  <span class="coordinateX">(5</span>
                  <span class="coordinateY">10)</span>
                </span>
              </h1>
            </div>
        """)
        dto = VillageProfileParser.parse(html)
        assert dto is not None
        assert dto.village_name == "MiAldea"
        assert dto.coord_x == 5
        assert dto.coord_y == 10
        assert dto.player_name is None
        assert dto.population is None

    # UT-RD08P: village-N con N no mapeado → tribe=None + WARNING (EC-20)
    def test_rd08p_unmapped_village_n_gives_none_tribe(self, caplog):
        import logging
        html = dedent("""
            <div id="tileDetails" class="village village-99">
              <h1 class="titleInHeader">
                TestVillage
                <span class="coordinates coordinatesWrapper">
                  <span class="coordinateX">(1</span>
                  <span class="coordinateY">2)</span>
                </span>
              </h1>
            </div>
        """)
        with caplog.at_level(logging.WARNING, logger="adapters.browser.parsers.village_profile_parser"):
            dto = VillageProfileParser.parse(html)
        assert dto is not None
        assert dto.tribe is None
        assert any("village-99" in record.message for record in caplog.records)


# ===========================================================================
# Mapeo tribu por uNN (RN-26)
# ===========================================================================

class TestUnitClassToTribeOrdinal:
    """Tests del mapeo unit_class → tribu para las unidades del fixture."""

    def test_u21_is_gauls_1(self):
        result = unit_class_to_tribe_ordinal("u21")
        assert result is not None
        tribe, ordinal = result
        assert tribe.value == "gauls"
        assert ordinal == 1

    def test_u22_is_gauls_2(self):
        result = unit_class_to_tribe_ordinal("u22")
        assert result is not None
        tribe, ordinal = result
        assert tribe.value == "gauls"
        assert ordinal == 2

    def test_u3_is_romans_scout(self):
        """u3 es el explorador romano (ordinal 3 = spy candidate)."""
        result = unit_class_to_tribe_ordinal("u3")
        assert result is not None
        tribe, ordinal = result
        assert tribe.value == "romans"
        assert ordinal == 3

    def test_uhero_returns_none(self):
        assert unit_class_to_tribe_ordinal("uhero") is None

    def test_out_of_range_returns_none(self):
        assert unit_class_to_tribe_ordinal("u999") is None

    def test_tribe_by_village_class_6_is_egyptians(self):
        """village-6 mapeado según la constante del spec RN-27."""
        assert TRIBE_BY_VILLAGE_CLASS[6] == "egyptians"


# ===========================================================================
# Métodos adicionales de BD — UT-RDB01..UT-RDB03
# ===========================================================================

def _run(coro):
    return asyncio.run(coro)


def _make_record(**kwargs) -> IncomingAttackRecord:
    now_iso = datetime.now(timezone.utc).isoformat()
    defaults = dict(
        world_id=1,
        village_game_id=100,
        source="dorf1",
        detected_at=now_iso,
        updated_at=now_iso,
        impact_at=(
            datetime.now(timezone.utc).replace(tzinfo=None)
        ).isoformat() + "Z",
    )
    defaults.update(kwargs)
    return IncomingAttackRecord(**defaults)


async def _setup_db_with_world() -> tuple[aiosqlite.Connection, IncomingAttackSQLiteAdapter]:
    """Crea una BD en memoria con la tabla worlds y la tabla incoming_attacks."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS worlds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO worlds (id, server, name) VALUES (1, 'ts1.travian.es', 'Mundo 1');
        INSERT INTO worlds (id, server, name) VALUES (2, 'ts2.travian.es', 'Mundo 2');
    """)
    await conn.commit()
    adapter = IncomingAttackSQLiteAdapter(conn)
    await adapter.ensure_tables()
    return conn, adapter


class TestAdditionalDbMethods:
    """Tests UT-RDB01..UT-RDB03 de los métodos adicionales del adaptador SQLite."""

    # UT-RDB01: get_attack_by_id — devuelve dict con todos los campos; None si no existe
    def test_rdb01_get_attack_by_id(self):
        async def _inner():
            conn, adapter = await _setup_db_with_world()
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                record = IncomingAttackRecord(
                    world_id=1,
                    village_game_id=200,
                    source="sidebar",
                    detected_at=now_iso,
                    updated_at=now_iso,
                )
                attack_id = await adapter.upsert_attack(record)
                assert attack_id > 0

                # get_attack_by_id debe devolver el registro
                result = await adapter.get_attack_by_id(attack_id)
                assert result is not None
                assert result["id"] == attack_id
                assert result["village_game_id"] == 200
                assert result["source"] == "sidebar"
                assert result["attacker_snapshot_json"] is None

                # id inexistente → None
                missing = await adapter.get_attack_by_id(9999)
                assert missing is None
            finally:
                await conn.close()

        _run(_inner())

    # UT-RDB02: update_snapshot — actualiza attacker_snapshot_json
    def test_rdb02_update_snapshot(self):
        async def _inner():
            conn, adapter = await _setup_db_with_world()
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                record = IncomingAttackRecord(
                    world_id=1,
                    village_game_id=201,
                    source="rally_point",
                    detected_at=now_iso,
                    updated_at=now_iso,
                )
                attack_id = await adapter.upsert_attack(record)

                snapshot = json.dumps({"player_name": "GonnaDie", "tribe": "gauls"})
                await adapter.update_snapshot(attack_id, snapshot, now_iso)

                result = await adapter.get_attack_by_id(attack_id)
                assert result is not None
                assert result["attacker_snapshot_json"] == snapshot

                # Verificar que el JSON es parseable
                parsed = json.loads(result["attacker_snapshot_json"])
                assert parsed["player_name"] == "GonnaDie"
                assert parsed["tribe"] == "gauls"
            finally:
                await conn.close()

        _run(_inner())

    # UT-RDB03: summary_by_world — recuento correcto de ataques activos por mundo
    def test_rdb03_summary_by_world(self):
        async def _inner():
            conn, adapter = await _setup_db_with_world()
            try:
                now_iso = datetime.now(timezone.utc).isoformat()

                # Insertar 2 ataques en mundo 1 (1 activo con impact_at futuro, 1 sidebar sin timer)
                future_iso = "2099-12-31T23:59:59+00:00"
                past_iso   = "2020-01-01T00:00:00+00:00"

                await adapter.upsert_attack(IncomingAttackRecord(
                    world_id=1, village_game_id=300, source="dorf1",
                    detected_at=now_iso, updated_at=now_iso,
                    impact_at=future_iso,  # activo
                ))
                await adapter.upsert_attack(IncomingAttackRecord(
                    world_id=1, village_game_id=301, source="sidebar",
                    detected_at=now_iso, updated_at=now_iso,
                    impact_at=None,  # sin timer → cuenta como pendiente (RT-05)
                ))
                await adapter.upsert_attack(IncomingAttackRecord(
                    world_id=1, village_game_id=302, source="dorf1",
                    detected_at=now_iso, updated_at=now_iso,
                    impact_at=past_iso,  # pasado → NO cuenta
                ))

                summary = await adapter.summary_by_world()
                assert isinstance(summary, list)
                # Debe devolver entrada para ambos mundos
                world_ids = [s["world_id"] for s in summary]
                assert 1 in world_ids
                assert 2 in world_ids

                mundo1 = next(s for s in summary if s["world_id"] == 1)
                mundo2 = next(s for s in summary if s["world_id"] == 2)

                # Mundo 1: 1 activo (futuro) + 1 sin timer = 2 pendientes
                assert mundo1["pending_attacks"] == 2
                # Mundo 2: sin ataques = 0
                assert mundo2["pending_attacks"] == 0
            finally:
                await conn.close()

        _run(_inner())
