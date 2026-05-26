"""
Entidad Account — representa una cuenta de Travian gestionada por el bot.
Solo contiene credenciales y la lista de mundos en los que participa.

Campos:
  id       — asignado por la BD (None antes de persistir).
  email    — identificador único del lobby de Travian (normalizado a lower+strip).
  username — nombre visible libre, no necesita ser único.
  password — en memoria siempre str (descifrado); el adaptador SQLite recibe la
             contraseña ya cifrada al persistir (save_account/update_account) y
             devuelve password="" al cargar (get_account/get_account_by_email/
             list_accounts). El descifrado ocurre exclusivamente en LoginUseCase,
             que obtiene el token cifrado via get_account_password_cipher() y lo
             descifra con el objeto Fernet inyectado.
             El campo se excluye del repr() de la dataclass (field repr=False)
             para que la contraseña en claro nunca aparezca en logs de trazas.
  worlds   — mundos registrados bajo esta cuenta.
"""
from dataclasses import dataclass, field
from typing import Optional

from core.entities.world import World


@dataclass
class Account:
    id: Optional[int]
    email: str
    username: str
    password: str = field(repr=False)   # en memoria siempre str; "" cuando viene de get_account (sin descifrar)
    worlds: list[World] = field(default_factory=list)

    @staticmethod
    def normalize_email(email: str) -> str:
        """Normalización canónica del email: sin espacios y en minúsculas.

        Fuente ÚNICA de verdad. Los use cases la reutilizan para que la búsqueda
        de unicidad use exactamente el mismo valor que se persiste, evitando
        normalizar el email en varios sitios (riesgo de desincronización).
        """
        return email.strip().lower()

    def __post_init__(self) -> None:
        self.email = self.normalize_email(self.email)
        if not self.email:
            raise ValueError("El email no puede estar vacío.")
        if not self.username:
            raise ValueError("El nombre de usuario no puede estar vacío.")
