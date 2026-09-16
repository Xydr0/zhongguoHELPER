import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "bot.sqlite3"

BADGE_THRESHOLDS = [50, 100, 500]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    wordoftheday_channel_id INTEGER,
    wordoftheday_level INTEGER
);

CREATE TABLE IF NOT EXISTS user_stats (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    streak_count INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT,
    hsk_level INTEGER,
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS quiz_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    word_simplified TEXT NOT NULL,
    level INTEGER,
    correct INTEGER NOT NULL,
    answered_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quiz_answers_user ON quiz_answers(user_id, guild_id);

CREATE TABLE IF NOT EXISTS badges (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    badge_key TEXT NOT NULL,
    earned_at TEXT NOT NULL,
    PRIMARY KEY (user_id, guild_id, badge_key)
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(_SCHEMA)


# --- Config mot du jour ---------------------------------------------------

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


# --- Utilisateurs / score / streak ----------------------------------------

def _ensure_user_row(conn: sqlite3.Connection, user_id: int, guild_id: int):
    conn.execute(
        "INSERT OR IGNORE INTO user_stats (user_id, guild_id) VALUES (?, ?)",
        (user_id, guild_id),
    )


def get_user_stats(user_id: int, guild_id: int) -> sqlite3.Row:
    with get_connection() as conn:
        _ensure_user_row(conn, user_id, guild_id)
        conn.commit()
        return conn.execute(
            "SELECT * FROM user_stats WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ).fetchone()


def add_xp(user_id: int, guild_id: int, amount: int):
    with get_connection() as conn:
        _ensure_user_row(conn, user_id, guild_id)
        conn.execute(
            "UPDATE user_stats SET xp = MAX(xp + ?, 0) WHERE user_id = ? AND guild_id = ?",
            (amount, user_id, guild_id),
        )


def set_hsk_level(user_id: int, guild_id: int, level: int):
    with get_connection() as conn:
        _ensure_user_row(conn, user_id, guild_id)
        conn.execute(
            "UPDATE user_stats SET hsk_level = ? WHERE user_id = ? AND guild_id = ?",
            (level, user_id, guild_id),
        )


def touch_streak(user_id: int, guild_id: int) -> int:
    """Met a jour le streak (jours consecutifs d'activite) et retourne sa nouvelle valeur."""
    today = date.today()
    with get_connection() as conn:
        _ensure_user_row(conn, user_id, guild_id)
        row = conn.execute(
            "SELECT streak_count, last_active_date FROM user_stats WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ).fetchone()

        last_active = datetime.strptime(row["last_active_date"], "%Y-%m-%d").date() if row["last_active_date"] else None

        if last_active == today:
            new_streak = row["streak_count"] or 1
        elif last_active == today - timedelta(days=1):
            new_streak = (row["streak_count"] or 0) + 1
        else:
            new_streak = 1

        conn.execute(
            "UPDATE user_stats SET streak_count = ?, last_active_date = ? WHERE user_id = ? AND guild_id = ?",
            (new_streak, today.isoformat(), user_id, guild_id),
        )
        return new_streak


def get_leaderboard(guild_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM user_stats WHERE guild_id = ? ORDER BY xp DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()


# --- Historique de quiz / SRS ----------------------------------------------

def record_quiz_answer(user_id: int, guild_id: int, word_simplified: str, level: int | None, correct: bool):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO quiz_answers (user_id, guild_id, word_simplified, level, correct, answered_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, guild_id, word_simplified, level, int(correct), datetime.utcnow().isoformat()),
        )


def words_seen_count(user_id: int, guild_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT word_simplified) AS n FROM quiz_answers WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ).fetchone()
        return row["n"] if row else 0


def words_to_review(user_id: int, guild_id: int, limit: int = 10) -> list[sqlite3.Row]:
    """Mots les plus souvent rates en quiz, en priorite (revision espacee simplifiee)."""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                word_simplified,
                level,
                SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS wrong,
                SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) AS right,
                MAX(answered_at) AS last_seen
            FROM quiz_answers
            WHERE user_id = ? AND guild_id = ?
            GROUP BY word_simplified
            HAVING wrong > 0
            ORDER BY (wrong - right) DESC, last_seen ASC
            LIMIT ?
            """,
            (user_id, guild_id, limit),
        ).fetchall()


# --- Badges -----------------------------------------------------------------

def get_badges(user_id: int, guild_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM badges WHERE user_id = ? AND guild_id = ? ORDER BY earned_at",
            (user_id, guild_id),
        ).fetchall()


def award_badge(user_id: int, guild_id: int, badge_key: str) -> bool:
    """Attribue manuellement un badge. Retourne True si nouvellement attribue, False s'il l'avait deja."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO badges (user_id, guild_id, badge_key, earned_at) VALUES (?, ?, ?, ?)",
            (user_id, guild_id, badge_key, datetime.utcnow().isoformat()),
        )
        return cur.rowcount > 0


def check_and_award_badges(user_id: int, guild_id: int) -> list[int]:
    """Attribue les badges de palier nouvellement atteints (mots vus). Retourne les paliers nouvellement debloques."""
    seen = words_seen_count(user_id, guild_id)
    with get_connection() as conn:
        existing = {
            row["badge_key"]
            for row in conn.execute(
                "SELECT badge_key FROM badges WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            ).fetchall()
        }
        newly_earned = []
        for threshold in BADGE_THRESHOLDS:
            key = f"words_{threshold}"
            if seen >= threshold and key not in existing:
                conn.execute(
                    "INSERT INTO badges (user_id, guild_id, badge_key, earned_at) VALUES (?, ?, ?, ?)",
                    (user_id, guild_id, key, datetime.utcnow().isoformat()),
                )
                newly_earned.append(threshold)
        return newly_earned
