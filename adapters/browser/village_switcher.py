"""
Parser del village-switcher del sidebar de Travian.

Lee la lista de aldeas propias desde el DOM de la página activa (sin navegación
extra) y devuelve entidades Village para persistir en la tabla villages.

CONTRATO ANTI-DETECCIÓN (spec noise-path-wizard.md §9.3 + §11):
  - SOLO lectura: ningún click, ningún scroll, ninguna navegación extra.
  - Usa tab.evaluate() con una función JS pura; no dispara eventos DOM.
  - No genera peticiones de red adicionales al servidor de Travian.
  - Tiempo de ejecución: < 50 ms (solo procesamiento JS en DOM ya cargado).
  - Se ejecuta como máximo 1 vez por login (no es un poller continuo).

SELECTORES (verificados en el DOM real de Travian — farm_lists.py:146):
  - 'span.name[data-did]': cada aldea propia tiene un <span class="name"
    data-did="<newdid>" ...> en el sidebar del village-switcher. El atributo
    data-did es el identificador numérico de la aldea (= newdid en las URLs
    de Travian = data_id en la tabla villages).
  - El texto del span.name contiene el nombre de la aldea.
  - Las coordenadas se leen desde los atributos data-x / data-y del li padre
    del span, o del mismo span si los tiene. Si no están disponibles, se usan 0.

GATE GUARDIAN-ANTIDETECCION:
  - Este módulo toca el DOM de Travian. Antes de commitear, el guardian debe
    verificar: (1) selectores correctos y estables en Travian T4,
    (2) que evaluate() con función pura no dispara eventos observables,
    (3) que las coordenadas (x,y) se extraen correctamente.

Spec noise-path-wizard.md §7.7, §9.3, §11, RN-NP03.
"""
from __future__ import annotations

import logging

from core.entities.village import Village

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JS puro para extraer las aldeas del village-switcher
# ---------------------------------------------------------------------------
#
# Selector verificado en el DOM real de Travian (farm_lists.py línea 146):
#   document.querySelectorAll('span.name[data-did]')
#
# Cada span.name[data-did] representa una aldea propia en el sidebar.
# Su atributo data-did es el newdid (= data_id en BD).
# El elemento padre (li) puede tener data-x / data-y con las coordenadas.
# Si el li no las tiene, quedan en 0 (no son críticas para el funcionamiento
# básico del village-switcher; se pueden rellenar en una versión futura).

_JS_EXTRACT_VILLAGES = """
(function() {
    var spans = document.querySelectorAll('span.name[data-did]');
    if (!spans || !spans.length) return null;
    var result = [];
    for (var i = 0; i < spans.length; i++) {
        var span = spans[i];
        var did = parseInt(span.getAttribute('data-did'), 10);
        if (!did || did <= 0) continue;
        var name = (span.textContent || span.innerText || '').trim();
        if (!name) continue;
        // Leer coordenadas del li padre (o del span si las tiene directamente)
        var li = span.closest('li') || span.parentElement;
        var x = 0, y = 0;
        if (li) {
            var rawX = li.getAttribute('data-x');
            var rawY = li.getAttribute('data-y');
            if (rawX !== null) x = parseInt(rawX, 10) || 0;
            if (rawY !== null) y = parseInt(rawY, 10) || 0;
        }
        result.push({data_id: did, name: name, x: x, y: y});
    }
    return result.length > 0 ? result : null;
})()
"""


async def parse_village_switcher(tab, world_id: int) -> list[Village]:
    """
    Lee el village-switcher del sidebar de Travian y devuelve las aldeas propias.

    Parámetros:
        tab:       Tab activo de zendriver (la página donde está el bot ahora mismo).
        world_id:  ID del mundo en la BD (necesario para construir las entidades Village).

    Devuelve:
        Lista de Village con data_id, name, x, y rellenados.
        Lista vacía si el selector no se encuentra en el DOM (sin lanzar excepción).

    Contrato anti-detección:
        - SOLO tab.evaluate() — sin clicks ni navegación.
        - La función JS es pura (sin efectos secundarios observables).
        - En caso de fallo parcial: loguea y devuelve lista vacía.

    Spec noise-path-wizard.md §7.7, §9.3, CA-NP26, CA-NP27, CA-NP28.
    """
    try:
        result = await tab.evaluate(_JS_EXTRACT_VILLAGES)
    except Exception as exc:
        logger.warning(
            "parse_village_switcher: error evaluando JS en el DOM: %s", exc
        )
        return []

    if result is None:
        # El selector no encontró elementos — página sin sidebar (raro) o
        # selectores desactualizados (Travian actualizó el HTML).
        logger.warning(
            "parse_village_switcher: selector 'span.name[data-did]' no encontró "
            "elementos en el DOM actual. ¿El bot está en una página de Travian "
            "con el sidebar de aldeas? ¿Los selectores siguen siendo válidos?"
        )
        return []

    villages: list[Village] = []
    for item in result:
        try:
            village = Village(
                id=0,          # BD asignará el id real en el UPSERT
                world_id=world_id,
                data_id=int(item["data_id"]),
                name=str(item["name"]),
                x=int(item.get("x", 0) or 0),
                y=int(item.get("y", 0) or 0),
            )
            villages.append(village)
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning(
                "parse_village_switcher: error parseando item %r: %s", item, exc
            )
            continue

    logger.info(
        "parse_village_switcher: encontradas %d aldeas para mundo %d",
        len(villages), world_id,
    )
    return villages
