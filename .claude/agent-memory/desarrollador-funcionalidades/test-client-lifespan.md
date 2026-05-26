---
name: test-client-lifespan
description: TestClient de Starlette necesita context manager para disparar lifespan (startup/shutdown)
metadata:
  type: feedback
---

`TestClient(app)` sin context manager NO dispara el evento de startup/lifespan. Si `app.state` se inicializa en el lifespan (ej. `translation_port`), los tests fallarán con `AttributeError: 'State' object has no attribute 'translation_port'`.

**Correcto**:
```python
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
```

**Incorrecto**:
```python
client = TestClient(app)  # no dispara startup
```

**Why:** Starlette 1.1.0 / FastAPI 0.136 — el lifespan solo se ejecuta dentro del context manager `with`. Descubierto al implementar el singleton de traducciones en i18n-backend.

**How to apply:** Siempre usar `with TestClient(app)` en fixtures cuando el app usa lifespan para inicializar estado.
