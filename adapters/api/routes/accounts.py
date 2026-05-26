"""
Router FastAPI para la gestión de cuentas y mundos.

8 endpoints REST:
  POST   /accounts                          → 201 + AccountResponse + Location
  GET    /accounts                          → 200 + AccountListResponse
  GET    /accounts/{id}                     → 200 + AccountResponse
  PUT    /accounts/{id}                     → 200 + AccountResponse
  DELETE /accounts/{id}                     → 204
  POST   /accounts/{id}/worlds              → 201 + WorldResponse + Location
  GET    /accounts/{id}/worlds              → 200 + WorldListResponse
  DELETE /accounts/{id}/worlds/{world_id}  → 204

Convenciones:
  - Sin prefijo /api (el proxy de Vite lo retira).
  - Sin Accept-Language: devuelven datos operativos, no catálogo localizado.
  - La contraseña NUNCA se serializa en ninguna respuesta (write-only).
  - Toda validación de entrada es via Pydantic → 422 automático de FastAPI.
  - Sin lógica de negocio en las rutas: validan, llaman use case, serializan.
  - Cabeceras de seguridad añadidas por el middleware global de main.py.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import AnyHttpUrl, BaseModel, Field
from pydantic import EmailStr

from adapters.api.dependencies import get_db_port, get_fernet, get_world_runtime_port
from core.entities.tribe import Tribe
from core.exceptions import AccountNotFoundError, LoginFailedError, WorldNotFoundError
from core.ports.db_port import DbPort
from core.use_cases.account_use_cases import (
    CreateAccountUseCase,
    DeleteAccountUseCase,
    UpdateAccountUseCase,
)
from core.use_cases.login_use_case import LoginUseCase, LogoutUseCase
from core.use_cases.world_use_cases import AddWorldUseCase, DeleteWorldUseCase

router = APIRouter(tags=["accounts"])


# ---------------------------------------------------------------------------
# PlayableTribe — enum Pydantic de solo las 7 tribus jugables
# Usada en AddWorldRequest para que FastAPI valide y devuelva 422 si llega
# "nature" o "natars" (RT-06 del spec: solo en la capa API, no en el core).
# ---------------------------------------------------------------------------

class PlayableTribe(str, Enum):
    ROMANS    = "romans"
    TEUTONS   = "teutons"
    GAULS     = "gauls"
    EGYPTIANS = "egyptians"
    HUNS      = "huns"
    SPARTANS  = "spartans"
    VIKINGS   = "vikings"


# ---------------------------------------------------------------------------
# Schemas de request
# ---------------------------------------------------------------------------

class CreateAccountRequest(BaseModel):
    email:    EmailStr
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class UpdateAccountRequest(BaseModel):
    email:    EmailStr
    username: str = Field(..., min_length=1, max_length=100)
    password: Optional[str] = Field(default=None, min_length=1, max_length=200)
    # Si password=None → conservar el cifrado existente (RN-11)


class AddWorldRequest(BaseModel):
    server: AnyHttpUrl  # protocolo http/https obligatorio (AnyHttpUrl); max 500 chars
    tribe:  PlayableTribe


# ---------------------------------------------------------------------------
# Schemas de response
# ---------------------------------------------------------------------------

class WorldResponse(BaseModel):
    id:         int
    server:     str
    tribe:      str
    created_at: str

    model_config = {"from_attributes": True}


class AccountResponse(BaseModel):
    id:         int
    email:      str
    username:   str
    # password: AUSENTE — write-only, nunca se serializa
    worlds:     list[WorldResponse] = []
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class AccountListResponse(BaseModel):
    accounts: list[AccountResponse]


class WorldListResponse(BaseModel):
    worlds: list[WorldResponse]


class SessionStatusResponse(BaseModel):
    active: bool
    world_id: int
    account_id: int


# ---------------------------------------------------------------------------
# Helpers de serialización
# ---------------------------------------------------------------------------

async def _get_world_created_at(db: DbPort, world_id: int) -> str:
    """Obtiene el created_at de un mundo directamente de la BD."""
    # Acceso directo a la conexión — el adaptador lo tiene en _conn
    if hasattr(db, "_conn"):
        cursor = await db._conn.execute(
            "SELECT created_at FROM worlds WHERE id = ?", (world_id,)
        )
        row = await cursor.fetchone()
        return row["created_at"] if row else ""
    return ""


async def _get_account_timestamps(db: DbPort, account_id: int) -> tuple[str, str]:
    """Obtiene (created_at, updated_at) de una cuenta directamente de la BD."""
    if hasattr(db, "_conn"):
        cursor = await db._conn.execute(
            "SELECT created_at, updated_at FROM accounts WHERE id = ?", (account_id,)
        )
        row = await cursor.fetchone()
        if row:
            return row["created_at"], row["updated_at"]
    return ("", "")


async def _account_to_response(account, db: DbPort) -> AccountResponse:
    """Construye AccountResponse incluyendo los timestamps desde la BD."""
    created_at, updated_at = await _get_account_timestamps(db, account.id)
    worlds = []
    for w in account.worlds:
        w_created_at = await _get_world_created_at(db, w.id)
        worlds.append(WorldResponse(
            id=w.id,
            server=w.server,
            tribe=w.tribe.value,
            created_at=w_created_at,
        ))
    return AccountResponse(
        id=account.id,
        email=account.email,
        username=account.username,
        worlds=worlds,
        created_at=created_at,
        updated_at=updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints de cuentas
# ---------------------------------------------------------------------------

@router.post(
    "/accounts",
    status_code=status.HTTP_201_CREATED,
    response_model=AccountResponse,
    summary="Crear cuenta",
    description=(
        "Registra una nueva cuenta de Travian. "
        "La contraseña se cifra con Fernet antes de persistir y nunca se devuelve."
    ),
)
async def create_account(
    body: CreateAccountRequest,
    response: Response,
    request: Request,
    db: DbPort = Depends(get_db_port),
    fernet=Depends(get_fernet),
) -> AccountResponse:
    use_case = CreateAccountUseCase(db=db, fernet=fernet)
    account = await use_case.execute(
        email=str(body.email),
        username=body.username,
        password_plain=body.password,
    )
    response.headers["Location"] = f"/accounts/{account.id}"
    return await _account_to_response(account, db)


@router.get(
    "/accounts",
    status_code=status.HTTP_200_OK,
    response_model=AccountListResponse,
    summary="Listar cuentas",
    description="Devuelve todas las cuentas registradas con sus mundos.",
)
async def list_accounts(
    db: DbPort = Depends(get_db_port),
) -> AccountListResponse:
    accounts = await db.list_accounts()
    account_responses = []
    for acc in accounts:
        account_responses.append(await _account_to_response(acc, db))
    return AccountListResponse(accounts=account_responses)


@router.get(
    "/accounts/{account_id}",
    status_code=status.HTTP_200_OK,
    response_model=AccountResponse,
    summary="Obtener cuenta por ID",
)
async def get_account(
    account_id: int,
    db: DbPort = Depends(get_db_port),
) -> AccountResponse:
    from core.exceptions import AccountNotFoundError
    account = await db.get_account(account_id)
    if account is None:
        raise AccountNotFoundError(account_id)
    return await _account_to_response(account, db)


@router.put(
    "/accounts/{account_id}",
    status_code=status.HTTP_200_OK,
    response_model=AccountResponse,
    summary="Actualizar cuenta",
    description=(
        "Reemplaza los campos editables de una cuenta. "
        "Si 'password' se omite, la contraseña almacenada no cambia."
    ),
)
async def update_account(
    account_id: int,
    body: UpdateAccountRequest,
    db: DbPort = Depends(get_db_port),
    fernet=Depends(get_fernet),
) -> AccountResponse:
    use_case = UpdateAccountUseCase(db=db, fernet=fernet)
    account = await use_case.execute(
        account_id=account_id,
        email=str(body.email),
        username=body.username,
        password_plain=body.password,
    )
    return await _account_to_response(account, db)


@router.delete(
    "/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar cuenta",
    description=(
        "Elimina una cuenta y todos sus mundos y aldeas en cascada. "
        "Devuelve 409 si algún mundo tiene sesión activa en el bot."
    ),
)
async def delete_account(
    account_id: int,
    request: Request,
    db: DbPort = Depends(get_db_port),
) -> None:
    runtime_port = getattr(request.app.state, "world_runtime_port", None)
    use_case = DeleteAccountUseCase(db=db, runtime_port=runtime_port)
    await use_case.execute(account_id)


# ---------------------------------------------------------------------------
# Endpoints de mundos
# ---------------------------------------------------------------------------

@router.post(
    "/accounts/{account_id}/worlds",
    status_code=status.HTTP_201_CREATED,
    response_model=WorldResponse,
    summary="Añadir mundo a una cuenta",
    description=(
        "Registra un mundo (servidor Travian) bajo una cuenta existente. "
        "NATURE y NATARS son tribus NPC — devuelven 422."
    ),
)
async def add_world(
    account_id: int,
    body: AddWorldRequest,
    response: Response,
    db: DbPort = Depends(get_db_port),
) -> WorldResponse:
    # Convertir PlayableTribe (str Enum Pydantic) a Tribe del core
    tribe = Tribe(body.tribe.value)
    server_raw = str(body.server)
    use_case = AddWorldUseCase(db=db)
    world = await use_case.execute(account_id=account_id, server_raw=server_raw, tribe=tribe)
    response.headers["Location"] = f"/accounts/{account_id}/worlds/{world.id}"
    created_at = await _get_world_created_at(db, world.id)
    return WorldResponse(
        id=world.id,
        server=world.server,
        tribe=world.tribe.value,
        created_at=created_at,
    )


@router.get(
    "/accounts/{account_id}/worlds",
    status_code=status.HTTP_200_OK,
    response_model=WorldListResponse,
    summary="Listar mundos de una cuenta",
)
async def list_worlds(
    account_id: int,
    db: DbPort = Depends(get_db_port),
) -> WorldListResponse:
    from core.exceptions import AccountNotFoundError
    account = await db.get_account(account_id)
    if account is None:
        raise AccountNotFoundError(account_id)
    worlds_data = await db.list_worlds(account_id)
    world_responses = []
    for w in worlds_data:
        w_created_at = await _get_world_created_at(db, w.id)
        world_responses.append(WorldResponse(
            id=w.id,
            server=w.server,
            tribe=w.tribe.value,
            created_at=w_created_at,
        ))
    return WorldListResponse(worlds=world_responses)


@router.delete(
    "/accounts/{account_id}/worlds/{world_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar mundo",
    description="Elimina un mundo y sus aldeas en cascada. Devuelve 409 si hay sesión activa.",
)
async def delete_world(
    account_id: int,
    world_id: int,
    request: Request,
    db: DbPort = Depends(get_db_port),
) -> None:
    runtime_port = getattr(request.app.state, "world_runtime_port", None)
    use_case = DeleteWorldUseCase(db=db, runtime_port=runtime_port)
    await use_case.execute(account_id=account_id, world_id=world_id)


# ---------------------------------------------------------------------------
# Helper de validación de pertenencia — reutilizado por los 3 endpoints de sesión
# ---------------------------------------------------------------------------

async def _verify_world_belongs_to_account(
    account_id: int,
    world_id: int,
    db,
) -> None:
    """
    Verifica que account_id existe y que world_id pertenece a esa cuenta.

    Lanza AccountNotFoundError si la cuenta no existe.
    Lanza WorldNotFoundError si world_id no existe o no pertenece a account_id.

    El 404 homogéneo para world_id ajeno es intencional (RN-04): no se revela
    que el mundo existe en otra cuenta (consistente con EC-12 del spec
    registro-cuentas-mundos).
    """
    account = await db.get_account(account_id)
    if account is None:
        raise AccountNotFoundError(account_id)
    world_ids = {w.id for w in account.worlds}
    if world_id not in world_ids:
        raise WorldNotFoundError(world_id)


# ---------------------------------------------------------------------------
# Endpoints de sesión
# ---------------------------------------------------------------------------

@router.post(
    "/accounts/{account_id}/worlds/{world_id}/session",
    status_code=status.HTTP_200_OK,
    response_model=SessionStatusResponse,
    summary="Abrir sesión (login)",
    description=(
        "Abre una sesión autenticada en Travian para la cuenta y mundo indicados. "
        "Operación síncrona: puede tardar hasta 10 segundos (delays anti-detección). "
        "Si ya existe una sesión activa, la cierra antes de abrir una nueva. "
        "Devuelve 401 si el login falla (credenciales incorrectas o error de red)."
    ),
)
async def session_login(
    account_id: int,
    world_id: int,
    db=Depends(get_db_port),
    registry=Depends(get_world_runtime_port),
    fernet=Depends(get_fernet),
) -> SessionStatusResponse:
    await _verify_world_belongs_to_account(account_id, world_id, db)
    use_case = LoginUseCase(registry=registry, db=db, fernet=fernet)
    success = await use_case.execute(account_id, world_id)
    if not success:
        # Obtener username para el mensaje de error (la cuenta existe: ya la verificamos)
        account = await db.get_account(account_id)
        raise LoginFailedError(account.username if account else str(account_id))
    return SessionStatusResponse(active=True, world_id=world_id, account_id=account_id)


@router.delete(
    "/accounts/{account_id}/worlds/{world_id}/session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión (logout)",
    description=(
        "Cierra la sesión activa del bot para el mundo indicado. "
        "Idempotente: devuelve 204 aunque no haya sesión activa."
    ),
)
async def session_logout(
    account_id: int,
    world_id: int,
    db=Depends(get_db_port),
    registry=Depends(get_world_runtime_port),
) -> None:
    await _verify_world_belongs_to_account(account_id, world_id, db)
    use_case = LogoutUseCase(registry=registry)
    await use_case.execute(world_id)


@router.get(
    "/accounts/{account_id}/worlds/{world_id}/session",
    status_code=status.HTTP_200_OK,
    response_model=SessionStatusResponse,
    summary="Estado de sesión",
    description=(
        "Devuelve si hay una sesión activa del bot para el mundo indicado. "
        "No requiere sesión activa para funcionar."
    ),
)
async def session_status(
    account_id: int,
    world_id: int,
    db=Depends(get_db_port),
    registry=Depends(get_world_runtime_port),
) -> SessionStatusResponse:
    await _verify_world_belongs_to_account(account_id, world_id, db)
    active = registry.is_active(world_id)
    return SessionStatusResponse(active=active, world_id=world_id, account_id=account_id)
