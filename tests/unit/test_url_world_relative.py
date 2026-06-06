"""
Tests del normalizador URL world-relative (catálogo de rutas global).

El dev pega la URL completa del mundo (https://ts20.x2.america.travian.com/...);
la plantilla GLOBAL debe almacenar solo la parte relativa para que el mundo se
anteponga al asignar la ruta. Ver route_template_service.to_world_relative_url.
"""
import pytest

from core.use_cases.route_template_service import to_world_relative_url


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("https://ts20.x2.america.travian.com/dorf1.php", "/dorf1.php"),
        ("https://ts20.x2.america.travian.com/karte.php?x=1&y=-2", "/karte.php?x=1&y=-2"),
        ("https://ts20.x2.america.travian.com/", "/"),
        ("https://ts20.x2.america.travian.com/spieler.php?uid=5#tab", "/spieler.php?uid=5#tab"),
        ("http://ts5.travian.es/statistics", "/statistics"),
        ("/dorf2.php", "/dorf2.php"),            # ya relativa
        ("/build.php?gid=16&tt=99", "/build.php?gid=16&tt=99"),
        ("", ""),
        (None, None),
    ],
)
def test_to_world_relative_url(entrada, esperado):
    assert to_world_relative_url(entrada) == esperado


def test_strip_no_deja_dominio_de_mundo_cableado():
    """La plantilla nunca debe quedar con un mundo concreto en la URL."""
    rel = to_world_relative_url("https://ts20.x2.america.travian.com/dorf1.php")
    assert "://" not in rel
    assert "travian.com" not in rel
    assert rel.startswith("/")
