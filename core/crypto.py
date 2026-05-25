"""
Módulo de cifrado de contraseñas — Fernet (AES-128-CBC + HMAC-SHA256).

Reglas de seguridad:
  - La clave Fernet vive en la variable de entorno TRAVIAN_BOT_SECRET_KEY.
  - Si la variable no está configurada al arrancar, load_fernet_key() lanza
    RuntimeError con mensaje claro. La app NO arranca en ese caso.
  - La clave NUNCA se expone fuera de este módulo: encrypt/decrypt reciben
    el objeto Fernet ya inicializado, no la clave en bruto.
  - La contraseña NUNCA se registra en logs (el middleware _mask_frame_locals
    en main.py enmascara variables con nombre "password").

Uso desde el lifespan:
    from core.crypto import load_fernet_key
    fernet = load_fernet_key()                   # falla si falta la variable
    app.state.fernet = fernet

Uso desde use cases:
    from core.crypto import encrypt_password, decrypt_password
    cifrada: bytes = encrypt_password(fernet, password_plain)
    plana:   str   = decrypt_password(fernet, cifrada)
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet


def load_fernet_key() -> Fernet:
    """
    Lee TRAVIAN_BOT_SECRET_KEY del entorno y devuelve un objeto Fernet listo.

    La clave debe ser una cadena base64url generada por Fernet.generate_key()
    (44 caracteres base64). Si no está configurada, la aplicación no puede
    cifrar/descifrar contraseñas y debe fallar de forma explícita.

    Raises:
        RuntimeError: si TRAVIAN_BOT_SECRET_KEY no está en el entorno.
        ValueError:   si el valor no es una clave Fernet válida.
    """
    key_b64 = os.environ.get("TRAVIAN_BOT_SECRET_KEY")
    if key_b64 is None:
        raise RuntimeError(
            "TRAVIAN_BOT_SECRET_KEY no está configurada. "
            "Genera una clave con: python3 -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\" "
            "y expórtala antes de arrancar la API: "
            "export TRAVIAN_BOT_SECRET_KEY=<clave>"
        )
    # Fernet lanza ValueError si el valor no es una clave válida (longitud/base64).
    return Fernet(key_b64.encode())


def encrypt_password(fernet: Fernet, plaintext: str) -> bytes:
    """
    Cifra una contraseña en texto claro y devuelve el token Fernet (bytes).

    El token incluye IV aleatorio y HMAC, por lo que cada llamada produce
    un resultado diferente para la misma contraseña (no determinístico).
    """
    return fernet.encrypt(plaintext.encode("utf-8"))


def decrypt_password(fernet: Fernet, token: bytes) -> str:
    """
    Descifra un token Fernet y devuelve la contraseña en texto claro.

    Raises:
        cryptography.fernet.InvalidToken: si el token está corrupto o
        fue cifrado con una clave diferente.
    """
    return fernet.decrypt(token).decode("utf-8")
