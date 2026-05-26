---
name: game-data-port-pattern
description: Patrón de inyección de GameDataPort — singleton en app.state igual que translation_port
metadata:
  type: project
---

GameDataPort está implementado como GameDataSQLiteAdapter, inicializado en el lifespan de FastAPI junto a translation_port.

**Why:** Se sigue exactamente el mismo patrón que translation_port: singleton en app.state, inyectado via `Depends(get_game_data_port)` desde `adapters/api/dependencies.py`.

**How to apply:**
- Para nuevos endpoints que necesiten datos de troop_stats/troop_upgrades/icon_metadata: `game_data_port: GameDataPort = Depends(get_game_data_port)`
- Los tests de API mockean `app.state.game_data_port` directamente con un MagicMock que tiene métodos AsyncMock
- La conexión SQLite se cierra en el lifespan (yield / conn.close())

El endpoint GET /catalog/troops/{tribe}/stats inyecta DOS puertos: game_data_port + translation_port (para el nombre localizado con fallback).

Relacionado con: [[fastapi-conventions]]
