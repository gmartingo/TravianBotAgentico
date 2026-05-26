---
name: fernet-key-must-be-persisted
description: TRAVIAN_BOT_SECRET_KEY debe ser estable/persistida o las contraseñas guardadas quedan indescifrables
metadata: 
  node_type: memory
  type: reference
  originSessionId: 3cb63abf-740c-4663-91de-fe22727bffcb
---

La contraseña de cada cuenta se guarda **cifrada con Fernet** en `accounts.password` (BLOB). La clave vive SOLO en la variable de entorno `TRAVIAN_BOT_SECRET_KEY` (ver `core/crypto.py::load_fernet_key`); la app NO la auto-carga de ningún fichero y crashea al arrancar si falta.

**Gotcha crítico:** si la clave cambia entre el registro y el login (p.ej. se generó al vuelo con `Fernet.generate_key()` en una shell efímera), `decrypt` lanza `InvalidToken` → `LoginFailedError`/401 **antes de abrir Chrome**. La contraseña guardada con la clave perdida es irrecuperable: hay que re-guardarla (PUT /accounts/{id} con password) o borrar+re-registrar bajo una clave estable.

**Solución operativa:** fijar la clave en `~/.zshrc` (`export TRAVIAN_BOT_SECRET_KEY='<44 chars, base64url, termina en =>'`) para que sea la misma en todo arranque. El 2026-05-26 el usuario tuvo que borrar y re-registrar la cuenta de prueba (testtravian13@gmail.com) por este motivo; al re-registrar con clave estable el login real funcionó. Relacionado: [[login-sesion-api-feature]], [[registro-cuentas-mundos-feature]].
