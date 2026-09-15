import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bot.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    wordoftheday_channel_id INTEGER,
    wordoftheday_level INTEGER
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(_SCHEMA)


def get_guild_config(guild_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        ).fetchone()


def set_wordoftheday_config(guild_id: int, channel_id: int, level: int | None = None):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO guild_config (guild_id, wordoftheday_channel_id, wordoftheday_level)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                wordoftheday_channel_id = excluded.wordoftheday_channel_id,
                wordoftheday_level = excluded.wordoftheday_level
            """,
            (guild_id, channel_id, level),
        )


def all_wordoftheday_configs() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM guild_config WHERE wordoftheday_channel_id IS NOT NULL"
        ).fetchall()
