"""
Configuración de la conexión SQLite con WAL mode.
"""
import aiosqlite

DB_PATH = "travian_bot.db"


async def get_connection() -> aiosqlite.Connection:
    """Devuelve una conexión aiosqlite con WAL activado."""
    conn = await aiosqlite.connect(DB_PATH)
    await conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = aiosqlite.Row
    return conn
