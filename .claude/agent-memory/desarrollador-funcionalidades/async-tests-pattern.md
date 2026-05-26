---
name: async-tests-pattern
description: Convención de tests async del proyecto — asyncio.run() directo, NO @pytest.mark.asyncio
metadata:
  type: feedback
---

Tests async del proyecto usan `asyncio.run()` directamente en funciones síncronas, NO `@pytest.mark.asyncio`.

**Why:** El proyecto usa pytest-asyncio en modo STRICT. Los fixtures async requieren `@pytest_asyncio.fixture` (no `@pytest.fixture`). La convención establecida en el proyecto (test_login_use_case.py, test_logout_use_case.py) es evitar el decorador y llamar a `asyncio.run()` directamente.

**How to apply:** Para tests que necesiten awaitar código async:
```python
def test_algo():
    result = asyncio.run(mi_funcion_async())
    assert result == esperado
```

Para fixtures que creen recursos async (p.ej. conexiones SQLite en memoria):
```python
def _make_adapter():
    async def _create():
        conn = await aiosqlite.connect(":memory:")
        adapter = MiAdapter(conn)
        await adapter.setup()
        return adapter, conn
    return asyncio.run(_create())
```

Nota: no usar `asyncio.get_event_loop().run_until_complete()` — está deprecado en Python 3.14.

Relacionado con: [[test-client-lifespan]]
