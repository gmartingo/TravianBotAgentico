"""
Parser estático para las 5 sub-pestañas de /village/statistics/troops.

Métodos:
  - parse_own(html)       → TroopsOwnResponse
  - parse_support(html)   → TroopsSupportResponse  (raw, sin troop_names)
  - parse_smithy(html)    → TroopsSmithyResponse
  - parse_hospital(html)  → TroopsHospitalResponse
  - parse_training(html)  → TroopsTrainingResponse

Los métodos son @staticmethod: la clase no tiene estado.
Ningún selector usa texto visible (alt, texto de celda) para identificar tropas —
solo clases CSS (uNN) según RN-01 del spec lectura-troops.

El parser devuelve troop_types como list[str] (uNN). El use case del core
transforma esa lista en list[TroopTypeInfo] con nombres localizados.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from adapters.browser.parsers._common import (
    extract_game_id_from_vil_cell,
    extract_game_id_from_village_name_cell,
    extract_unit_class,
)
from core.dtos.troops_dto import (
    BuildingQueueDTO,
    TroopsHospitalResponse,
    TroopsOwnResponse,
    TroopsSmithyResponse,
    TroopsSupportResponse,
    TroopsTrainingResponse,
    VillageHospitalDTO,
    VillageOwnTroopsDTO,
    VillageSmithyDTO,
    VillageSupportTroopsDTO,
    VillageTrainingDTO,
)
from core.utils.parsing import parse_int, parse_time

# Patrón para extraer newdid= y gid= de hrefs de Travian.
_NEWDID_RE = re.compile(r"newdid=(\d+)")
_GID_RE = re.compile(r"gid=(\d+)")


class TroopsParser:
    """Parser HTML → DTOs para las 5 sub-pestañas de tropas de Travian."""

    # ------------------------------------------------------------------
    # 9.1  parse_own
    # ------------------------------------------------------------------

    @staticmethod
    def parse_own(html: str) -> TroopsOwnResponse:
        """
        Parsea /village/statistics/troops/own (tabla#troops).

        Devuelve TroopsOwnResponse con:
          - troop_types: list[str] — uNN del thead (u21-u30 + uhero)
          - villages:    list[VillageOwnTroopsDTO] — una entrada por aldea
          - totals:      dict[str, int] — sumas de la fila tr.sum

        Filas tr.empty y tr.sum se ignoran en la lista de aldeas.
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table#troops")

        # 1. Leer columnas del thead
        troop_types: list[str] = []
        for td in table.select("thead tr td.unit"):
            img = td.select_one("img.unit")
            if img:
                unn = extract_unit_class(img)
                if unn:
                    troop_types.append(unn)

        # 2. Leer filas de aldeas (solo las que tienen td.villageName)
        villages: list[VillageOwnTroopsDTO] = []
        for row in table.select("tbody tr"):
            name_cell = row.select_one("td.villageName")
            if name_cell is None:
                continue
            game_id = extract_game_id_from_village_name_cell(name_cell)
            if game_id is None:
                continue

            # Celdas de cantidad: todas las td que NO son villageName, en orden
            td_list = [
                td for td in row.find_all("td")
                if "villageName" not in (td.get("class") or [])
            ]
            counts: dict[str, int] = {}
            for i, unn in enumerate(troop_types):
                td = td_list[i] if i < len(td_list) else None
                if td is None:
                    counts[unn] = 0
                else:
                    counts[unn] = parse_int(td.get_text(strip=True))

            villages.append(VillageOwnTroopsDTO(game_id=game_id, counts=counts))

        # 3. Leer tr.sum (totales) — la celda de village es td.vil, no td.villageName
        totals: dict[str, int] = {}
        sum_row = table.select_one("tr.sum")
        if sum_row:
            # Excluir la celda "Sum" (td.vil) para quedarse con las celdas de valores
            sum_tds = [
                td for td in sum_row.find_all("td")
                if "vil" not in (td.get("class") or [])
            ]
            for i, unn in enumerate(troop_types):
                td = sum_tds[i] if i < len(sum_tds) else None
                totals[unn] = parse_int(td.get_text(strip=True)) if td else 0

        return TroopsOwnResponse(
            troop_types=troop_types,  # list[str]; use case lo enriquece
            villages=villages,
            totals=totals,
        )

    # ------------------------------------------------------------------
    # 9.2  parse_support
    # ------------------------------------------------------------------

    @staticmethod
    def parse_support(html: str) -> TroopsSupportResponse:
        """
        Parsea /village/statistics/troops/support (div.troops_wrapper > table.vil_troops).

        Devuelve TroopsSupportResponse con:
          - villages: list[VillageSupportTroopsDTO]
          - troop_names: {} (dict vacío — el use case lo construye con traducción)

        El parser no llama a translation_port; troop_names lo completa el use case.
        """
        soup = BeautifulSoup(html, "html.parser")
        villages: list[VillageSupportTroopsDTO] = []

        for wrapper in soup.select("div.troops_wrapper"):
            table = wrapper.select_one("table.vil_troops")
            if table is None:
                continue

            # game_id desde el enlace del thead
            link = table.select_one("thead th a[href*='newdid=']")
            if link is None:
                continue
            m = _NEWDID_RE.search(link.get("href", ""))
            if m is None:
                continue
            game_id = int(m.group(1))

            own: dict[str, int] = {}
            nature: dict[str, int] = {}

            # tbody.troops: pares (fila_iconos, fila_cantidades), sin tr.empty
            troops_body = table.select_one("tbody.troops")
            if troops_body:
                rows = [
                    r for r in troops_body.find_all("tr")
                    if not r.select_one("td.empty") and not r.select_one("td[colspan]")
                ]

                # Iterar por pares (iconos, cantidades)
                i = 0
                while i + 1 < len(rows):
                    icon_row = rows[i]
                    qty_row = rows[i + 1]
                    imgs = icon_row.find_all("img", class_="unit")
                    qty_tds = qty_row.find_all("td")

                    for j, img in enumerate(imgs):
                        unn = extract_unit_class(img)
                        if unn is None:
                            continue
                        qty_text = qty_tds[j].get_text(strip=True) if j < len(qty_tds) else "0"
                        qty = parse_int(qty_text)

                        # Clasificar: u31-u40 → nature; u21-u30 + uhero → own
                        if unn == "uhero":
                            own["uhero"] = own.get("uhero", 0) + qty
                        elif unn.startswith("u") and unn[1:].isdigit():
                            n = int(unn[1:])
                            if 31 <= n <= 40:
                                nature[unn] = qty
                            else:
                                own[unn] = qty
                        # Otros (u41+) → own por defecto
                        else:
                            own[unn] = qty

                    i += 2

            hero = own.get("uhero", 0)

            # tbody.upkeep: cereal/hora + fuerza off/def/cav
            upkeep_per_hour = 0
            offence: int | None = None
            def_infantry: int | None = None
            def_cavalry: int | None = None

            upkeep_body = table.select_one("tbody.upkeep")
            if upkeep_body:
                # Consumo de cereal
                cons_span = upkeep_body.select_one("div.consumption span")
                if cons_span:
                    upkeep_per_hour = parse_int(cons_span.get_text(strip=True))

                # Fuerza off/def: cada div.inlineIcon.strength tiene un <i> + span.value
                for strength_div in upkeep_body.select("div.inlineIcon.strength"):
                    icon = strength_div.select_one("i")
                    val_span = strength_div.select_one("span.value")
                    if icon is None or val_span is None:
                        continue
                    raw = val_span.get_text(strip=True)
                    if raw == "-":
                        continue  # EC-11: sin tropas → None
                    icon_classes = icon.get("class") or []
                    value = parse_int(raw)
                    if "offence_small" in icon_classes:
                        offence = value
                    elif "defenceInfantry_small" in icon_classes:
                        def_infantry = value
                    elif "defenceCavalry_small" in icon_classes:
                        def_cavalry = value

            villages.append(VillageSupportTroopsDTO(
                game_id=game_id,
                own=own,
                nature=nature,
                hero=hero,
                upkeep_per_hour=upkeep_per_hour,
                offence=offence,
                def_infantry=def_infantry,
                def_cavalry=def_cavalry,
            ))

        # troop_names vacío — el use case lo construye con translation_port
        return TroopsSupportResponse(villages=villages, troop_names={})

    # ------------------------------------------------------------------
    # 9.3  parse_smithy
    # ------------------------------------------------------------------

    @staticmethod
    def parse_smithy(html: str) -> TroopsSmithyResponse:
        """
        Parsea /village/statistics/troops/smithy (table.under_progress).

        Devuelve TroopsSmithyResponse con:
          - troop_types: list[str] — uNN del thead segunda fila (u21-u28)
          - villages:    list[VillageSmithyDTO]

        Regla EC-02/EC-03: "-" → None (no investigable); "0" → 0 (int).
        Regla EC-04/EC-05: in_progress puede tener múltiples uNN; span.dot → [].
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.under_progress")

        # 1. Leer columnas de la segunda fila del thead (th.unit > img.unit)
        troop_types: list[str] = []
        for th in table.select("thead tr:nth-child(2) th.unit"):
            img = th.select_one("img.unit")
            if img:
                unn = extract_unit_class(img)
                if unn:
                    troop_types.append(unn)

        # 2. Filas de aldeas (td.vil.fc contiene el enlace con newdid=)
        villages: list[VillageSmithyDTO] = []
        for row in table.select("tbody tr"):
            vil_cell = row.select_one("td.vil.fc")
            if vil_cell is None:
                continue
            game_id = extract_game_id_from_vil_cell(vil_cell)
            if game_id is None:
                continue

            tds = row.find_all("td")

            # Columna "in progress" (2ª td, índice 1)
            in_progress: list[str] = []
            if len(tds) > 1:
                in_progress_td = tds[1]
                for img in in_progress_td.find_all("img", class_="unit"):
                    unn = extract_unit_class(img)
                    if unn:
                        in_progress.append(unn)
                # Si hay span.dot y ninguna img → in_progress ya es [] (correcto)

            # Columnas de niveles (3ª en adelante, índice 2+)
            level_tds = tds[2:] if len(tds) > 2 else []
            levels: dict[str, int | None] = {}
            for i, unn in enumerate(troop_types):
                td = level_tds[i] if i < len(level_tds) else None
                if td is None:
                    levels[unn] = None
                else:
                    raw = td.get_text(strip=True)
                    if raw == "-":
                        levels[unn] = None  # EC-02: no investigable
                    else:
                        levels[unn] = parse_int(raw)  # EC-03: 0 es int, no None

            villages.append(VillageSmithyDTO(
                game_id=game_id,
                in_progress=in_progress,
                levels=levels,
            ))

        return TroopsSmithyResponse(troop_types=troop_types, villages=villages)

    # ------------------------------------------------------------------
    # 9.4  parse_hospital
    # ------------------------------------------------------------------

    @staticmethod
    def parse_hospital(html: str) -> TroopsHospitalResponse:
        """
        Parsea /village/statistics/troops/hospital (table.under_progress).

        Devuelve TroopsHospitalResponse con:
          - player_tribe: int — extraído de th.villageName > i.tribeN_medium (RN-05)
          - troop_types:  list[str] — uNN del thead segunda fila (u21-u26)
          - villages:     list[VillageHospitalDTO]

        EC-06: span.dot → has_hospital=True, healing=False
        EC-07: span.none → has_hospital=False, healing=False, wounded={}
        Cualquier otro contenido → has_hospital=True, healing=True (TR-03)
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.under_progress")

        # 1. Tribu del jugador desde th.villageName > i[class*="tribe"]
        player_tribe = 0
        tribe_th = table.select_one("th.villageName")
        if tribe_th:
            icon = tribe_th.select_one("i[class]")
            if icon:
                for cls in (icon.get("class") or []):
                    m = re.match(r"tribe(\d+)_medium", cls)
                    if m:
                        player_tribe = int(m.group(1))
                        break

        # 2. Columnas de heridos (segunda fila del thead, th.unit > img.unit)
        troop_types: list[str] = []
        for th in table.select("thead tr:nth-child(2) th.unit"):
            img = th.select_one("img.unit")
            if img:
                unn = extract_unit_class(img)
                if unn:
                    troop_types.append(unn)

        # 3. Filas de aldeas (td.villageName)
        villages: list[VillageHospitalDTO] = []
        for row in table.select("tbody tr"):
            name_cell = row.select_one("td.villageName")
            if name_cell is None:
                continue
            game_id = extract_game_id_from_village_name_cell(name_cell)
            if game_id is None:
                continue

            # Columna inProgress
            in_progress_td = row.select_one("td.inProgress")
            has_hospital = False
            healing = False

            if in_progress_td:
                if in_progress_td.select_one("span.dot"):
                    has_hospital = True
                    healing = False  # EC-06: hospital existe, sin curación activa
                elif in_progress_td.select_one("span.none"):
                    has_hospital = False
                    healing = False  # EC-07: sin hospital
                else:
                    # Posible span.duration o timer si hay curación en curso (TR-03)
                    has_hospital = True
                    healing = True

            # Columnas de heridos: índices 2+ (0=villageName, 1=inProgress)
            tds = row.find_all("td")
            wounded_tds = tds[2:] if len(tds) > 2 else []
            wounded: dict[str, int] = {}
            if has_hospital:
                for i, unn in enumerate(troop_types):
                    td = wounded_tds[i] if i < len(wounded_tds) else None
                    wounded[unn] = parse_int(td.get_text(strip=True)) if td else 0

            villages.append(VillageHospitalDTO(
                game_id=game_id,
                has_hospital=has_hospital,
                healing=healing,
                wounded=wounded,
            ))

        return TroopsHospitalResponse(
            player_tribe=player_tribe,
            troop_types=troop_types,
            villages=villages,
        )

    # ------------------------------------------------------------------
    # 9.5  parse_training
    # ------------------------------------------------------------------

    @staticmethod
    def parse_training(html: str) -> TroopsTrainingResponse:
        """
        Parsea /village/statistics/troops/training (table.under_progress).

        Devuelve TroopsTrainingResponse con:
          - building_gids: list[int] — gids de columnas (19, 20, 21, 46)
          - buildings:     [] (list vacío — el use case lo enriquece con BuildingInfo)
          - villages:      list[VillageTrainingDTO]

        RN-08/TR-02: los gids se extraen del primer a[href*='gid='] de la primera
        fila de datos. Si esa fila tiene span.none (edificio inexistente), se usa
        el typeNN del icono del thead como fallback.

        EC-12: span.dot → building_exists=True, queue_seconds=0
        EC-13: span.none → building_exists=False, queue_seconds=None
        EC-14: parse_time maneja strip de espacios en el texto de duración.
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.under_progress")

        # 1. Número de columnas de edificios y iconos del thead
        header_ths = table.select("thead tr th.unit")
        num_cols = len(header_ths)

        # 2. Extraer gids de la primera fila de datos
        building_gids: list[int] = []
        first_data_row = table.select_one("tbody tr")
        if first_data_row:
            data_tds = first_data_row.find_all("td")
            # td[0] = villageName; td[1..num_cols] = columnas de edificios
            for col_idx, td in enumerate(data_tds[1: 1 + num_cols]):
                link = td.select_one("a[href*='gid=']")
                if link:
                    m = _GID_RE.search(link.get("href", ""))
                    if m:
                        building_gids.append(int(m.group(1)))
                        continue
                # Fallback: leer typeNN del icono del thead (TR-02)
                if col_idx < len(header_ths):
                    icon = header_ths[col_idx].select_one("i.building_small")
                    if icon:
                        for cls in (icon.get("class") or []):
                            m2 = re.match(r"type(\d+)", cls)
                            if m2:
                                building_gids.append(int(m2.group(1)))
                                break
                        else:
                            building_gids.append(0)
                    else:
                        building_gids.append(0)

        # 3. Filas de aldeas
        villages: list[VillageTrainingDTO] = []
        for row in table.select("tbody tr"):
            name_cell = row.select_one("td.villageName")
            if name_cell is None:
                continue
            game_id = extract_game_id_from_village_name_cell(name_cell)
            if game_id is None:
                continue

            data_tds = row.find_all("td")
            building_tds = data_tds[1: 1 + num_cols]

            queues: list[BuildingQueueDTO] = []
            for col_idx, td in enumerate(building_tds):
                gid = building_gids[col_idx] if col_idx < len(building_gids) else 0
                duration_span = td.select_one("span.duration")
                dot_span = td.select_one("span.dot")

                if duration_span:
                    raw_time = duration_span.get_text(strip=True)
                    queue_seconds = parse_time(raw_time)
                    queues.append(BuildingQueueDTO(
                        gid=gid, building_exists=True, queue_seconds=queue_seconds
                    ))
                elif dot_span:
                    # EC-12: edificio existe, sin cola activa
                    queues.append(BuildingQueueDTO(
                        gid=gid, building_exists=True, queue_seconds=0
                    ))
                else:
                    # EC-13: span.none o celda vacía → edificio inexistente
                    queues.append(BuildingQueueDTO(
                        gid=gid, building_exists=False, queue_seconds=None
                    ))

            villages.append(VillageTrainingDTO(game_id=game_id, queues=queues))

        # buildings vacío — el use case lo enriquece con BuildingInfo + nombres
        return TroopsTrainingResponse(
            buildings=[],
            building_gids=building_gids,
            villages=villages,
        )
