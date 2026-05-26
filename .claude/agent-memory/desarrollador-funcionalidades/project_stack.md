---
name: project-stack
description: Stack técnico del proyecto TravianBot — versiones exactas, comando de tests y convenciones clave
metadata:
  type: project
---

Stack verificado en producción (2026-05-24):
- Python 3.14.4 en .venv
- FastAPI 0.136.3 + Starlette 1.1.0 + Pydantic 2.13.4
- pytest 9.0.3
- httpx 0.28.1 (cliente de test)

Comando para ejecutar tests (excluye tests de antidetección que requieren Chrome real):
```
.venv/bin/pytest tests/ --ignore=tests/antideteccion -v
```

**Why:** Los tests de antideteccion/ requieren Chrome instalado y no se pueden correr en CI sin browser. El resto de tests no necesitan browser.

**How to apply:** Siempre usar este comando para verificar que no hay regresiones. No correr tests/antideteccion/ sin Chrome disponible.

Relaciones con [[fastapi-conventions]] y [[test-client-lifespan]].
