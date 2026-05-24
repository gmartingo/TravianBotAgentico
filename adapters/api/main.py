"""
Punto de entrada de la API FastAPI.
Registra routers y configura la aplicación.
"""
from fastapi import FastAPI

app = FastAPI(
    title="TravianBot API",
    description="API de control del bot de Travian. Requiere Accept-Language en cada endpoint.",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict:
    """Endpoint de salud — no requiere Accept-Language."""
    return {"status": "ok"}
