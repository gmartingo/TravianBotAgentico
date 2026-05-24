"""
Tests unitarios de LogoutUseCase.
No abren Chrome ni BD. Mockean WorldRuntimePort.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from core.use_cases.login_use_case import LogoutUseCase


def _make_logout_use_case():
    registry = MagicMock()
    registry.logout = AsyncMock(return_value=None)
    return LogoutUseCase(registry=registry), registry


# ---------------------------------------------------------------------------
# Caso: logout llama al registry con el world_id correcto
# ---------------------------------------------------------------------------

def test_logout_calls_registry_con_world_id():
    """registry.logout debe ser invocado exactamente una vez con el world_id correcto."""
    use_case, registry = _make_logout_use_case()

    asyncio.run(use_case.execute(world_id=5))

    registry.logout.assert_called_once_with(5)


# ---------------------------------------------------------------------------
# Caso: logout es idempotente (registry no lanza si no hay sesión)
# ---------------------------------------------------------------------------

def test_logout_idempotente_no_lanza_si_no_hay_sesion():
    """
    registry.logout no lanza excepción si no hay sesión activa.
    LogoutUseCase no debe propagar ninguna excepción en ese caso.
    """
    use_case, registry = _make_logout_use_case()
    # El registry ya retorna None por defecto en el mock — simula el caso idempotente

    # No debe lanzar ninguna excepción
    asyncio.run(use_case.execute(world_id=999))

    registry.logout.assert_called_once_with(999)


# ---------------------------------------------------------------------------
# Caso: logout con world_id = 0 (valor de borde)
# ---------------------------------------------------------------------------

def test_logout_acepta_world_id_cero():
    use_case, registry = _make_logout_use_case()
    asyncio.run(use_case.execute(world_id=0))
    registry.logout.assert_called_once_with(0)
