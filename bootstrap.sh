#!/usr/bin/env bash
#
# bootstrap.sh — Prepara este workspace en un PC nuevo (macOS / Linux).
#
# Deja "el cerebro" idéntico al otro PC:
#   - clona el repo de agentes (agentes_propios) en ~/.claude/agents
#   - restaura el CLAUDE.md global (graphify) si falta
#   - enlaza la memoria de Claude (~/.claude/projects/<hash>/memory) a este repo
#   - recuerda los secretos que NO viajan por git (clave Fernet, BD, perfiles)
#
# Uso:
#   chmod +x bootstrap.sh && ./bootstrap.sh
#
# Idempotente: se puede ejecutar varias veces sin romper nada.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="$HOME/.claude"
AGENTS_REPO="git@github.com:gmartingo/agentes_propios.git"
AGENTS_DIR="$CLAUDE_HOME/agents"
CLAUDE_MEM="$REPO_DIR/.claude/claude-memory"

echo "==> Workspace: $REPO_DIR"

# 1) Repo de agentes (analista, palantir, desarrollador-*, ...) en ~/.claude/agents
if [ -d "$AGENTS_DIR/.git" ]; then
  echo "==> agentes_propios ya clonado en $AGENTS_DIR (pull)"
  git -C "$AGENTS_DIR" pull --ff-only || echo "    (pull omitido; revisa el estado del repo de agentes)"
else
  echo "==> Clonando agentes_propios en $AGENTS_DIR"
  mkdir -p "$CLAUDE_HOME"
  git clone "$AGENTS_REPO" "$AGENTS_DIR"
fi

# 2) CLAUDE.md global (instrucción del skill graphify)
if [ ! -f "$CLAUDE_HOME/CLAUDE.md" ]; then
  echo "==> Restaurando ~/.claude/CLAUDE.md (graphify)"
  cat > "$CLAUDE_HOME/CLAUDE.md" <<'EOF'
# graphify
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.
EOF
else
  echo "==> ~/.claude/CLAUDE.md ya existe (no se toca)"
fi

# 3) Enlazar la memoria de Claude a este repo (fuente única de verdad)
#    Claude Code guarda la memoria del proyecto en:
#      ~/.claude/projects/<ruta-absoluta-con-/-y-espacios-como-->/memory
HASH="$(printf '%s' "$REPO_DIR" | sed 's/[/ ]/-/g')"
PROJ_MEM="$CLAUDE_HOME/projects/$HASH/memory"
echo "==> Memoria de Claude esperada en: $PROJ_MEM"
mkdir -p "$(dirname "$PROJ_MEM")"
if [ -L "$PROJ_MEM" ]; then
  ln -sfn "$CLAUDE_MEM" "$PROJ_MEM"
  echo "    symlink actualizado -> $CLAUDE_MEM"
elif [ -e "$PROJ_MEM" ]; then
  BK="${PROJ_MEM}.local-backup-$(date +%Y%m%d-%H%M%S)"
  mv "$PROJ_MEM" "$BK"
  ln -sfn "$CLAUDE_MEM" "$PROJ_MEM"
  echo "    memoria local respaldada en $BK y reemplazada por symlink"
else
  ln -sfn "$CLAUDE_MEM" "$PROJ_MEM"
  echo "    symlink creado -> $CLAUDE_MEM"
fi

# 4) Secretos que NO viajan por git
echo ""
echo "==> CEREBRO LISTO. Faltan los secretos (ver SETUP-WORKSPACE.md):"
if [ -z "${TRAVIAN_BOT_SECRET_KEY:-}" ]; then
  echo "    [!] TRAVIAN_BOT_SECRET_KEY NO está en el entorno."
  echo "        Debe ser EXACTAMENTE la misma clave que en el otro PC, o no se"
  echo "        descifrarán las contraseñas guardadas. Añádela a ~/.zshrc:"
  echo "        export TRAVIAN_BOT_SECRET_KEY='<la-misma-clave-de-44-chars>'"
else
  echo "    [ok] TRAVIAN_BOT_SECRET_KEY presente en el entorno."
fi
echo "    [ ] Copia la BD (*.db) y la carpeta profiles/ por canal seguro (AirDrop/USB),"
echo "        NUNCA por git. Solo si quieres las MISMAS cuentas en este PC."
echo ""
echo "Hecho."
