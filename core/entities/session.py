"""
Entidades del dominio de Human Sessions.

Define los tipos de datos y funciones puras para el sistema de timeline
horario de actividad con tres modos (HARDCORE / PASIVO / DISCONNECTED).

Secciones del spec:
  §7.1  SessionMode
  §7.2  SessionBlock
  §7.3  SessionTimeline
  §7.4  SessionOverride
  §7.5  SessionConfig
  §9.2  _find_active_block, _block_end_as_datetime, current_mode  (funciones puras)
  §8    Constantes de defaults hardcodeados (RN-HS11)

Las funciones puras de cálculo de modo no tienen IO ni estado: reciben el
timeline y datetime.now() y devuelven el modo activo + el instante de fin con
jitter. Se colocan en este módulo para que sean testables sin BD ni WorldAgent.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


# ---------------------------------------------------------------------------
# §7.1 — Enum SessionMode
# ---------------------------------------------------------------------------

class SessionMode(str, Enum):
    HARDCORE     = "HARDCORE"
    PASIVO       = "PASIVO"
    DISCONNECTED = "DISCONNECTED"


# ---------------------------------------------------------------------------
# §7.2 — SessionBlock
# ---------------------------------------------------------------------------

@dataclass
class SessionBlock:
    start_hour:   int          # 0-23
    start_minute: int          # 0-59
    end_hour:     int          # 0-24  (24 = medianoche del día siguiente)
    end_minute:   int          # 0-59  (0 si end_hour=24)
    mode:         SessionMode


# ---------------------------------------------------------------------------
# §7.3 — SessionTimeline
# ---------------------------------------------------------------------------

@dataclass
class SessionTimeline:
    world_id:       int
    weekday:        int                  # 0=lun … 6=dom
    blocks:         list[SessionBlock]   # ordenados por start_hour:start_minute
    jitter_minutes: int  = 15            # ±N min en cada borde de bloque
    is_default:     bool = False         # True si usa el default hardcodeado, no BD


# ---------------------------------------------------------------------------
# §7.4 — SessionOverride
# ---------------------------------------------------------------------------

@dataclass
class SessionOverride:
    world_id:   int
    mode:       SessionMode
    expires_at: datetime          # ISO-8601 UTC; fin del bloque actual con jitter


# ---------------------------------------------------------------------------
# §7.5 — SessionConfig
# ---------------------------------------------------------------------------

@dataclass
class SessionConfig:
    world_id:                 int
    passive_interval_factor:  float = 2.0   # rango [1.5, 5.0]
    passive_send_probability: float = 0.05  # rango [0.01, 0.50]


# ---------------------------------------------------------------------------
# §RN-HS11 — Timeline por defecto hardcodeado
# ---------------------------------------------------------------------------

def _make_default_blocks(is_weekend: bool) -> list[SessionBlock]:
    """
    Lun-Vie:  08:00-23:00 HARDCORE / 23:00-24:00 + 00:00-08:00 DISCONNECTED
    Sáb-Dom:  09:00-24:00 HARDCORE / 00:00-09:00 DISCONNECTED

    Nota: los bloques siempre cubren 00:00-24:00 en espacio lineal (sin cruce
    de medianoche), por lo que el DISCONNECTED nocturno se parte en dos:
    00:00-08:00 y 23:00-24:00 para lunes-viernes.
    """
    if is_weekend:
        return [
            SessionBlock(0, 0, 9, 0, SessionMode.DISCONNECTED),
            SessionBlock(9, 0, 24, 0, SessionMode.HARDCORE),
        ]
    else:
        return [
            SessionBlock(0, 0, 8, 0, SessionMode.DISCONNECTED),
            SessionBlock(8, 0, 23, 0, SessionMode.HARDCORE),
            SessionBlock(23, 0, 24, 0, SessionMode.DISCONNECTED),
        ]


def get_default_timeline(world_id: int, weekday: int) -> SessionTimeline:
    """
    Devuelve el timeline por defecto para el (world_id, weekday) dado.
    Se usa cuando el usuario no ha configurado ese día en BD.
    """
    is_weekend = weekday in (5, 6)  # sábado=5, domingo=6
    return SessionTimeline(
        world_id=world_id,
        weekday=weekday,
        blocks=_make_default_blocks(is_weekend),
        jitter_minutes=15,
        is_default=True,
    )


# ---------------------------------------------------------------------------
# §9.2 — Funciones puras de cálculo de modo
# ---------------------------------------------------------------------------

def _find_active_block(blocks: list[SessionBlock], now: datetime) -> SessionBlock:
    """
    Encuentra el bloque activo para el instante 'now'.

    Los bloques cubren 24h sin huecos (invariante garantizado en la escritura).
    El bloque activo es el que contiene 'now' en [start, end).

    Soporta bloques que cruzan medianoche (end_m < start_m), aunque el PUT
    de timeline los prohíbe en persistencia — se mantiene aquí por completitud
    de la lógica de runtime (§8.3, nota sobre bloques que cruzan medianoche).
    """
    current_minutes = now.hour * 60 + now.minute
    for block in blocks:
        start_m = block.start_hour * 60 + block.start_minute
        end_m   = block.end_hour * 60 + block.end_minute   # 24*60=1440
        if end_m == 0:
            end_m = 1440  # end_hour=24 → medianoche del día siguiente

        if start_m < end_m:
            # Bloque normal (no cruza medianoche)
            if start_m <= current_minutes < end_m:
                return block
        else:
            # Bloque que cruza medianoche (p.ej. 23:00-08:00)
            if current_minutes >= start_m or current_minutes < end_m:
                return block

    # Invariante roto: nunca debería llegar aquí si el timeline cubre 24h
    raise RuntimeError(
        f"Timeline no cubre el instante actual {now.strftime('%H:%M')} — invariante roto"
    )


def _block_end_as_datetime(block: SessionBlock, now: datetime) -> datetime:
    """
    Calcula el datetime de fin nominal del bloque dado, relativo al día de 'now'.
    Si end_hour=24 (medianoche), se convierte en el inicio del día siguiente.
    """
    if block.end_hour == 24:
        # Medianoche del día siguiente
        next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return next_day
    return now.replace(
        hour=block.end_hour,
        minute=block.end_minute,
        second=0,
        microsecond=0,
    )


def current_mode(
    now: datetime,
    timeline: SessionTimeline,
    override: SessionOverride | None,
) -> tuple[SessionMode, datetime]:
    """
    Dado el instante actual, el timeline del día y un posible override, devuelve:
    - el SessionMode activo
    - el instante de fin del bloque activo CON JITTER (jitter_fin)

    Si hay override activo (no expirado) → devuelve el modo del override y
    su expires_at como jitter_fin (el override ya tiene el jitter calculado).

    Spec §9.2.
    """
    # 1. Override prevalece si no ha expirado
    if override is not None:
        # Normalizar timezone para la comparación: si uno es naive y el otro aware,
        # convertir 'now' a offset-aware UTC asumiendo que es local-naive UTC.
        exp = override.expires_at
        now_cmp = now
        if exp.tzinfo is not None and now_cmp.tzinfo is None:
            from datetime import timezone as _tz
            now_cmp = now_cmp.replace(tzinfo=_tz.utc)
        elif exp.tzinfo is None and now_cmp.tzinfo is not None:
            from datetime import timezone as _tz
            exp = exp.replace(tzinfo=_tz.utc)
        if now_cmp < exp:
            return override.mode, override.expires_at

    # 2. Encontrar el bloque activo en el timeline
    active_block = _find_active_block(timeline.blocks, now)

    # 3. Calcular el borde de fin nominal
    fin_nominal = _block_end_as_datetime(active_block, now)

    # 4. Aplicar jitter aleatorio ±jitter_minutes
    jitter_seconds = random.uniform(
        -timeline.jitter_minutes * 60,
        +timeline.jitter_minutes * 60,
    )
    jitter_fin = fin_nominal + timedelta(seconds=jitter_seconds)

    # 5. Garantía EC-HS03: jitter_fin >= now + 1 min
    min_fin = now + timedelta(minutes=1)
    if jitter_fin < min_fin:
        jitter_fin = min_fin

    return active_block.mode, jitter_fin


def calculate_jitter_fin_for_now(
    now: datetime,
    timeline: SessionTimeline,
) -> datetime:
    """
    Calcula el jitter_fin del bloque activo en 'now' sin considerar overrides.
    Se usa en PUT /session/mode para calcular expires_at del override nuevo.
    """
    _, jitter_fin = current_mode(now, timeline, override=None)
    return jitter_fin
