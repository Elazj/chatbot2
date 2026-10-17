"""
SQLite storage for accounts and everything that belongs to one student:
chat history, reminders, and notes.

SQLite ships with Python, so there is nothing to install or run. The file
lives at instance/nocturna.db and is created automatically on first start.

Every table except `users` has a user_id, so one student can never see
another student's messages, reminders, notes, documents, quizzes, flashcards
or study plans -- each query filters on it, and the API layer answers 404
(not 403) for ids that belong to someone else.

Schema changes are applied by _migrate(), which is safe to run on an existing
database: new tables are created, and new columns are added to old tables
without touching the rows already there.
"""

import os
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'bot')),
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    due_date    TEXT NOT NULL,
    announced   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id, due_date);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id, id);
"""
LEARNING_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT NOT NULL DEFAULT 'New chat',
    explain_mode TEXT NOT NULL DEFAULT 'default',
    document_id  INTEGER,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at);

CREATE TABLE IF NOT EXISTS message_feedback (
    message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    value      INTEGER NOT NULL CHECK (value IN (-1, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS courses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id   INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    filename    TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'material' CHECK (kind IN ('material', 'past_exam')),
    status      TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'failed')),
    stage       TEXT NOT NULL DEFAULT 'Uploading...',
    error       TEXT,
    pages       INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_docs_user ON documents(user_id, course_id);

CREATE TABLE IF NOT EXISTS document_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id   INTEGER,
    ord         INTEGER NOT NULL,
    page        INTEGER,
    section     TEXT,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_scope ON document_chunks(user_id, document_id, course_id);

CREATE TABLE IF NOT EXISTS quizzes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL DEFAULT 'quiz' CHECK (kind IN ('quiz', 'mock_exam')),
    title        TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT '{}',
    course_id    INTEGER,
    document_id  INTEGER,
    duration_min INTEGER,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_quizzes_user ON quizzes(user_id, id);

CREATE TABLE IF NOT EXISTS quiz_questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id     INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    qtype       TEXT NOT NULL CHECK (qtype IN ('mcq', 'tf', 'short', 'open')),
    prompt      TEXT NOT NULL,
    options     TEXT NOT NULL DEFAULT '[]',
    answer      TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT '',
    topic       TEXT,
    reference   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id    INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score      REAL NOT NULL DEFAULT 0,
    total      INTEGER NOT NULL DEFAULT 0,
    results    TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS flashcards (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    front         TEXT NOT NULL,
    back          TEXT NOT NULL,
    topic         TEXT,
    course_id     INTEGER,
    document_id   INTEGER,
    ease          REAL NOT NULL DEFAULT 2.5,
    interval_days INTEGER NOT NULL DEFAULT 0,
    reps          INTEGER NOT NULL DEFAULT 0,
    lapses        INTEGER NOT NULL DEFAULT 0,
    due_date      TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cards_due ON flashcards(user_id, due_date);

CREATE TABLE IF NOT EXISTS flashcard_reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id    INTEGER NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating     INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 4),
    topic      TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS study_plans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    course_id     INTEGER,
    exam_date     TEXT NOT NULL,
    hours_per_day REAL NOT NULL DEFAULT 2,
    level         TEXT NOT NULL DEFAULT 'intermediate',
    struggling    TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS study_tasks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id   INTEGER NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day_index INTEGER NOT NULL,
    due_date  TEXT NOT NULL,
    label     TEXT NOT NULL,
    topic     TEXT,
    kind      TEXT NOT NULL DEFAULT 'study',
    done      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_plan ON study_tasks(plan_id, day_index);

CREATE TABLE IF NOT EXISTS study_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    ref        INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_user ON study_events(user_id, created_at);

CREATE TABLE IF NOT EXISTS past_exam_analyses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id  INTEGER,
    doc_ids    TEXT NOT NULL DEFAULT '[]',
    result     TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def connection():
    """Open a connection, commit on success, roll back on error, always close."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.executescript(LEARNING_SCHEMA)
        _backfill_conversations(conn)


# ------------------------------------------------------------- migrations

def _columns(conn, table: str):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(conn, table: str, column: str, ddl: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _migrate(conn) -> None:
    """Bring a database created by an older version up to date."""
    _add_column(conn, "messages", "conversation_id", "INTEGER REFERENCES conversations(id) ON DELETE CASCADE")
    _add_column(conn, "messages", "meta", "TEXT NOT NULL DEFAULT '{}'")
    _add_column(conn, "notes", "title", "TEXT NOT NULL DEFAULT ''")
    _add_column(conn, "notes", "course_id", "INTEGER")
    _add_column(conn, "notes", "document_id", "INTEGER")
    _add_column(conn, "notes", "updated_at", "TEXT")


def _backfill_conversations(conn) -> None:
    """Messages saved before conversations existed go into one 'Earlier chat'
    conversation per student, so nothing is lost."""
    rows = conn.execute(
        "SELECT DISTINCT user_id FROM messages WHERE conversation_id IS NULL"
    ).fetchall()
    for r in rows:
        uid = r["user_id"]
        last = conn.execute(
            "SELECT MAX(created_at) AS t FROM messages WHERE user_id = ? AND conversation_id IS NULL", (uid,)
        ).fetchone()["t"]
        cur = conn.execute(
            "INSERT INTO conversations (user_id, title, updated_at) VALUES (?, 'Earlier chat', ?)", (uid, last)
        )
        conn.execute(
            "UPDATE messages SET conversation_id = ? WHERE user_id = ? AND conversation_id IS NULL",
            (cur.lastrowid, uid),
        )


# ----------------------------------------------------- tiny query helpers

def fetchall(sql: str, params=()):
    with connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def fetchone(sql: str, params=()):
    with connection() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def execute(sql: str, params=()) -> int:
    """Run one write statement; returns the new row id (for INSERTs)."""
    with connection() as conn:
        return conn.execute(sql, params).lastrowid


def executemany(sql: str, rows) -> None:
    with connection() as conn:
        conn.executemany(sql, rows)


# ------------------------------------------------------------------ users

def create_user(full_name: str, email: str, password_hash: str) -> int:
    """Raises sqlite3.IntegrityError if the email is already registered."""
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
            (full_name, email, password_hash),
        )
        return cur.lastrowid


def get_user_by_email(email: str):
    with connection() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def get_user_by_id(user_id: int):
    with connection() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


# ---------------------------------------------------------- conversations

def create_conversation(user_id: int, title: str = "New chat") -> int:
    return execute("INSERT INTO conversations (user_id, title) VALUES (?, ?)", (user_id, title))


def get_conversation(user_id: int, conversation_id: int):
    """None if it doesn't exist OR belongs to another student."""
    return fetchone("SELECT * FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id))


def latest_conversation(user_id: int):
    return fetchone("SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1", (user_id,))


def list_conversations(user_id: int, q: str = ""):
    if q:
        like = "%" + q.replace("%", "").replace("_", "") + "%"
        return fetchall(
            "SELECT DISTINCT c.id, c.title, c.updated_at FROM conversations c "
            "LEFT JOIN messages m ON m.conversation_id = c.id "
            "WHERE c.user_id = ? AND (c.title LIKE ? OR m.content LIKE ?) "
            "ORDER BY c.updated_at DESC, c.id DESC LIMIT 100",
            (user_id, like, like),
        )
    return fetchall(
        "SELECT id, title, updated_at FROM conversations WHERE user_id = ? "
        "ORDER BY updated_at DESC, id DESC LIMIT 200",
        (user_id,),
    )


def touch_conversation(conversation_id: int) -> None:
    execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (conversation_id,))


def clear_all_conversations(user_id: int) -> None:
    """Deletes chats (and their messages and feedback) only. Documents,
    notes, quizzes, flashcards, plans and progress are deliberately kept."""
    execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))


# --------------------------------------------------------------- messages

def add_message(user_id: int, role: str, content: str, conversation_id=None, meta=None) -> int:
    import json as _json
    if conversation_id is None:
        conv = latest_conversation(user_id)
        conversation_id = conv["id"] if conv else create_conversation(user_id)
    mid = execute(
        "INSERT INTO messages (user_id, role, content, conversation_id, meta) VALUES (?, ?, ?, ?, ?)",
        (user_id, role, content, conversation_id, _json.dumps(meta or {})),
    )
    touch_conversation(conversation_id)
    return mid


def get_messages(user_id: int, limit: int = 200, conversation_id=None):
    """Most recent `limit` messages of one conversation (default: the latest
    one), oldest first, with the student's feedback on each reply."""
    import json as _json
    if conversation_id is None:
        conv = latest_conversation(user_id)
        if not conv:
            return []
        conversation_id = conv["id"]
    rows = fetchall(
        "SELECT m.id, m.role, m.content, m.created_at, m.meta, f.value AS feedback "
        "FROM messages m LEFT JOIN message_feedback f ON f.message_id = m.id "
        "WHERE m.user_id = ? AND m.conversation_id = ? ORDER BY m.id DESC LIMIT ?",
        (user_id, conversation_id, limit),
    )
    out = []
    for r in reversed(rows):
        try:
            r["meta"] = _json.loads(r["meta"] or "{}")
        except ValueError:
            r["meta"] = {}
        out.append(r)
    return out


def clear_messages(user_id: int) -> None:
    clear_all_conversations(user_id)


# ------------------------------------------------------------------ notes

def add_note(user_id: int, content: str, title: str = "", course_id=None, document_id=None) -> int:
    if not title:
        first = content.strip().splitlines()[0] if content.strip() else "Untitled note"
        title = first[:60]
    return execute(
        "INSERT INTO notes (user_id, content, title, course_id, document_id, updated_at) "
        "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (user_id, content, title, course_id, document_id),
    )


def get_notes(user_id: int, limit: int = 10):
    return fetchall(
        "SELECT content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
