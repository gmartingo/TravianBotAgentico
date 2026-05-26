"""
Utilidades compartidas entre scrapers de kirilloid.

Funciones puras (sin dependencias de browser) que reutilizan ambos scrapers:
  - _color_distance     — distancia euclidiana RGBA para flood-fill
  - _remove_background  — elimina fondo de iconos con Pillow
  - _wait_for_element   — espera activa de selector CSS en página zendriver

Estos helpers se extrajeron de kirilloid_scraper.py para evitar acoplamiento
cruzado: kirilloid_buildings_scraper.py los importa desde aquí en lugar de
importar desde el módulo de tropas.
"""
from __future__ import annotations

from collections import Counter

from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# Eliminación de fondo con Pillow (sin browser — testable)
# ---------------------------------------------------------------------------


def _color_distance(c1: tuple, c2: tuple) -> float:
    """Distancia euclidiana entre dos colores RGBA (ignora canal alpha)."""
    return sum((a - b) ** 2 for a, b in zip(c1[:3], c2[:3])) ** 0.5


def _remove_background(img: Image.Image, tolerance: int = 30) -> Image.Image:
    """
    Elimina el fondo de un icono usando flood-fill desde las 4 esquinas.

    Estrategia:
    1. Lee el color de las 4 esquinas.
    2. El color de fondo es el más frecuente entre las 4 esquinas.
    3. Si las 4 esquinas tienen colores completamente distintos (len(set) == 4),
       no hay fondo uniforme detectable → devuelve la imagen sin cambios (EC-B-10).
    4. Para cada esquina cuyo color esté dentro de la tolerancia del color de fondo,
       aplica ImageDraw.floodfill con fill=(0,0,0,0) para hacerlo transparente.

    La imagen debe estar en modo RGBA antes de llamar a esta función.
    """
    img = img.convert("RGBA")
    corners = [
        img.getpixel((0, 0)),
        img.getpixel((img.width - 1, 0)),
        img.getpixel((0, img.height - 1)),
        img.getpixel((img.width - 1, img.height - 1)),
    ]
    corner_rgb = [c[:3] for c in corners]
    counts = Counter(corner_rgb)
    bg_color = counts.most_common(1)[0][0]

    # Si todas las esquinas son distintas → no hay fondo uniforme → devolver sin cambios
    if len(counts) == 4:
        return img

    fill_coords = [
        (0, 0),
        (img.width - 1, 0),
        (0, img.height - 1),
        (img.width - 1, img.height - 1),
    ]
    for (x, y) in fill_coords:
        corner_color = img.getpixel((x, y))[:3]
        if _color_distance(corner_color, bg_color) <= tolerance:
            ImageDraw.floodfill(img, (x, y), (0, 0, 0, 0), thresh=tolerance)

    return img


# ---------------------------------------------------------------------------
# Espera activa de elemento DOM (requiere browser — no testable sin Chrome)
# ---------------------------------------------------------------------------


async def _wait_for_element(page, selector: str, timeout: int = 30) -> None:
    """
    Espera a que un elemento sea visible en la página.
    Lanza KirilloidScraperError si el timeout expira.

    Nota: las importaciones de asyncio y exceptions se hacen en runtime
    para no requerir zendriver en los tests unitarios.
    """
    from core.exceptions import KirilloidScraperError
    import asyncio

    elapsed = 0.0
    interval = 0.5
    while elapsed < timeout:
        try:
            el = await page.query_selector(selector)
            if el is not None:
                return
        except Exception:
            pass
        await asyncio.sleep(interval)
        elapsed += interval
    raise KirilloidScraperError(
        message=f"Timeout esperando selector '{selector}' ({timeout}s)",
    )
