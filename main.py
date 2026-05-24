"""
Punto de entrada principal del bot de Travian.
Orquesta el arranque de la API y el motor de tareas.
"""
import asyncio
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
