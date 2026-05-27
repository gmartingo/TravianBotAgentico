"""
Utilidades de construcción de URLs para los adaptadores de browser.
"""


def build_url(base: str, path: str) -> str:
    """
    Construye una URL sin dobles barras independientemente de si `base` tiene
    trailing slash o `path` tiene leading slash.

    Ejemplos:
      build_url("https://ts20.x2.america.travian.com/", "/dorf1.php?newdid=1")
      → "https://ts20.x2.america.travian.com/dorf1.php?newdid=1"

      build_url("https://ts20.x2.america.travian.com", "dorf1.php?newdid=1")
      → "https://ts20.x2.america.travian.com/dorf1.php?newdid=1"
    """
    return base.rstrip("/") + "/" + path.lstrip("/")
