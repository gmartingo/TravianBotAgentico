# bootstrap.ps1 — Prepara este workspace en un PC nuevo (Windows).
#
# Deja "el cerebro" idéntico al otro PC:
#   - clona el repo de agentes (agentes_propios) en %USERPROFILE%\.claude\agents
#   - restaura el CLAUDE.md global (graphify) si falta
#   - enlaza la memoria de Claude a este repo (junction)
#   - recuerda los secretos que NO viajan por git (clave Fernet, BD, perfiles)
#
# Uso (primera vez puede requerir):  Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
#   .\bootstrap.ps1
#
# Idempotente.
$ErrorActionPreference = "Stop"

$RepoDir    = $PSScriptRoot
$ClaudeHome = Join-Path $env:USERPROFILE ".claude"
$AgentsRepo = "git@github.com:gmartingo/agentes_propios.git"
$AgentsDir  = Join-Path $ClaudeHome "agents"
$ClaudeMem  = Join-Path $RepoDir ".claude\claude-memory"

Write-Host "==> Workspace: $RepoDir"

# 1) Repo de agentes en ~\.claude\agents
if (Test-Path (Join-Path $AgentsDir ".git")) {
    Write-Host "==> agentes_propios ya clonado en $AgentsDir (pull)"
    git -C $AgentsDir pull --ff-only
} else {
    Write-Host "==> Clonando agentes_propios en $AgentsDir"
    New-Item -ItemType Directory -Force -Path $ClaudeHome | Out-Null
    git clone $AgentsRepo $AgentsDir
}

# 2) CLAUDE.md global (graphify)
$GlobalClaudeMd = Join-Path $ClaudeHome "CLAUDE.md"
if (-not (Test-Path $GlobalClaudeMd)) {
    Write-Host "==> Restaurando ~\.claude\CLAUDE.md (graphify)"
    @"
# graphify
- **graphify** (``~/.claude/skills/graphify/SKILL.md``) - any input to knowledge graph. Trigger: ``/graphify``
When the user types ``/graphify``, invoke the Skill tool with ``skill: "graphify"`` before doing anything else.
"@ | Set-Content -Encoding UTF8 $GlobalClaudeMd
} else {
    Write-Host "==> ~\.claude\CLAUDE.md ya existe (no se toca)"
}

# 3) Enlazar la memoria de Claude a este repo (junction)
#    NOTA: la convención exacta del nombre de carpeta en Windows puede variar.
#    Se calcula un valor por defecto (\ / : y espacios -> -) y se imprime para verificar.
$Hash = ($RepoDir -replace '[\\/: ]', '-')
$ProjMem = Join-Path $ClaudeHome "projects\$Hash\memory"
Write-Host "==> Memoria de Claude esperada en: $ProjMem"
New-Item -ItemType Directory -Force -Path (Split-Path $ProjMem) | Out-Null
if (Test-Path $ProjMem) {
    $item = Get-Item $ProjMem -Force
    if ($item.LinkType -eq "Junction") {
        Write-Host "    junction ya existe"
    } else {
        $bk = "$ProjMem.local-backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
        Move-Item $ProjMem $bk
        New-Item -ItemType Junction -Path $ProjMem -Target $ClaudeMem | Out-Null
        Write-Host "    memoria local respaldada en $bk y reemplazada por junction"
    }
} else {
    New-Item -ItemType Junction -Path $ProjMem -Target $ClaudeMem | Out-Null
    Write-Host "    junction creada -> $ClaudeMem"
}
Write-Host "    [!] Verifica que esa es la ruta que usa Claude Code en este PC"
Write-Host "        (mira las carpetas dentro de $ClaudeHome\projects\). Si no coincide,"
Write-Host "        recrea la junction apuntando a la carpeta correcta."

# 4) Secretos que NO viajan por git
Write-Host ""
Write-Host "==> CEREBRO LISTO. Faltan los secretos (ver SETUP-WORKSPACE.md):"
if (-not $env:TRAVIAN_BOT_SECRET_KEY) {
    Write-Host "    [!] TRAVIAN_BOT_SECRET_KEY NO esta definida."
    Write-Host "        Debe ser EXACTAMENTE la misma clave que en el otro PC."
    Write-Host '        setx TRAVIAN_BOT_SECRET_KEY "<la-misma-clave-de-44-chars>"'
} else {
    Write-Host "    [ok] TRAVIAN_BOT_SECRET_KEY presente."
}
Write-Host "    [ ] Copia la BD (*.db) y la carpeta profiles\ por canal seguro,"
Write-Host "        NUNCA por git. Solo si quieres las MISMAS cuentas en este PC."
Write-Host ""
Write-Host "Hecho."
