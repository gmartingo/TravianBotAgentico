# Clonar este workspace en otro PC

Objetivo: tener **el mismo espacio de trabajo** (código + agentes + memoria de Claude
y de los agentes + permisos) en cualquier dispositivo. El "cerebro" viaja por git; los
**secretos** se copian a mano y **nunca** se versionan.

---

## El workspace son 3 capas

| Capa | Dónde vive | ¿Viaja? | Cómo |
|---|---|---|---|
| **Código + memoria + permisos** | este repo (`TravianBotAgentico`, privado) | ✅ git | `git clone` + `bootstrap` |
| **Agentes** (analista, palantir, desarrollador-\*, ...) | repo `agentes_propios` → `~/.claude/agents/` | ✅ git | lo clona el `bootstrap` |
| **Secretos** (clave Fernet, BD, perfiles Chrome) | fuera de git | ❌ nunca git | copia manual segura |

Qué viaja dentro de este repo (antes estaba ignorado):
- `.claude/agent-memory/` — memoria de los subagentes (capability map de palantir, patrones, etc.).
- `.claude/claude-memory/` — memoria de Claude (las auto-memorias). En cada PC se **enlaza**
  a la ruta que Claude Code espera (`~/.claude/projects/<hash>/memory`) vía `bootstrap`.
- `.claude/settings.json` — permisos y `acceptEdits` (sin secretos), para la misma experiencia.

---

## Pasos en un PC nuevo

### 1. Clonar el repo
```bash
git clone https://github.com/gmartingo/TravianBotAgentico.git ~/DEV/"Travian con Agentes"
cd ~/DEV/"Travian con Agentes"
```
> La ruta de clonado debe ser **la misma** en todos los PC del mismo SO para que el enlace de
> memoria coincida sin ajustes (en macOS: `~/DEV/Travian con Agentes`).

### 2. Ejecutar el bootstrap
macOS / Linux:
```bash
chmod +x bootstrap.sh && ./bootstrap.sh
```
Windows (primera vez: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`):
```powershell
.\bootstrap.ps1
```
El bootstrap: clona `agentes_propios` en `~/.claude/agents`, restaura el `CLAUDE.md` global
(graphify) y enlaza la memoria de Claude a este repo.
> Requiere una **clave SSH dada de alta en GitHub** (el repo de agentes usa SSH).

### 3. Secretos (a mano — NUNCA por git)

**a) Clave Fernet — la MISMA en todos los PC.**
Las contraseñas de las cuentas se guardan cifradas con Fernet; la clave vive solo en la
variable de entorno `TRAVIAN_BOT_SECRET_KEY`. Si difiere entre PCs, las contraseñas de la
BD compartida **no se descifran** (`InvalidToken` → 401 sin abrir Chrome).
```bash
# macOS/Linux — en ~/.zshrc
export TRAVIAN_BOT_SECRET_KEY='<la-misma-clave-de-44-chars-base64url>'
```
```powershell
# Windows
setx TRAVIAN_BOT_SECRET_KEY "<la-misma-clave-de-44-chars-base64url>"
```

**b) BD y perfiles — solo si quieres las MISMAS cuentas.**
Copia por canal seguro (AirDrop, USB, almacenamiento cifrado), nunca por git:
- la base de datos `*.db` (cuentas y mundos, contraseñas cifradas)
- la carpeta `profiles/` (perfiles de Chrome por cuenta — cookies/sesión, clave para la anti-detección)

Si prefieres cuentas independientes por PC, omite este paso y vuelve a darlas de alta.

### 4. Arrancar
El entorno (`.venv`, `node_modules`) se recrea solo con el script de arranque del proyecto.

---

## Mantener los PCs sincronizados

- La memoria es **fuente única de verdad en el repo**: cuando Claude o un agente actualizan
  una memoria, se modifica dentro de `.claude/claude-memory/` o `.claude/agent-memory/`.
  Haz `commit` + `push` y en el otro PC `pull` para tener el mismo cerebro.
- Los agentes se actualizan en su propio repo: `git -C ~/.claude/agents pull`.

## Qué NO se versiona nunca (y por qué)
`profiles/`, `*.db`, `.env`, la clave Fernet → secretos / cookies de sesión. Publicarlos
rompería la seguridad y la anti-detección del bot.
