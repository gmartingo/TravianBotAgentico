"""
Adaptador de traducciones basado en archivos JSON.

Implementa TranslationPort leyendo catálogos de:
  - core/i18n/catalog/base/    — datos oficiales de Travian (versionados en git)
  - core/i18n/catalog/override/ — ajustes puntuales (ganan entrada por entrada sobre base)

El catálogo se carga una sola vez en __init__ y se mantiene en memoria.
Las consultas son lookups O(1) en dicts.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.entities.tribe import Tribe
from core.exceptions import TroopNotFoundError
from core.i18n.languages import DEFAULT_LANGUAGE
from core.ports.translation_port import TranslationPort


class JsonTranslationAdapter(TranslationPort):
    """
    Adaptador de traducciones que lee catálogos JSON de base + override.

    Parámetros
    ----------
    base_dir:
        Directorio con los archivos JSON base (buildings.json, troops.json, messages.json).
    override_dir:
        Directorio con los archivos JSON override (opcionales — si no existen se ignoran).
    """

    def __init__(self, base_dir: Path, override_dir: Path) -> None:
        base_buildings = self._load_json_required(base_dir / "buildings.json")
        base_troops = self._load_json_required(base_dir / "troops.json")
        base_messages = self._load_json_required(base_dir / "messages.json")

        ov_buildings = self._load_json_optional(override_dir / "buildings.json")
        ov_troops = self._load_json_optional(override_dir / "troops.json")
        ov_messages = self._load_json_optional(override_dir / "messages.json")

        # Override gana entrada por entrada (merge de nivel superior)
        self._buildings: dict[str, dict] = {**base_buildings, **ov_buildings}
        self._troops: dict[str, dict] = {**base_troops, **ov_troops}
        self._messages: dict[str, dict] = {**base_messages, **ov_messages}

    # ------------------------------------------------------------------
    # Carga de JSON
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json_required(path: Path) -> dict:
        """Carga un JSON obligatorio. Lanza RuntimeError si falta o está corrupto."""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise RuntimeError(
                f"Catálogo base obligatorio no encontrado: {path}"
            ) from None
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"JSON corrupto en catálogo base: {path} — {exc}"
            ) from exc

    @staticmethod
    def _load_json_optional(path: Path) -> dict:
        """Carga un JSON opcional. Devuelve {} si el archivo no existe."""
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"JSON corrupto en catálogo override: {path} — {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Implementación de TranslationPort
    # ------------------------------------------------------------------

    def get_building_name(self, gid: int, lang: str) -> str:
        """
        Devuelve el nombre del edificio. Fallback granular a 'es' si falta la
        traducción para lang. Devuelve f"building_{gid}" si el gid es desconocido.
        """
        key = str(gid)
        entry = self._buildings.get(key)
        if entry is None:
            return f"building_{gid}"
        name = entry.get(lang, "").strip()
        if not name:
            name = entry.get(DEFAULT_LANGUAGE, "").strip()
        return name or f"building_{gid}"

    def get_all_buildings(self, lang: str) -> list[dict]:
        """
        Devuelve todos los edificios con el idioma efectivamente servido por item.

        Cada elemento: {"gid": int, "alias": str, "lang_servido": str, "nombre": str}
        """
        result = []
        for key, entry in self._buildings.items():
            gid = int(key)
            alias = entry.get("alias", f"building_{gid}")
            name = entry.get(lang, "").strip()
            if name:
                lang_servido = lang
            else:
                name = entry.get(DEFAULT_LANGUAGE, "").strip() or f"building_{gid}"
                lang_servido = DEFAULT_LANGUAGE
            result.append({
                "gid": gid,
                "alias": alias,
                "lang_servido": lang_servido,
                "nombre": name,
            })
        return result

    def get_troop_name(self, tribe: Tribe, ordinal: int, lang: str) -> str:
        """
        Devuelve el nombre de la tropa. Fallback a 'es' si falta la traducción.
        Lanza TroopNotFoundError si el ordinal no existe para la tribu.
        """
        key = f"{tribe.value.upper()}_{ordinal}"
        entry = self._troops.get(key)
        if entry is None:
            raise TroopNotFoundError(tribe=tribe, ordinal=ordinal)
        name = entry.get(lang, "").strip()
        if not name:
            name = entry.get(DEFAULT_LANGUAGE, "").strip()
        return name or f"{key}_unknown"

    def get_troop_names_by_tribe(self, tribe: Tribe, lang: str) -> list[dict]:
        """
        Devuelve todas las tropas de una tribu con el idioma efectivamente servido.

        Cada elemento: {"ordinal": int, "key": str, "lang_servido": str, "nombre": str}
        Lanza TroopNotFoundError (ordinal=None) si la tribu no tiene tropas en el catálogo.
        """
        prefix = f"{tribe.value.upper()}_"
        entries = {k: v for k, v in self._troops.items() if k.startswith(prefix)}
        if not entries:
            raise TroopNotFoundError(tribe=tribe, ordinal=None)
        result = []
        for key, entry in sorted(entries.items(),
                                  key=lambda kv: int(kv[0].split("_")[-1])):
            ordinal = int(key.split("_")[-1])
            name = entry.get(lang, "").strip()
            if name:
                lang_servido = lang
            else:
                name = entry.get(DEFAULT_LANGUAGE, "").strip() or f"{key}_unknown"
                lang_servido = DEFAULT_LANGUAGE
            result.append({
                "ordinal": ordinal,
                "key": key,
                "lang_servido": lang_servido,
                "nombre": name,
            })
        return result

    def get_message(self, code: str, lang: str, **params) -> str:
        """
        Devuelve el mensaje de error localizado para el code dado.
        Fallback a 'es' si falta la traducción. Fallback al code plano si el
        code no existe en el catálogo. Nunca lanza excepción.
        """
        entry = self._messages.get(code)
        if entry is None:
            return f"{code} {params}"
        template = entry.get(lang, "").strip()
        if not template:
            template = entry.get(DEFAULT_LANGUAGE, "").strip()
        if not template:
            return f"{code} {params}"
        try:
            return template.format(**params)
        except KeyError:
            return template  # params incompletos — devuelve template sin interpolar
