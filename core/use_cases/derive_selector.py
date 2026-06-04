"""
Algoritmo de derivación de selectores CSS estructurales.

Función pura: no tiene IO, no depende de adaptadores. Recibe el outerHTML
de un elemento HTML y devuelve el mejor selector CSS estructural según una
heurística priorizada (RN-NP05 del spec noise-path-wizard.md §8.1).

Spec noise-path-wizard.md §9.2 (pseudocódigo) y §4 (RN-NP05).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# Patrones de detección
# ---------------------------------------------------------------------------

# IDs auto-generados: ember, __react, hex hash 8+ chars, empieza por dígito,
# patrón "letra(s)-número(s)" tipo "label-1" (ej. React).
AUTO_ID_PATTERN = re.compile(
    r"^[0-9]|ember|__react|[0-9a-f]{8,}|^[a-z]+-[0-9]+$",
    re.IGNORECASE,
)

# Valores de atributos data-* potencialmente inestables: timestamps (4+ dígitos),
# hashes hex de 6+ chars.
UNSTABLE_DATA_PATTERN = re.compile(
    r"[0-9]{4,}|\b[0-9a-f]{6,}\b",
)

# Clases utilitarias Tailwind / reset CSS que no aportan semántica.
UTILITY_CLASS_PATTERN = re.compile(
    r"^[wh]-\d|^[mp][trblxy]?-\d|^text-[a-z]|^bg-[a-z]|^flex|^grid|^block|^inline|^hidden"
    r"|^border|^rounded|^shadow|^items-|^justify-|^gap-|^p-[0-9]|^m-[0-9]"
    r"|^col-|^row-|^font-|^leading-|^tracking-|^overflow|^z-[0-9]",
    re.IGNORECASE,
)

# Tamaño máximo de outerHTML aceptado (50 KB)
MAX_OUTER_HTML_BYTES = 50 * 1024


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@dataclass
class DeriveSelectorResult:
    """Resultado del algoritmo de derivación de selector."""
    selector: str
    is_unique: bool
    priority_level: int                             # 1-9 (ver RN-NP05)
    method: str                                     # "id", "name", "gid", "href_exact",
                                                    # "href_partial", "data_attr",
                                                    # "class_combo", "context_combo", "fallback"
    warning: str | None = None
    alternatives: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser HTML mínimo
# ---------------------------------------------------------------------------

class _FirstElementParser(HTMLParser):
    """
    Extrae el tag y atributos del primer elemento HTML del fragmento.
    Devuelve (tag, attrs_dict) o lanza ValueError si no hay elemento válido.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tag: str | None = None
        self.attrs: dict[str, str] = {}
        self._done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        self.tag = tag.lower()
        self.attrs = {k.lower(): (v or "") for k, v in attrs}
        self._done = True


def _parse_first_element(outer_html: str) -> tuple[str, dict[str, str]]:
    """
    Parsea el outerHTML y devuelve (tag, attrs_dict) del elemento raíz.
    Lanza ValueError si no puede encontrar un elemento válido.
    """
    parser = _FirstElementParser()
    try:
        parser.feed(outer_html.strip())
    except Exception as exc:
        raise ValueError("El outerHTML no pudo parsearse como HTML válido.") from exc

    if parser.tag is None:
        raise ValueError("El outerHTML no pudo parsearse como HTML válido.")

    return parser.tag, parser.attrs


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def derive_selector(outer_html: str) -> DeriveSelectorResult:
    """
    Analiza el outerHTML de un elemento HTML y devuelve el mejor selector
    CSS estructural según la heurística priorizada de RN-NP05.

    Parámetros:
        outer_html: HTML completo del elemento (obtenido con "Copiar outerHTML"
                    en DevTools). Se analiza solo el elemento raíz del fragmento.

    Devuelve:
        DeriveSelectorResult con selector recomendado, nivel de prioridad,
        método usado, flag de unicidad (heurístico), aviso y alternativas.

    Lanza:
        ValueError: si outer_html está vacío o no parsea como HTML válido.

    Nota sobre unicidad:
        is_unique=True significa "el selector es estructuralmente estable y
        único según la heurística aplicada sobre el FRAGMENTO HTML". No garantiza
        unicidad en el documento real de Travian. La verificación definitiva es
        expected_url_after_click en runtime (RN-NP05, limitación inherente).
    """
    if not outer_html or not outer_html.strip():
        raise ValueError("outer_html no puede estar vacío.")

    if len(outer_html.encode("utf-8")) > MAX_OUTER_HTML_BYTES:
        raise ValueError(
            f"outer_html excede el límite de {MAX_OUTER_HTML_BYTES // 1024} KB."
        )

    tag, attrs = _parse_first_element(outer_html)

    # ------------------------------------------------------------------
    # Nivel 1: id no auto-generado
    # ------------------------------------------------------------------
    id_val = attrs.get("id", "").strip()
    if id_val and not AUTO_ID_PATTERN.search(id_val):
        return DeriveSelectorResult(
            selector=f"#{id_val}",
            is_unique=True,
            priority_level=1,
            method="id",
        )

    # ------------------------------------------------------------------
    # Nivel 2: atributo name
    # ------------------------------------------------------------------
    name_val = attrs.get("name", "").strip()
    if name_val:
        return DeriveSelectorResult(
            selector=f"{tag}[name='{name_val}']",
            is_unique=True,
            priority_level=2,
            method="name",
        )

    # ------------------------------------------------------------------
    # Nivel 3-5: solo para elementos <a>
    # ------------------------------------------------------------------
    if tag == "a":
        href = attrs.get("href", "").strip()

        # Nivel 3: a[href*="gid=N"]
        gid_match = re.search(r"gid=(\d+)", href)
        if gid_match:
            return DeriveSelectorResult(
                selector=f"a[href*='gid={gid_match.group(1)}']",
                is_unique=True,
                priority_level=3,
                method="gid",
            )

        # Nivel 4: href exacto (ruta fija sin query strings ni hash, empieza por /)
        if href and "?" not in href and "#" not in href and href.startswith("/"):
            return DeriveSelectorResult(
                selector=f"a[href='{href}']",
                is_unique=True,
                priority_level=4,
                method="href_exact",
            )

        # Nivel 5: href parcial estable (extrae el path antes de ? o #)
        if href and href.startswith("/"):
            path_part = href.split("?")[0].split("#")[0]
            if len(path_part) > 1:
                return DeriveSelectorResult(
                    selector=f"a[href*='{path_part}']",
                    is_unique=True,   # heurística — no garantizada en el documento real
                    priority_level=5,
                    method="href_partial",
                    warning=(
                        "Selector basado en href parcial. "
                        "Verifica unicidad en el contexto real del documento."
                    ),
                )

    # ------------------------------------------------------------------
    # Nivel 6: atributos data-* con valores estables
    # ------------------------------------------------------------------
    stable_data = {
        k: v for k, v in attrs.items()
        if k.startswith("data-") and v and not UNSTABLE_DATA_PATTERN.search(v)
    }
    if stable_data:
        k, v = next(iter(stable_data.items()))
        return DeriveSelectorResult(
            selector=f"{tag}[{k}='{v}']",
            is_unique=True,
            priority_level=6,
            method="data_attr",
        )

    # ------------------------------------------------------------------
    # Nivel 7: clases CSS semánticas (no utilitarias)
    # ------------------------------------------------------------------
    raw_classes = attrs.get("class", "").split()
    semantic_classes = [
        c for c in raw_classes if not UTILITY_CLASS_PATTERN.match(c)
    ]
    if semantic_classes:
        # Máximo 2 clases para el selector principal
        class_sel = ".".join(semantic_classes[:2])
        alternatives = [f".{semantic_classes[0]}"] if len(semantic_classes) > 1 else []
        return DeriveSelectorResult(
            selector=f"{tag}.{class_sel}",
            is_unique=False,
            priority_level=7,
            method="class_combo",
            warning=(
                "Selector basado en clases CSS. "
                "Puede no ser único en el documento real de Travian."
            ),
            alternatives=alternatives,
        )

    # ------------------------------------------------------------------
    # Nivel 8/9: fallback — solo el tag, muy poco específico
    # ------------------------------------------------------------------
    return DeriveSelectorResult(
        selector=tag,
        is_unique=False,
        priority_level=9,
        method="fallback",
        warning=(
            "No se encontró un selector único estable en el fragmento HTML proporcionado. "
            "Considera añadir un atributo id o data-* al elemento, "
            "o usa un selector manual estructural."
        ),
        alternatives=[],
    )
