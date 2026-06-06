"""
Servicio de dominio puro para el catálogo de plantillas de rutas.

Lógica de negocio sin dependencias de adaptadores ni de infraestructura.
Recibe el puerto como parámetro (inyección de dependencias).

Funciones:
  - validate_no_cycle: detecta ciclos en la cadena de orígenes al editar.
  - validate_chain_integrity: verifica que la cadena del origen propuesto
    no contiene ciclos internos (para creación, donde el ID aún no existe).
  - resolve_origin_chain: aplana la cadena raíz→hoja en lista de ResolvedStep.
  - validate_selector_is_structural: rechaza selectores por texto visible.

Excepciones:
  - CyclicOriginError: ciclo detectado en la cadena de orígenes.
  - TemplateNotFoundError: plantilla referenciada no existe.

Spec route-templates-developer-portal.md §v2.3, §v2.4, §v2-REGLA-SELECTORES.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from core.entities.noise import NavigationStep, RouteTemplate
from core.ports.route_template_db_port import RouteTemplateDbPort


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------

class CyclicOriginError(Exception):
    """
    Se lanza cuando origin_template_id crearía un ciclo en la cadena de
    orígenes, o cuando la cadena supera el límite de profundidad (max_depth).

    cycle_path: lista de IDs de la cadena en el punto en que se detectó el ciclo
                o se alcanzó el límite. Puede incluir el ID que causó el ciclo.

    Spec §v2.3: error HTTP 409 con cycle_path en el body.
    """
    def __init__(self, cycle_path: list[int]) -> None:
        self.cycle_path = cycle_path
        super().__init__(f"Ciclo detectado en cadena de orígenes: {cycle_path}")


class TemplateNotFoundError(Exception):
    """Se lanza cuando una plantilla referenciada en la cadena no existe en BD."""
    def __init__(self, template_id: int) -> None:
        self.template_id = template_id
        super().__init__(f"Plantilla {template_id} no encontrada.")


# ---------------------------------------------------------------------------
# ResolvedStep — salida de resolve_origin_chain
# ---------------------------------------------------------------------------

@dataclass
class ResolvedStep:
    """
    Un clic resuelto en la cadena de ejecución, en orden de ejecución.

    El motor de producción (_execute_noise_action) y el modo test (EP-RT10)
    iteran esta lista para ejecutar human_click + delay + verify_url en cada paso.

    Spec §v2.4.
    """
    template_id: int
    template_slug: str
    label: str
    path_id: int                      # ID del RouteTemplatePath en BD
    step: NavigationStep              # el único step del path atómico
    expected_url: str | None          # = step.expected_url_after_click


# ---------------------------------------------------------------------------
# Constante de profundidad máxima
# ---------------------------------------------------------------------------

_MAX_CHAIN_DEPTH = 20


# ---------------------------------------------------------------------------
# Validación de cadena en CREACIÓN (sin ID propio aún)
# ---------------------------------------------------------------------------

async def validate_chain_integrity(
    proposed_origin_id: int,
    db: RouteTemplateDbPort,
    max_depth: int = _MAX_CHAIN_DEPTH,
) -> None:
    """
    Verifica que la cadena del origen propuesto no contiene ciclos internos
    ni supera el límite de profundidad.

    Se llama en POST /route-templates cuando origin_template_id != None.
    En creación el ID de la nueva plantilla aún no existe, por lo que no puede
    formar un ciclo consigo misma. Solo verificamos la integridad de la cadena
    ascendente del origen.

    Lanza CyclicOriginError si la cadena tiene ciclo o supera max_depth.

    Spec §v2.11 (pseudocódigo de creación).
    """
    visited: list[int] = []
    current_id: int | None = proposed_origin_id

    while current_id is not None:
        if current_id in visited:
            raise CyclicOriginError(visited + [current_id])
        visited.append(current_id)
        if len(visited) > max_depth:
            raise CyclicOriginError(visited)

        ancestor = await db.get_template(current_id)
        if ancestor is None:
            # Origen apunta a una plantilla que no existe: rompe la cadena.
            # No es un ciclo, pero sí es un error (OriginNotFoundError lo
            # gestiona el handler antes de llegar aquí).
            break
        current_id = ancestor.origin_template_id


# ---------------------------------------------------------------------------
# Validación anti-ciclos en EDICIÓN
# ---------------------------------------------------------------------------

async def validate_no_cycle(
    new_template_id: int,
    proposed_origin_id: int,
    db: RouteTemplateDbPort,
    max_depth: int = _MAX_CHAIN_DEPTH,
) -> None:
    """
    Recorre la cadena de orígenes empezando por proposed_origin_id.
    Lanza CyclicOriginError si new_template_id aparece en la cadena
    (ciclo directo o indirecto) o si la profundidad supera max_depth.

    Complejidad: O(d) queries donde d es la profundidad de la cadena.
    Para d <= 20 y un catálogo < 200 plantillas es imperceptible.

    Casos cubiertos (spec §v2.3 + EC-V2-01..EC-V2-04):
      EC-V2-01: auto-ciclo A → A (new_template_id == proposed_origin_id)
      EC-V2-02: ciclo indirecto C → B → A → C
      EC-V2-03: origen borrado — rompe la cadena limpiamente (no es ciclo)
      EC-V2-04: cadena > 20 niveles → CyclicOriginError

    Spec §v2.3.
    """
    visited: list[int] = []
    current_id: int | None = proposed_origin_id

    while current_id is not None:
        if current_id == new_template_id:
            # El ID que se está editando aparece en su propia cadena ascendente.
            raise CyclicOriginError(visited + [current_id])
        if current_id in visited:
            # Ciclo entre terceros (no involucra a new_template_id directamente,
            # pero la cadena es corrupta).
            raise CyclicOriginError(visited + [current_id])
        visited.append(current_id)
        if len(visited) > max_depth:
            raise CyclicOriginError(visited)

        ancestor = await db.get_template(current_id)
        if ancestor is None:
            # Origen apunta a plantilla que ya no existe: rompe la cadena limpiamente.
            break
        current_id = ancestor.origin_template_id


# ---------------------------------------------------------------------------
# Resolución de la cadena raíz→hoja
# ---------------------------------------------------------------------------

async def resolve_origin_chain(
    template_id: int,
    db: RouteTemplateDbPort,
    max_depth: int = _MAX_CHAIN_DEPTH,
) -> list[ResolvedStep]:
    """
    Devuelve la lista ORDENADA de pasos en orden de ejecución:
    [ResolvedStep_raíz, ..., ResolvedStep_plantilla_solicitada].

    Algoritmo:
    1. Cargar la plantilla y todos sus antecesores siguiendo origin_template_id
       hacia arriba, formando la lista [solicitada, padre, abuelo, ..., raíz]
       (en orden INVERSO a la ejecución).
    2. Invertir la lista → [raíz, ..., solicitada] (orden de ejecución).
    3. Para cada nodo en orden: cargar su RouteTemplatePath[0] (el único path
       atómico) y su NavigationStep[0] (el único step atómico).
       Nodos sin path o sin step se SALTAN (EC-V2-07).
    4. Devolver la lista de ResolvedStep.

    Lanza:
      - TemplateNotFoundError: si cualquier plantilla de la cadena no existe
        (incluido el template_id inicial).
      - CyclicOriginError: si detecta ciclo (defensa; la validación en escritura
        ya debería prevenirlo).

    Spec §v2.4.
    """
    chain: list[RouteTemplate] = []
    current_id: int | None = template_id
    visited: set[int] = set()

    while current_id is not None:
        if current_id in visited:
            raise CyclicOriginError(list(visited))
        visited.add(current_id)
        if len(visited) > max_depth:
            raise CyclicOriginError(list(visited))

        tpl = await db.get_template(current_id)
        if tpl is None:
            raise TemplateNotFoundError(current_id)
        chain.append(tpl)
        current_id = tpl.origin_template_id

    # chain es [solicitada, padre, ..., raíz] — invertir para orden de ejecución
    chain.reverse()  # → [raíz, ..., solicitada]

    resolved: list[ResolvedStep] = []
    for tpl in chain:
        paths = tpl.paths
        if not paths:
            # Nodo sin path: EC-V2-07 — se salta, no aporta clic a la cadena.
            continue
        path = paths[0]          # atómico: exactamente 1 path por ruta atómica
        if not path.steps:
            continue             # path sin step: idem
        step = path.steps[0]     # atómico: exactamente 1 step por path atómico

        assert tpl.id is not None, "plantilla recuperada de BD debe tener ID"
        assert path.id is not None, "path recuperado de BD debe tener ID"

        resolved.append(ResolvedStep(
            template_id=tpl.id,
            template_slug=tpl.slug,
            label=tpl.label,
            path_id=path.id,
            step=step,
            expected_url=step.expected_url_after_click,
        ))

    return resolved


# ---------------------------------------------------------------------------
# Validación de selectores estructurales (GAP-4, §v2-REGLA-SELECTORES)
# ---------------------------------------------------------------------------

# Patrones prohibidos en selectores de steps — selección por texto visible.
# Travian tiene 25 idiomas; un selector por texto se rompe al cambiar de idioma.
_FORBIDDEN_SELECTOR_PATTERNS: tuple[str, ...] = (
    ":has-text(",
    ":contains(",
    "text()=",
    "contains(text(),",
)


def validate_selector_is_structural(selector: str) -> None:
    """
    Valida que el selector no usa selección por texto visible.

    Lanza ValueError con mensaje legible (multi-idioma) si el selector contiene
    alguno de los patrones prohibidos de §v2-REGLA-SELECTORES.

    Se llama desde los handlers de EP-RT02 y EP-RT04 antes de persistir.
    La excepción se traduce a HTTP 422 en el router.

    Spec §v2-REGLA-SELECTORES, EC-RT12 (actualizado).
    """
    for pattern in _FORBIDDEN_SELECTOR_PATTERNS:
        if pattern in selector:
            raise ValueError(
                f"El selector '{selector}' usa selección por texto visible, "
                "que cambia según el idioma (Travian tiene 25 idiomas). "
                "Usa un selector estructural: atributo (href, id, class, name), "
                "tipo de elemento o posición DOM."
            )


def to_world_relative_url(url: str | None) -> str | None:
    """
    Normaliza una URL a relativa al mundo, quitando scheme + host.

    El catálogo de plantillas es GLOBAL (sin mundo). El desarrollador puede pegar
    la URL completa de un mundo concreto (p.ej.
    'https://ts20.x2.america.travian.com/dorf1.php?x=1'); se almacena SOLO la parte
    relativa ('/dorf1.php?x=1') para que al ASIGNAR la ruta a un mundo se le
    anteponga la base de ESE mundo (build_url). Así la plantilla nunca queda con un
    mundo cableado.

    - URL absoluta (con scheme y/o host) -> path [+ '?'+query] [+ '#'+fragment],
      con '/' inicial garantizado.
    - URL ya relativa -> se devuelve con strip (sin cambios estructurales).
    - None o cadena vacía -> se devuelve igual.

    Spec route-templates-developer-portal.md — URL world-relative.
    """
    if not url:
        return url
    parts = urlsplit(url.strip())
    if parts.scheme or parts.netloc:
        path = parts.path or "/"
        if not path.startswith("/"):
            path = "/" + path
        rel = path
        if parts.query:
            rel += "?" + parts.query
        if parts.fragment:
            rel += "#" + parts.fragment
        return rel
    # Ruta ya relativa: garantizar la '/' inicial (p.ej. "village/statistics" → "/village/statistics")
    # para que pase la validación de url_pattern relativo del adaptador.
    rel = url.strip()
    if rel and not rel.startswith(("/", "#", "?")):
        rel = "/" + rel
    return rel
