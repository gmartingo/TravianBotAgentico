"""
Punto de entrada principal del bot de Travian.
Orquesta el arranque de la API y el motor de tareas.
"""
import os
import sys

# Si no estamos en el .venv del proyecto, relanzamos con el Python correcto.
_venv_python = os.path.join(
    os.path.dirname(__file__), ".venv",
    "Scripts" if sys.platform == "win32" else "bin",
    "python.exe" if sys.platform == "win32" else "python",
)
if os.path.exists(_venv_python) and os.path.abspath(sys.executable) != os.path.abspath(_venv_python):
    import subprocess
    sys.exit(subprocess.call([os.path.abspath(_venv_python)] + sys.argv))

import uvicorn
from adapters.api.main import app


def main() -> None:
    uvicorn.run(
        "adapters.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
