"""
Configuración global de pytest.

Fija una clave Fernet de test en el entorno ANTES de que cualquier test importe
la app FastAPI. El lifespan de `adapters/api/main.py` llama a `load_fernet_key()`,
que lanza RuntimeError si `TRAVIAN_BOT_SECRET_KEY` no está definida (RN-04). Sin
esta clave de test, todos los tests que arrancan la app (catalog, game_data,
health, cuentas) fallarían en el startup.

Se usa `setdefault`: si el desarrollador ya exporta una clave real en su entorno,
se respeta; en CI / local sin clave, se genera una efímera para la sesión de tests.
"""
import os

from cryptography.fernet import Fernet

# Generada en tiempo de import del conftest → disponible antes de importar la app.
os.environ.setdefault("TRAVIAN_BOT_SECRET_KEY", Fernet.generate_key().decode())
