"""
Excepciones del dominio del bot de Travian.
Toda excepción propia del core hereda de TravianBotError.

Cada subclase concreta declara:
  - error_code: str  — código SCREAMING_SNAKE_CASE para lookup en catálogo de mensajes
  - params: dict     — valores para interpolar en la plantilla del catálogo

El mensaje humano de str(err) se mantiene en español para compatibilidad
con los tests existentes (T-3 del spec i18n-backend).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.entities.tribe import Tribe


class TravianBotError(Exception):
    """Base de todas las excepciones del dominio."""

    error_code: str = "TRAVIAN_BOT_ERROR"
    params: dict = {}


class AccountNotFoundError(TravianBotError):
    error_code = "ACCOUNT_NOT_FOUND"

    def __init__(self, account_id: int) -> None:
        super().__init__(f"Cuenta {account_id} no encontrada")
        self.account_id = account_id
        self.params = {"account_id": account_id}


class DuplicateAccountError(TravianBotError):
    error_code = "DUPLICATE_ACCOUNT"

    def __init__(self, email: str) -> None:
        super().__init__(f"Ya existe una cuenta con el email '{email}'")
        self.email = email
        self.params = {"email": email}


class WorldNotFoundError(TravianBotError):
    error_code = "WORLD_NOT_FOUND"

    def __init__(self, world_id: int) -> None:
        super().__init__(f"Mundo {world_id} no encontrado")
        self.world_id = world_id
        self.params = {"world_id": world_id}


class SessionNotActiveError(TravianBotError):
    error_code = "SESSION_NOT_ACTIVE"

    def __init__(self) -> None:
        super().__init__("No hay sesión activa — ejecuta login primero")
        self.params = {}


class InvalidCredentialsError(TravianBotError):
    error_code = "INVALID_CREDENTIALS"

    def __init__(self, username: str) -> None:
        super().__init__(f"Credenciales incorrectas para '{username}'")
        self.username = username
        self.params = {"username": username}


class VillageNotFoundError(TravianBotError):
    error_code = "VILLAGE_NOT_FOUND"

    def __init__(self, village_id: int) -> None:
        super().__init__(f"Aldea {village_id} no encontrada")
        self.village_id = village_id
        self.params = {"village_id": village_id}


class FarmListNotFoundError(TravianBotError):
    error_code = "FARM_LIST_NOT_FOUND"

    def __init__(self, farm_list_id: int) -> None:
        super().__init__(f"Lista de vacas {farm_list_id} no encontrada")
        self.farm_list_id = farm_list_id
        self.params = {"farm_list_id": farm_list_id}


# Las siguientes se incluyen para completitud del dominio; se usarán en features posteriores:
class LoginError(TravianBotError):
    """Error genérico durante el proceso de login en Travian."""

    error_code = "LOGIN_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Error durante el proceso de login en Travian")
        self.params = {}


class BrowserError(TravianBotError):
    """Error en la capa de automatización del navegador."""

    error_code = "BROWSER_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Error en la capa de automatización del navegador")
        self.params = {}


class ElementNotClickableError(BrowserError):
    """
    El elemento del DOM no es clicable (rect inválido o fuera de pantalla).

    Usada por adapters/browser/driver.py en las funciones de click humano.
    Añadida en la feature human-click (2026-06-01).
    """

    error_code = "ELEMENT_NOT_CLICKABLE"

    def __init__(self, element_tag: str = "", reason: str = "") -> None:
        msg = f"Elemento no clicable: {element_tag}"
        if reason:
            msg += f" — {reason}"
        super().__init__(msg)
        self.element_tag = element_tag
        self.reason = reason
        self.params = {"element_tag": element_tag, "reason": reason}


class DatabaseError(TravianBotError):
    """Error al acceder a la base de datos local."""

    error_code = "DATABASE_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Error al acceder a la base de datos local")
        self.params = {}


# --- Nuevas excepciones añadidas en la feature i18n-backend ---

class TroopNotFoundError(TravianBotError):
    error_code = "TROOP_NOT_FOUND"

    def __init__(self, tribe: "Tribe", ordinal: int | None = None) -> None:
        super().__init__(f"Tropa {ordinal} de {tribe.value} no encontrada")
        self.tribe = tribe
        self.ordinal = ordinal
        self.params = {"tribe": tribe.value, "ordinal": str(ordinal or "")}


class BuildingNotFoundError(TravianBotError):
    error_code = "BUILDING_NOT_FOUND"

    def __init__(self, gid: int) -> None:
        super().__init__(f"Edificio gid={gid} no encontrado")
        self.gid = gid
        self.params = {"gid": gid}


# --- Excepciones añadidas en la feature lectura-overview-tronco-comun ---

class OverviewPageNotLoadedError(TravianBotError):
    """
    La página de overview de Travian no cargó en el timeout configurado.
    Se lanza desde LiveOverviewAdapter cuando wait_for(#content) expira o el
    HTML devuelto está vacío.
    """

    error_code = "OVERVIEW_PAGE_NOT_LOADED"

    def __init__(self, world_id: int = 0, page: object = None) -> None:
        page_name = page.value if hasattr(page, "value") else str(page)
        super().__init__(
            f"La página '{page_name}' de overview no cargó (world_id={world_id})"
        )
        self.world_id = world_id
        self.page = page
        self.params = {"world_id": str(world_id), "page": page_name}


class OverviewFixtureNotFoundError(TravianBotError):
    """
    No se encontró el fichero fixture HTML para la página solicitada.
    Se lanza desde FixtureOverviewAdapter cuando {page.value}.html no existe
    en el directorio de fixtures.
    """

    error_code = "OVERVIEW_FIXTURE_NOT_FOUND"

    def __init__(self, page: object = None) -> None:
        page_name = page.value if hasattr(page, "value") else str(page)
        super().__init__(
            f"Fixture no encontrado para la página '{page_name}' "
            f"(se esperaba el fichero '{page_name}.html')"
        )
        self.page = page
        self.params = {"page": page_name}


# --- Excepciones añadidas en la feature kirilloid-tropas-scraper ---

class DuplicateWorldError(TravianBotError):
    """Se lanza cuando se intenta registrar un mundo con (account_id, server) ya existente."""

    error_code = "DUPLICATE_WORLD"

    def __init__(self, server: str) -> None:
        super().__init__(f"Ya existe un mundo con server '{server}' en esta cuenta")
        self.server = server
        self.params = {"server": server}


class ActiveSessionConflictError(TravianBotError):
    """Se lanza al intentar borrar una cuenta/mundo con sesión activa en el bot."""

    error_code = "ACTIVE_SESSION_CONFLICT"

    def __init__(self, world_id: int) -> None:
        super().__init__(
            f"Hay una sesión activa para el mundo {world_id}. Haz logout primero."
        )
        self.world_id = world_id
        self.params = {"world_id": world_id}


class KirilloidScraperError(TravianBotError):
    """
    Error en el scraper de kirilloid.ru.
    Se lanza cuando una tribu/URL no carga en el timeout configurado,
    o cuando la estructura HTML de kirilloid ha cambiado de forma rompedora.

    Hereda de TravianBotError para integrarse con el handler global de la API
    y el sistema de logging del proyecto.
    """

    error_code = "KIRILLOID_SCRAPER_ERROR"

    def __init__(self, message: str = "", tribe: str = "", url: str = "") -> None:
        msg = message or f"Error en el scraper de kirilloid (tribu='{tribe}', url='{url}')"
        super().__init__(msg)
        self.tribe = tribe
        self.url = url
        self.params = {"tribe": tribe, "url": url}


# --- Excepciones añadidas en la feature login-sesion-api ---

class LoginFailedError(TravianBotError):
    """
    El login en Travian falló: credenciales incorrectas, error de red,
    o cualquier excepción interna de zendriver.
    El browser ya fue cerrado por login.py antes de llegar aquí.
    No se distingue entre "credenciales incorrectas" y "error de red" (RN-13):
    previene enumeración de información.
    """

    error_code = "LOGIN_FAILED"

    def __init__(self, username: str) -> None:
        super().__init__(f"Login fallido para '{username}'")
        self.username = username
        self.params = {"username": username}


# --- Excepción añadida en la feature human-sessions ---

class FernetDecryptionError(TravianBotError):
    """
    No se pudo descifrar la contraseña de una cuenta: la clave Fernet falta,
    está mal configurada o no coincide con la usada al cifrar.

    Es un error de CONFIGURACIÓN (no transitorio): el WorldAgent entra en
    estado DISCONNECTED-error y no reintenta con backoff (EC-HS15, RN-HS13).
    El usuario debe corregir TRAVIAN_BOT_SECRET_KEY y reiniciar.
    """

    error_code = "FERNET_DECRYPTION_ERROR"

    def __init__(self, account_id: int) -> None:
        super().__init__(
            f"No se pudo descifrar la contraseña de la cuenta {account_id}. "
            "Verifica TRAVIAN_BOT_SECRET_KEY."
        )
        self.account_id = account_id
        self.params = {"account_id": account_id}


# --- Excepciones añadidas en la feature farm-lists ---

class SchedulerNotFoundError(TravianBotError):
    """Scheduler de farm lists no encontrado."""

    error_code = "SCHEDULER_NOT_FOUND"

    def __init__(self, scheduler_id: int) -> None:
        super().__init__(f"Scheduler {scheduler_id} no encontrado")
        self.scheduler_id = scheduler_id
        self.params = {"scheduler_id": scheduler_id}


class FarmSlotNotFoundError(TravianBotError):
    """Slot de farm list no encontrado (clave compuesta id + farm_list_id)."""

    error_code = "FARM_SLOT_NOT_FOUND"

    def __init__(self, slot_id: int) -> None:
        super().__init__(f"Slot {slot_id} no encontrado")
        self.slot_id = slot_id
        self.params = {"slot_id": slot_id}


class FarmListSendError(TravianBotError):
    """Error al pulsar el botón Start de una farm list en Travian."""

    error_code = "FARM_LIST_SEND_ERROR"

    def __init__(self, farm_list_id: int, reason: str) -> None:
        super().__init__(f"Error enviando la lista {farm_list_id}: {reason}")
        self.farm_list_id = farm_list_id
        self.reason = reason
        self.params = {"farm_list_id": farm_list_id, "reason": reason}


class FarmListPageError(TravianBotError):
    """
    La página de farm lists no cargó o el Gold Club no está activo.
    Se lanza cuando navigate_to_farm_list no puede cargar la plaza de reuniones
    o cuando no hay listas en el DOM.
    """

    error_code = "FARM_LIST_PAGE_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.params = {"message": message}


class FarmListResponseError(TravianBotError):
    """
    El DOM devolvió datos incompletos o malformados para una farm list concreta.
    Se lanza cuando faltan campos obligatorios (id, name) en el objeto JS extraído.
    """

    error_code = "FARM_LIST_RESPONSE_ERROR"

    def __init__(self, index: int, message: str) -> None:
        super().__init__(f"Lista[{index}]: {message}")
        self.index = index
        self.params = {"index": index, "message": message}


# --- Excepciones añadidas en la feature noise-navigation ---

class BrowserBusyError(TravianBotError):
    """
    El lock de browser del WorldAgent no pudo adquirirse en el tiempo límite.

    Se lanza por execute_path_test cuando asyncio.wait_for(lock.acquire(), timeout)
    expira porque _execute_noise_action o refresh_villages ya tienen el lock.

    El handler HTTP lo convierte en HTTP 409 con detail legible.
    """

    error_code = "BROWSER_BUSY"

    def __init__(self, world_id: int = 0, timeout_s: int = 60) -> None:
        super().__init__(
            f"Browser del mundo {world_id} ocupado: no se adquirió el lock en {timeout_s}s"
        )
        self.world_id = world_id
        self.timeout_s = timeout_s
        self.params = {"world_id": world_id, "timeout_s": timeout_s}


class NoiseStepError(TravianBotError):
    """
    Un paso de la ruta de ruido de navegación falló.

    Se lanza por _execute_noise_step cuando el JS no encuentra el elemento,
    o cuando wait_for se agota. El WorldAgent captura esta excepción para
    incrementar el contador de fallos del destino y, si llega a 3,
    marcarlo como dead.

    action: tipo de NoiseAction que falló.
    selector: selector CSS del paso.
    reason: descripción legible del fallo.
    """

    error_code = "NOISE_STEP_ERROR"

    def __init__(self, action: str = "", selector: str = "", reason: str = "") -> None:
        msg = f"Paso de ruido fallido [{action}] selector='{selector}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.action = action
        self.selector = selector
        self.reason = reason
        self.params = {"action": action, "selector": selector, "reason": reason}


# --- Excepciones añadidas en la feature radar-ataques-entrantes ---

class IncomingAttackPageError(TravianBotError):
    """
    Error al cargar la página requerida por el radar de ataques entrantes
    (dorf1, rally point o ficha de atacante).

    Se lanza por IncomingAttackBrowserAdapter cuando la navegación falla
    o el DOM no responde en el timeout configurado.

    Ver spec docs/specs/radar-ataques-entrantes.md §7.
    Añadida en la feature radar-ataques-entrantes (2026-06-05).
    """

    error_code = "INCOMING_ATTACK_PAGE_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Error al cargar la página del radar de ataques")
        self.params = {"message": message}
