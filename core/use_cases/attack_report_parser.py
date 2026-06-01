"""
Parser de reportes de ataque a oasis de Travian.

Convierte el texto crudo de un reporte (copiado desde la interfaz de Travian)
en un AttackReportPreview con todos los datos normalizados.

Reglas de negocio principales:
  RN-01 El defensor debe ser NATURE (al menos un animal reconocido).
  RN-02 Autodetección de idioma por inversión del catálogo NATURE (0 colisiones).
  RN-03 Tropas atacantes: ordinal = None (nombres ambiguos entre tribus).
  RN-04 Nombre de animal no reconocido → rechazar todo, no guardar parcial.
  RN-05 Duplicados: verificados por clave única en BD (vía db_port opcional).
  RN-06 Supervivientes = enviadas − perdidas (no se leen del texto).
  RN-07 Botín: 4 recursos + capacidad + inventario opcional del héroe.
  RN-08-bis Timestamp: guardado verbatim desde la línea del ataque (naive, sin zona horaria).
             utc_offset se conserva como metadato informativo pero NO se resta.
  RN-09 Un solo bloque por pegado; si hay más → error.

Ver spec docs/specs/bd-ataques-oasis.md §9.2 para el algoritmo en detalle.
Añadido en la feature bd-ataques-oasis (2026-05-30).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core.entities.attack_report import (
    AnimalEntry,
    AttackerTroopEntry,
    AttackReportPreview,
    BountyData,
)

if TYPE_CHECKING:
    from core.ports.attack_report_port import AttackReportPort


# ---------------------------------------------------------------------------
# Excepciones propias del parser
# ---------------------------------------------------------------------------


class ReportFormatError(ValueError):
    """El texto no tiene el formato esperado de reporte de Travian."""
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class MultipleReportsError(ReportFormatError):
    """Se detectaron múltiples bloques de reporte en el texto pegado."""
    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(f"Se detectaron {count} bloques de reporte. Pega solo un reporte a la vez.")


class NotNatureOasisError(ReportFormatError):
    """El reporte no contiene animales Nature como defensores."""
    def __init__(self) -> None:
        super().__init__("El reporte no contiene animales Nature como defensores. Solo se aceptan ataques a oasis.")


class UnrecognizedAnimalError(ReportFormatError):
    """Uno o más nombres en la sección de defensor no se encontraron en el catálogo NATURE."""
    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__(
            f"Nombres de animales no reconocidos: {names!r}. Revisa el texto pegado."
        )


class DefeatReportParseError(Exception):
    """
    El reporte es de combate perdido pero el formato es corrupto o inesperado.

    Se lanza cuando la fila de cantidades del defensor mezcla '?' y dígitos,
    lo cual indica un reporte corrupto (Travian nunca produce filas mixtas).

    §17.3 del spec bd-ataques-oasis.md.
    """
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# ---------------------------------------------------------------------------
# Índice invertido NATURE (singleton lazy)
# ---------------------------------------------------------------------------

_NATURE_INDEX: dict[str, int] | None = None

# Alias de nombres que el juego REAL de Travian muestra en los reportes pero que
# difieren del nombre que kirilloid usa en core/i18n/catalog/base/troops.json.
# Clave = nombre en minúsculas tal cual aparece en el reporte; valor = ordinal NATURE.
# Verificado sin colisión contra el catálogo (0 idiomas usan estos nombres para
# otro animal). Ampliar aquí si aparecen más discrepancias kirilloid↔juego.
#   - NATURE_3: kirilloid="Serpent" / juego (en)="Snake"
_NATURE_LIVE_ALIASES: dict[str, int] = {
    "snake": 3,
}


def _get_nature_index() -> dict[str, int]:
    """
    Construye (una sola vez, lazy) el índice invertido de animales NATURE.

    Resultado: { "rat": 1, "ratte": 1, "araña": 2, "spider": 2, ... }

    El índice es seguro para uso global sin conocer el idioma:
    - 215 entradas únicas en 25 idiomas.
    - Cero colisiones cross-language (mismo nombre → siempre el mismo ordinal).

    Fuente: core/i18n/catalog/base/troops.json (claves NATURE_1..10).
    """
    global _NATURE_INDEX
    if _NATURE_INDEX is not None:
        return _NATURE_INDEX

    catalog_path = (
        Path(__file__).parent.parent / "i18n" / "catalog" / "base" / "troops.json"
    )
    with catalog_path.open(encoding="utf-8") as f:
        data = json.load(f)

    index: dict[str, int] = {}
    for key, translations in data.items():
        if not key.startswith("NATURE_"):
            continue
        ordinal = int(key.rsplit("_", 1)[1])
        for name in translations.values():
            name_lower = name.strip().lower()
            index[name_lower] = ordinal  # seguro: 0 colisiones confirmadas

    # Fusionar alias del juego real que kirilloid no contempla (p.ej. "Snake").
    index.update(_NATURE_LIVE_ALIASES)

    _NATURE_INDEX = index
    return _NATURE_INDEX


def build_nature_inverted_index() -> dict[str, int]:
    """API pública para obtener el índice invertido (útil para tests y diagnóstico)."""
    return _get_nature_index()


# ---------------------------------------------------------------------------
# Índice invertido de TROPAS por tribu (para deducir tribu + ordinal → icono)
# ---------------------------------------------------------------------------

# nombre_lower → [(tribe_lower, ordinal)]  (un nombre puede existir en varias tribus)
_TROOP_INDEX: dict[str, list[tuple[str, int]]] | None = None


def _get_troop_index() -> dict[str, list[tuple[str, int]]]:
    """
    Índice invertido de nombres de tropa → (tribu, ordinal), todas las tribus/idiomas.

    Fuente: core/i18n/catalog/base/troops.json (claves GAULS_1, ROMANS_3, …).
    Se excluye NATURE (los animales se resuelven con _get_nature_index()).
    Tribu en minúsculas para casar con los icon_id ("GAULS" → "gauls" → gauls_4.png).
    """
    global _TROOP_INDEX
    if _TROOP_INDEX is not None:
        return _TROOP_INDEX

    catalog_path = (
        Path(__file__).parent.parent / "i18n" / "catalog" / "base" / "troops.json"
    )
    with catalog_path.open(encoding="utf-8") as f:
        data = json.load(f)

    index: dict[str, list[tuple[str, int]]] = {}
    for key, translations in data.items():
        prefix, _, ord_str = key.rpartition("_")
        if not ord_str.isdigit() or prefix == "NATURE":
            continue
        tribe = prefix.lower()
        ordinal = int(ord_str)
        for name in translations.values():
            nl = name.strip().lower()
            index.setdefault(nl, []).append((tribe, ordinal))

    _TROOP_INDEX = index
    return _TROOP_INDEX


def _resolve_attacker_tribe(attacker_troops: list[AttackerTroopEntry]) -> str | None:
    """
    Deduce la tribu del atacante por votación: cada nombre de tropa reconocido
    suma un voto a cada tribu candidata; gana la tribu con más coincidencias.

    El roster de un reporte es de UNA sola tribu, así que la votación converge a
    ella aunque algún nombre sea ambiguo entre tribus. Devuelve None si ningún
    nombre se reconoce (p.ej. solo "Hero").
    """
    index = _get_troop_index()
    votes: dict[str, int] = {}
    for entry in attacker_troops:
        nl = entry.troop_name.strip().lower()
        for tribe, _ord in set(index.get(nl, [])):
            votes[tribe] = votes.get(tribe, 0) + 1
    if not votes:
        return None
    # Desempate determinista: más votos, luego orden alfabético de la tribu.
    return max(votes.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _assign_attacker_ordinals(
    attacker_troops: list[AttackerTroopEntry], tribe: str | None
) -> None:
    """Asigna troop_ordinal a cada tropa según la tribu deducida (in-place)."""
    if not tribe:
        return
    index = _get_troop_index()
    for entry in attacker_troops:
        nl = entry.troop_name.strip().lower()
        for cand_tribe, ordinal in index.get(nl, []):
            if cand_tribe == tribe:
                entry.troop_ordinal = ordinal
                break


# ---------------------------------------------------------------------------
# Patrones de regex
# ---------------------------------------------------------------------------

# Patrón de fecha del ataque: "30.05.26, 16:28:53"
_FECHA_PATTERN = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2}),\s*(\d{2}):(\d{2}):(\d{2})\b")

# Patrón de "Server time" con offset UTC:
#   "Server time: 17:28:53 (UTC +1:00)"  o  "Server time: 17:28:53 (UTC+01:00)"
_SERVER_TIME_PATTERN = re.compile(
    r"Server time[:\s]+\d{2}:\d{2}:\d{2}\s*\(UTC\s*([+-]\d{1,2}:\d{2})\)",
    re.IGNORECASE,
)

# Coordenadas: "(X|Y)" o "(X/-Y)" o "(-X|-Y)" — enteros con signo, separador | o /
_COORD_PATTERN = re.compile(r"\((-?\d+)[|/](-?\d+)\)")

# Fila de números: línea que contiene solo números separados por espacios/comas/tabs
# Usada para detectar filas de cantidad en las tablas de tropas/animales.
_NUMBER_ROW_PATTERN = re.compile(r"^[\s\d,\t]+$")

# Línea de capacidad: "N/M" donde N y M son enteros
_CAPACITY_PATTERN = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")

# Inventario del héroe: 4 números (wood clay iron crop) en una línea tras "inventory"
_INVENTORY_SIGNAL = re.compile(r"inventor", re.IGNORECASE)

# Línea con exactamente 4 enteros ≥ 0 separados por espacios o comas
_FOUR_NUMBERS = re.compile(r"^\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*$")

# ── Patrones para detección del modo perdido (§17.2) ─────────────────────────
# Fila de derrota: solo tokens '?' separados por espacios/tabs (ningún dígito).
# Ejemplos válidos: "?", "?  ?  ?", "?\t?\t?"
_DEFEAT_ROW_PATTERN = re.compile(r"^\?[\s\t]*(\?[\s\t]*)*$")


def _is_defeat_row(line: str) -> bool:
    """True si la línea es una fila de cantidades desconocidas (solo '?').

    §17.2: detección idioma-agnóstica del modo perdido. Solo se llama
    sobre la siguiente línea no vacía tras la cabecera de animales en
    _extract_animals (sección Defender); nunca sobre tropas atacantes.
    """
    return bool(_DEFEAT_ROW_PATTERN.match(line.strip()))


def _is_mixed_row(line: str) -> bool:
    """True si la línea mezcla '?' y dígitos (caso de reporte corrupto).

    §17.2: Travian siempre produce filas homogéneas. Una fila mixta indica
    texto corrupto o pegado incorrecto → se lanza DefeatReportParseError.
    """
    has_digit = bool(re.search(r"\d", line))
    has_question = "?" in line
    return has_digit and has_question


# ---------------------------------------------------------------------------
# Helpers de parseo
# ---------------------------------------------------------------------------

# Caracteres de control bidireccional / invisibles que Travian inserta en
# números y coordenadas al renderizar la interfaz. Si no se eliminan, los
# regex de coordenadas y números no casan (p.ej. "(‭−‭70‬‬|‭73‬)").
#   U+200E LRM, U+200F RLM, U+200B ZWSP, U+FEFF BOM,
#   U+202A..U+202E (embeddings/overrides), U+2066..U+2069 (isolates)
_BIDI_CONTROL_CHARS = (
    "‎‏​﻿"
    "‪‫‬‭‮"
    "⁦⁧⁨⁩"
)
_BIDI_CONTROL_RE = re.compile(f"[{_BIDI_CONTROL_CHARS}]")

# Variantes Unicode de guion/menos que Travian usa en coordenadas negativas.
# Se normalizan al guion-menos ASCII '-' para que los regex numéricos casen.
#   U+2010 hyphen, U+2011 non-breaking hyphen, U+2012 figure dash,
#   U+2013 en dash, U+2014 em dash, U+2015 horizontal bar, U+2212 minus sign
_UNICODE_MINUS_RE = re.compile(r"[‐‑‒–—―−]")


def _normalize_raw_text(raw_text: str) -> str:
    """
    Limpia el texto crudo copiado desde Travian antes de parsearlo.

    Travian renderiza números y coordenadas envueltos en marcas de control
    bidireccional (LRM/RLM, overrides, isolates) y usa el signo menos
    tipográfico '−' (U+2212) en vez del guion ASCII. Ambos rompen los regex.

    Esta normalización:
      1. Elimina los caracteres de control/invisibles.
      2. Convierte cualquier variante de guion/menos a '-' ASCII.
    """
    text = _BIDI_CONTROL_RE.sub("", raw_text)
    text = _UNICODE_MINUS_RE.sub("-", text)
    # Quitar comas usadas como separador de millares entre dígitos ("1,531" → "1531").
    # Solo entre dígitos: nunca toca comas que separan palabras. No se tocan los
    # puntos porque '.' es el separador de fecha de Travian ("31.05.26").
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return text


def _normalize_offset(offset_str: str) -> str:
    """
    Normaliza un offset a "+HH:MM" (dos dígitos de hora).
    Ej: "+1:00" → "+01:00", "-5:30" → "-05:30"
    """
    sign = offset_str[0]
    parts = offset_str[1:].split(":")
    hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 else 0
    return f"{sign}{hours:02d}:{minutes:02d}"


def _extract_numbers_from_line(line: str) -> list[int]:
    """Extrae todos los enteros de una línea de texto."""
    return [int(x) for x in re.findall(r"\d+", line)]


def _parse_table_block(lines: list[str]) -> tuple[list[str], list[list[int]]]:
    """
    Dada una lista de líneas, intenta extraer una tabla del estilo:

        NombreTropa1  NombreTropa2  NombreTropa3
        100           50            200          (fila "enviadas")
        10            0             5            (fila "perdidas")

    Devuelve:
      - header: lista de nombres de columna
      - rows: lista de filas de enteros (una fila por línea numérica)

    El algoritmo detecta la cabecera como la línea de texto antes de las filas
    puramente numéricas. Ignoramos líneas vacías.

    Para los formatos de Travian, la tabla puede aparecer de varias formas:
      1. Cabecera de texto + 2 filas numéricas (enviadas y pérdidas)
      2. Los nombres pueden estar en una sola fila separados por tabuladores/espacios

    Estrategia robusta: buscar la primera secuencia de 2+ líneas con solo números
    y usar la línea anterior como cabecera.
    """
    # Filtrar líneas vacías manteniendo índices
    non_empty = [(i, ln) for i, ln in enumerate(lines) if ln.strip()]

    # Buscar la primera línea que sea puramente numérica
    for idx, (orig_i, line) in enumerate(non_empty):
        nums = _extract_numbers_from_line(line)
        if nums and re.match(r"^[\s\d\t]+$", line.strip()):
            # Línea numérica encontrada: la cabecera está en la línea anterior
            header_line = ""
            if idx > 0:
                header_line = non_empty[idx - 1][1]

            # Extraer nombres de la cabecera (split por 2+ espacios o tab)
            header = re.split(r"\t|  +", header_line.strip()) if header_line else []
            header = [h.strip() for h in header if h.strip()]

            # Recopilar todas las filas numéricas consecutivas
            rows: list[list[int]] = []
            for _, ln in non_empty[idx:]:
                stripped = ln.strip()
                if re.match(r"^[\d\s\t]+$", stripped) and stripped:
                    rows.append(_extract_numbers_from_line(ln))
                elif rows:
                    # Primera línea no numérica tras la secuencia → stop
                    break

            return header, rows

    return [], []


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

def parse_attack_report(
    raw_text: str,
    db_port: "AttackReportPort | None" = None,
) -> AttackReportPreview:
    """
    Parsea el texto crudo de un reporte de Travian y devuelve un AttackReportPreview.

    Parámetros:
      raw_text: texto completo pegado desde Travian (max 50 000 chars).
      db_port:  si se pasa, verifica unicidad en BD y rellena already_exists/existing_id.
                En tests sin BD se puede pasar None.

    Lanza:
      MultipleReportsError    si hay más de un bloque de fecha.
      ReportFormatError       si no se puede extraer fecha, coords o aldea.
      NotNatureOasisError     si no hay animales NATURE como defensores.
      UnrecognizedAnimalError si algún nombre de defensor no está en el catálogo.
    """
    # -----------------------------------------------------------------------
    # PASO 1 — Normalizar y detectar bloques
    # -----------------------------------------------------------------------
    # Quitar marcas de control bidi y normalizar el menos Unicode que Travian
    # inserta en coordenadas/números (si no, los regex de coords no casan).
    text = _normalize_raw_text(raw_text).strip()
    lines = text.splitlines()

    # Contar líneas que contienen una fecha de ataque
    date_lines = [ln for ln in lines if _FECHA_PATTERN.search(ln)]
    if len(date_lines) > 1:
        raise MultipleReportsError(len(date_lines))
    if len(date_lines) == 0:
        raise ReportFormatError("No se encontró fecha de ataque. Formato esperado: DD.MM.YY, HH:MM:SS")

    # -----------------------------------------------------------------------
    # PASO 2 — Extraer cabecera (fecha, offset, coordenadas, aldea origen)
    # -----------------------------------------------------------------------

    # Fecha del ataque
    m_fecha = _FECHA_PATTERN.search(text)
    if not m_fecha:
        raise ReportFormatError("No se pudo parsear la fecha del reporte. Formato esperado: DD.MM.YY, HH:MM:SS")

    day, month, year_2d, hour, minute, second = (int(x) for x in m_fecha.groups())
    year = 2000 + year_2d
    try:
        dt_server = datetime(year, month, day, hour, minute, second)
    except ValueError as exc:
        raise ReportFormatError(f"Fecha inválida en el reporte: {exc}") from exc

    # Offset UTC (EC-03: puede estar ausente)
    # RN-08-bis: utc_offset se conserva SOLO como metadato informativo.
    # NO se usa para calcular attacked_at — guardamos la hora del ataque verbatim.
    utc_offset: str | None = None
    m_server = _SERVER_TIME_PATTERN.search(text)
    if m_server:
        raw_offset = m_server.group(1)  # "+1:00" o "-05:30"
        utc_offset = _normalize_offset(raw_offset)
        # Metadato informativo. NO se resta ni se convierte a UTC.

    # Hora del ataque verbatim (naive, sin zona horaria).
    # dt_server proviene de la línea "DD.MM.YY, HH:MM:SS" del reporte.
    # Formato resultante: "YYYY-MM-DDTHH:MM:SS"
    attacked_at = dt_server.isoformat()

    # Coordenadas destino — puede haber varias pares de coords en el texto
    # (origen y destino). Tomamos todas y elegimos las que corresponden al destino.
    # Estrategia: la primera aparición suele ser las coordenadas del DESTINO del ataque
    # en la línea del título o encabezado del reporte.
    all_coords = _COORD_PATTERN.findall(text)
    if not all_coords:
        raise ReportFormatError("No se encontraron coordenadas de destino en el reporte.")

    # El destino generalmente es el primer par de coordenadas que aparece
    # (en la línea del nombre del oasis atacado, antes de la sección Attacker).
    # Encontramos la posición de la fecha y buscamos coords ANTES de la sección Attacker.
    fecha_pos = m_fecha.start()
    text_before_fecha = text[:fecha_pos]
    coords_before = _COORD_PATTERN.findall(text_before_fecha)

    if coords_before:
        coord_x_dest, coord_y_dest = int(coords_before[0][0]), int(coords_before[0][1])
    else:
        # Fallback: primer par del texto completo
        coord_x_dest, coord_y_dest = int(all_coords[0][0]), int(all_coords[0][1])

    # Aldea origen
    # Estrategia: buscar la sección "Attacker" y extraer el nombre de la aldea
    # que aparece antes de las coordenadas de origen. El formato típico es:
    #   "Attacker\n<nombre_aldea> (X|Y)\n..."
    # También puede ser: "Atacante\n<nombre> (X|Y)"
    # Buscamos la línea que contiene la coordenada de ORIGEN (segunda aparición de coords).
    origin_village_name = _extract_origin_village(lines, all_coords)

    # -----------------------------------------------------------------------
    # PASO 3 — Extraer tropas atacantes
    # -----------------------------------------------------------------------
    attacker_troops = _extract_attacker_troops(text, lines)

    # Deducir la tribu del atacante y asignar ordinales (para resolver sprites).
    # Cambia RN-03 original (ordinal=None): dentro de un reporte el roster basta
    # para identificar tribu+ordinal de forma fiable. Decisión aprobada por el usuario.
    attacker_tribe = _resolve_attacker_tribe(attacker_troops)
    _assign_attacker_ordinals(attacker_troops, attacker_tribe)

    # -----------------------------------------------------------------------
    # PASO 4 — Extraer animales (defensor NATURE)
    # -----------------------------------------------------------------------
    animals = _extract_animals(text, lines)

    # -----------------------------------------------------------------------
    # PASO 5 — Extraer botín
    # -----------------------------------------------------------------------
    bounty, hero_inventory = _extract_bounty(text, lines)

    # -----------------------------------------------------------------------
    # PASO 6 — Verificar unicidad en BD (si se pasa db_port)
    # -----------------------------------------------------------------------
    already_exists = False
    existing_id: int | None = None
    # Nota: la verificación es async pero parse_attack_report es sync.
    # La verificación la hace el HANDLER de la ruta usando el db_port directamente.
    # El parser no tiene acceso al event loop. El parámetro db_port se reserva
    # para uso futuro o para tests que quieran inyectar un mock síncrono.
    # En producción: el endpoint hace la verificación y rellena already_exists/existing_id.

    return AttackReportPreview(
        attacked_at=attacked_at,
        utc_offset=utc_offset,
        coord_x_dest=coord_x_dest,
        coord_y_dest=coord_y_dest,
        origin_village_name=origin_village_name,
        attacker_troops=attacker_troops,
        animals=animals,
        bounty=bounty,
        hero_inventory=hero_inventory,
        already_exists=already_exists,
        existing_id=existing_id,
        attacker_tribe=attacker_tribe,
    )


# ---------------------------------------------------------------------------
# Sub-parsers internos
# ---------------------------------------------------------------------------

def _extract_origin_village(lines: list[str], all_coords: list[tuple]) -> str:
    """
    Extrae el nombre de la aldea origen del atacante.

    El formato de Travian es:
        Attacker
        NombreAldea (X|Y)   ← esta línea

    El nombre es el texto antes de las coordenadas en la línea de la aldea atacante.
    La coordenada de origen es el segundo par de coordenadas en el texto (el primero
    es el destino, el segundo es la aldea de origen en la sección Attacker).

    Fallback: si no se puede extraer, devuelve "Desconocido".
    """
    # Buscar la sección de Attacker (varía por idioma)
    _ATTACKER_SECTIONS = re.compile(
        r"^\s*(Attacker|Atacante|Angreifer|Attaquant|Нападающий|مهاجم|Нападач|"
        r"Útočník|Angriber|Επιτιθέμενος|حمله‌کننده|תוקף|Támadó|Attaccante|"
        r"攻撃者|Puolustaja|Uzbrucējs|Aanvaller|Atakujący|Atacante|Attackerare|"
        r"Saldırgan|Нападник)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    m_attacker = _ATTACKER_SECTIONS.search("\n".join(lines))
    if m_attacker:
        # Buscar en las 5 líneas siguientes la que contiene coordenadas.
        # Usar start(1) (la palabra capturada) y no start(): el "\s*" inicial del
        # patrón puede tragarse el salto de línea de una línea en blanco previa,
        # lo que desplazaría el índice una línea (devolvería "Attacker").
        attacker_line_idx = "\n".join(lines).count("\n", 0, m_attacker.start(1))
        first_nonempty: str | None = None
        for i in range(attacker_line_idx + 1, min(attacker_line_idx + 6, len(lines))):
            line = lines[i]
            if first_nonempty is None and line.strip():
                first_nonempty = line.strip()
            m_coord = _COORD_PATTERN.search(line)
            if m_coord:
                # El nombre es el texto antes del paréntesis de coordenadas
                name = line[:m_coord.start()].strip()
                if name:
                    return name
                break
        # Formato sin coords en la línea del atacante (p.ej. "[Tag] Player from
        # village 01"): la mejor pista disponible es esa primera línea tras la
        # cabecera. Mejor eso que caer al fallback global, que agarra el título.
        if first_nonempty:
            return first_nonempty

    # Fallback: buscar cualquier línea con "<texto> (X|Y)"
    # donde las coords sean distintas de las del destino
    for line in lines:
        m_coord = _COORD_PATTERN.search(line)
        if m_coord:
            name = line[:m_coord.start()].strip()
            if name and not name.startswith("("):
                # Evitar líneas que son solo coordenadas o que empiezan con "("
                # También evitar líneas que son solo el nombre del oasis
                # (que terminarían con el par de coords del destino)
                return name

    return "Desconocido"


def _extract_attacker_troops(text: str, lines: list[str]) -> list[AttackerTroopEntry]:
    """
    Extrae la tabla de tropas atacantes.

    El bloque Attacker tiene este formato (simplificado):
        Attacker
        NombreAldea (X|Y)
        <cabecera con nombres de tropas>
        <fila de enviadas>
        <fila de perdidas>

    Devuelve lista de AttackerTroopEntry. Si no hay tropas (solo héroe o texto
    sin sección numérica), devuelve lista vacía.

    En MVP: troop_ordinal = None (RN-03, nombres ambiguos entre tribus).
    """
    return _parse_troop_table(text, lines, section="attacker")


def _extract_animals(text: str, lines: list[str]) -> list[AnimalEntry]:
    """
    Extrae la tabla de animales defensores (sección Defender/Defensor/...).

    Valida que todos los nombres estén en el índice NATURE.
    Lanza NotNatureOasisError o UnrecognizedAnimalError si falla.
    """
    nature_index = _get_nature_index()

    # Buscar la sección de Defender (varía por idioma)
    _DEFENDER_SECTIONS = re.compile(
        r"^\s*(Defender|Defensor|Verteidiger|Défenseur|Защитник|المدافع|Бранилац|"
        r"Obránce|Forsvarer|Αμυνόμενος|مدافع|מגן|Védő|Difensore|防衛者|"
        r"Gynėjas|Aizstāvis|Verdediger|Obrońca|Defensor|Försvarare|Savunmacı|"
        r"Захисник)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    joined = "\n".join(lines)
    m_defender = _DEFENDER_SECTIONS.search(joined)

    if not m_defender:
        raise NotNatureOasisError()

    # Extraer las líneas desde la sección Defender en adelante
    defender_start = joined[:m_defender.start()].count("\n") + 1
    defender_lines = lines[defender_start:]

    # Buscar el bloque de tabla (cabecera + filas numéricas o fila de '?')
    # La cabecera contiene los nombres de los animales.
    # En modo perdido (§17.2) la siguiente línea es solo '?'; en modo normal es numérica.
    header_names: list[str] = []
    rows_numeric: list[list[int]] = []
    defeat_mode: bool = False  # True si el atacante perdió (cantidades desconocidas)

    # Buscar la primera línea de la sección que actúe como cabecera de tabla
    i = 0
    while i < len(defender_lines):
        line = defender_lines[i].strip()
        if not line:
            i += 1
            continue

        # Detectar si es cabecera (tiene texto, no es puramente numérica)
        # La siguiente línea no vacía debe ser numérica o de '?'
        if i + 1 < len(defender_lines):
            # Buscar la siguiente línea no vacía
            next_idx = i + 1
            while next_idx < len(defender_lines) and not defender_lines[next_idx].strip():
                next_idx += 1
            if next_idx >= len(defender_lines):
                i += 1
                continue

            next_line = defender_lines[next_idx].strip()

            # §17.2 — Comprobar fila mixta antes que cualquier otra detección
            if _is_mixed_row(next_line):
                raise DefeatReportParseError(
                    "La fila de cantidades del defensor mezcla '?' y dígitos. "
                    "Formato de reporte no reconocido."
                )

            # §17.2 — Fila de solo '?': modo perdido
            if _is_defeat_row(next_line):
                # Candidato a cabecera: la línea actual
                candidate_names = re.split(r"\t|  +", line)
                candidate_names = [h.strip() for h in candidate_names if h.strip()]
                # Verificar que la candidata no sea una línea de coordenadas/aldea
                if candidate_names and all(not re.match(r"^\d+$", n) for n in candidate_names):
                    header_names = candidate_names
                    defeat_mode = True
                    rows_numeric = []  # vacío — no hay cantidades en modo perdido
                    break

            # Modo normal: la siguiente línea es numérica
            next_nums = _extract_numbers_from_line(next_line)
            if next_nums and re.match(r"^[\d\s\t]+$", next_line):
                # Esta línea es la cabecera
                header_names = re.split(r"\t|  +", line)
                header_names = [h.strip() for h in header_names if h.strip()]

                # Recopilar filas numéricas
                j = next_idx
                while j < len(defender_lines):
                    ln = defender_lines[j].strip()
                    if ln and re.match(r"^[\d\s\t]+$", ln):
                        rows_numeric.append(_extract_numbers_from_line(ln))
                        j += 1
                    else:
                        break
                break
        i += 1

    # Intento alternativo (solo en modo normal): búsqueda más laxa
    if not defeat_mode and (not header_names or len(rows_numeric) < 2):
        header_names, rows_numeric = _parse_table_flexible(defender_lines)

    if not header_names:
        raise NotNatureOasisError()

    # Validar nombres contra el índice NATURE (§17.4: se valida siempre,
    # incluso en modo perdido — los nombres SÍ aparecen en el reporte perdido)
    unrecognized: list[str] = []
    recognized: list[tuple[str, int]] = []  # (nombre, ordinal)

    for name in header_names:
        name_norm = name.strip().lower()
        if name_norm in nature_index:
            recognized.append((name.strip(), nature_index[name_norm]))
        else:
            unrecognized.append(name.strip())

    if unrecognized:
        raise UnrecognizedAnimalError(unrecognized)

    if not recognized:
        raise NotNatureOasisError()

    # Construir AnimalEntry para cada animal
    entries: list[AnimalEntry] = []

    if defeat_mode:
        # §17.4 — Modo perdido: present/killed/survived = None (desconocido).
        # EC-18: Travian muestra UNA fila de '?'; no se intenta leer segunda fila.
        for name, ordinal in recognized:
            entries.append(AnimalEntry(
                animal_ordinal=ordinal,
                animal_name=name,
                present=None,
                killed=None,
                survived=None,
            ))
    else:
        # Modo normal: rows_numeric[0] = presentes, rows_numeric[1] = muertos
        present_row = rows_numeric[0] if rows_numeric else []
        killed_row = rows_numeric[1] if len(rows_numeric) > 1 else []

        for idx, (name, ordinal) in enumerate(recognized):
            present = present_row[idx] if idx < len(present_row) else 0
            killed = killed_row[idx] if idx < len(killed_row) else 0
            survived = present - killed
            entries.append(AnimalEntry(
                animal_ordinal=ordinal,
                animal_name=name,
                present=present,
                killed=killed,
                survived=survived,
            ))

    return entries


def _parse_troop_table(
    text: str,
    lines: list[str],
    section: str = "attacker",
) -> list[AttackerTroopEntry]:
    """
    Extrae la tabla de tropas de la sección indicada.

    Devuelve una lista de AttackerTroopEntry (con troop_ordinal=None en MVP).
    """
    # Buscar la sección correspondiente
    if section == "attacker":
        pattern = re.compile(
            r"^\s*(Attacker|Atacante|Angreifer|Attaquant|Нападающий|مهاجم|Нападач|"
            r"Útočník|Angriber|Επιτιθέμενος|حمله‌کننده|תוקף|Támadó|Attaccante|"
            r"攻撃者|Puolustaja|Uzbrucējs|Aanvaller|Atakujący|Atacante|Attackerare|"
            r"Saldırgan|Нападник)\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
    else:
        return []

    joined = "\n".join(lines)
    m = pattern.search(joined)
    if not m:
        return []

    section_start = joined[:m.start()].count("\n") + 1
    # La sección del atacante termina donde empieza la del defensor
    _DEFENDER_SECTIONS = re.compile(
        r"^\s*(Defender|Defensor|Verteidiger|Défenseur|Защитник|المدافع|Бранилац|"
        r"Obránce|Forsvarer|Αμυνόμενος|مدافع|מגן|Védő|Difensore|防衛者|"
        r"Gynėjas|Aizstāvis|Verdediger|Obrońca|Defensor|Försvarare|Savunmacı|"
        r"Захисник)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m_def = _DEFENDER_SECTIONS.search(joined, m.end())
    if m_def:
        section_end = joined[:m_def.start()].count("\n") + 1
    else:
        section_end = len(lines)

    section_lines = lines[section_start:section_end]

    header_names: list[str] = []
    rows_numeric: list[list[int]] = []

    # Buscar cabecera y filas numéricas
    i = 0
    while i < len(section_lines):
        line = section_lines[i].strip()
        if not line:
            i += 1
            continue

        # Buscar cabecera: línea de texto seguida de línea numérica
        if i + 1 < len(section_lines):
            next_line = section_lines[i + 1].strip()
            next_nums = _extract_numbers_from_line(next_line)
            if next_nums and re.match(r"^[\d\s\t]+$", next_line):
                candidate_names = re.split(r"\t|  +", line)
                candidate_names = [h.strip() for h in candidate_names if h.strip()]
                # Verificar que no sea una línea de datos (coords, nombre de aldea)
                # La cabecera contiene solo texto, no números aislados
                if all(not re.match(r"^\d+$", n) for n in candidate_names):
                    header_names = candidate_names

                    j = i + 1
                    while j < len(section_lines):
                        ln = section_lines[j].strip()
                        if ln and re.match(r"^[\d\s\t]+$", ln):
                            rows_numeric.append(_extract_numbers_from_line(ln))
                            j += 1
                        else:
                            break
                    break
        i += 1

    if not header_names or len(rows_numeric) < 2:
        header_names, rows_numeric = _parse_table_flexible(section_lines)

    if not header_names or not rows_numeric:
        return []

    sent_row = rows_numeric[0] if rows_numeric else []
    lost_row = rows_numeric[1] if len(rows_numeric) > 1 else []

    entries: list[AttackerTroopEntry] = []
    for idx, name in enumerate(header_names):
        sent = sent_row[idx] if idx < len(sent_row) else 0
        lost = lost_row[idx] if idx < len(lost_row) else 0
        survived = sent - lost
        entries.append(AttackerTroopEntry(
            troop_name=name,
            troop_ordinal=None,  # RN-03: ambiguo entre tribus
            sent=sent,
            lost=lost,
            survived=survived,
        ))

    return entries


def _parse_table_flexible(section_lines: list[str]) -> tuple[list[str], list[list[int]]]:
    """
    Parser de tabla alternativo / más flexible.

    Cuando el formato tiene cabecera y números en filas separadas por tabulaciones
    o cuando hay una sola línea con todos los valores entremezclados.

    Intenta detectar el par (cabecera de texto, filas de números) de forma más laxa.
    """
    # Estrategia: filtrar líneas no vacías y buscar la primera línea numérica
    non_empty = [ln.strip() for ln in section_lines if ln.strip()]

    header: list[str] = []
    rows: list[list[int]] = []

    for i, line in enumerate(non_empty):
        # ¿Es esta línea solo dígitos y espacios/tabs?
        if re.match(r"^[\d\s\t]+$", line) and _extract_numbers_from_line(line):
            # La línea anterior (si existe) es la cabecera
            if i > 0:
                prev = non_empty[i - 1]
                # La cabecera no debe ser solo números
                if not re.match(r"^[\d\s\t]+$", prev):
                    header = re.split(r"\t|  +", prev)
                    header = [h.strip() for h in header if h.strip()]

            # Recopilar filas numéricas consecutivas
            j = i
            while j < len(non_empty):
                ln = non_empty[j]
                if re.match(r"^[\d\s\t]+$", ln) and ln.strip():
                    rows.append(_extract_numbers_from_line(ln))
                    j += 1
                else:
                    break
            break

    return header, rows


def _extract_bounty(
    text: str,
    lines: list[str],
) -> tuple[BountyData, dict | None]:
    """
    Extrae el bloque de botín del reporte.

    Formato típico:
        Bounty (o Resources, Beute, Butin, Добыча…)
        480  480  480  480        ← wood clay iron crop
        120/240                   ← capacity_used/total
        [Additional resources were added to the hero's inventory...]
        48  48  48  48            ← hero_inventory (opcional)

    Devuelve (BountyData, hero_inventory_dict | None).
    """
    # Buscar sección de botín (varía por idioma)
    _BOUNTY_SECTIONS = re.compile(
        r"^\s*(Bounty|Resources|Beute|Butin|Добыча|Ресурсы|غنائم|Плен|"
        r"Kořist|Bytte|Λάφυρα|غنیمت|שלל|Zsákmány|Bottino|戦利品|"
        r"Grobis|Laupījums|Buit|Łupy|Espólio|Plunder|Plundra|Ganimet|"
        r"Здобич|Plunder|Reward)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    joined = "\n".join(lines)
    m_bounty = _BOUNTY_SECTIONS.search(joined)

    # Valores por defecto
    wood = clay = iron = crop = 0
    capacity_used = capacity_total = 0
    hero_inventory: dict | None = None

    if not m_bounty:
        # Intentar extraer de forma más genérica — buscar la línea de capacidad
        # y los 4 números antes de ella
        return BountyData(wood=0, clay=0, iron=0, crop=0,
                          capacity_used=0, capacity_total=0), None

    bounty_start = joined[:m_bounty.start()].count("\n") + 1
    bounty_lines = lines[bounty_start:bounty_start + 20]  # ventana del bloque de botín

    # Travian tiene dos layouts para el botín:
    #   A) los 4 recursos en una sola línea:  "37 147 37 37"
    #   B) un recurso por línea:               "37" / "147" / "37" / "37"
    # Y, opcionalmente, tras una señal de inventario, los 4 del héroe en el mismo
    # layout. Recogemos números en orden, separando lo previo a la capacidad
    # (botín) de lo posterior a la señal de inventario (héroe).
    before_capacity: list[int] = []   # números de botín (antes de la línea de capacidad)
    inventory_nums: list[int] = []    # números del inventario del héroe
    found_capacity = False
    inventory_signal_seen = False

    # Una línea es "puramente numérica" si solo tiene dígitos/espacios/tabs (ya sin
    # comas ni control bidi gracias a _normalize_raw_text).
    _PURE_NUMERIC = re.compile(r"^[\d\s\t]+$")

    for line in bounty_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Señal de inventario del héroe (texto): a partir de aquí los números van al héroe.
        if _INVENTORY_SIGNAL.search(stripped):
            inventory_signal_seen = True
            continue

        # Línea de capacidad: "N/M" → cierra la recogida de recursos del botín.
        m_cap = _CAPACITY_PATTERN.search(stripped)
        if m_cap and not found_capacity:
            capacity_used = int(m_cap.group(1))
            capacity_total = int(m_cap.group(2))
            found_capacity = True
            continue

        # Línea de números puros → recursos (botín o inventario del héroe).
        if _PURE_NUMERIC.match(stripped):
            nums = _extract_numbers_from_line(stripped)
            if inventory_signal_seen:
                inventory_nums.extend(nums)
            elif not found_capacity:
                before_capacity.extend(nums)
            continue

        # Línea de texto que no es señal de inventario (p.ej. "Defender"): fin del
        # bloque de botín. Cortar para no contaminar con la tabla del defensor.
        if before_capacity or found_capacity or inventory_signal_seen:
            break

    # Asignar los primeros 4 números del botín (wood, clay, iron, crop).
    if len(before_capacity) >= 4:
        wood, clay, iron, crop = before_capacity[:4]

    # Inventario del héroe: primeros 4 números tras la señal.
    if len(inventory_nums) >= 4:
        hero_inventory = {
            "wood": inventory_nums[0],
            "clay": inventory_nums[1],
            "iron": inventory_nums[2],
            "crop": inventory_nums[3],
        }

    return (
        BountyData(
            wood=wood,
            clay=clay,
            iron=iron,
            crop=crop,
            capacity_used=capacity_used,
            capacity_total=capacity_total,
        ),
        hero_inventory,
    )
