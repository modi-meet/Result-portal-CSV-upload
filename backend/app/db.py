"""Database access. SQLite by default (local, Docker, tests); Postgres when DATABASE_URL is set (e.g. Neon on Vercel).

Both give back the same shape: conn.execute(sql with ? placeholders), rows readable by name or index,
and `with conn:` for a transaction. So the rest of the app doesn't care which one it's talking to.
"""

import os
import re
import sqlite3
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "portal.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    id              {pk},
    filename        TEXT NOT NULL,
    file_hash       TEXT NOT NULL,
    header          TEXT NOT NULL,          -- json list, normalised names
    header_raw      TEXT NOT NULL,
    status          TEXT NOT NULL,          -- 'staged' (being checked/fixed) or 'committed'
    created_at      TEXT NOT NULL,
    committed_at    TEXT,
    rows_read       INTEGER NOT NULL DEFAULT 0,
    imported        INTEGER NOT NULL DEFAULT 0,
    rejected        INTEGER NOT NULL DEFAULT 0,
    removed         INTEGER NOT NULL DEFAULT 0,
    new_count       INTEGER NOT NULL DEFAULT 0,
    updated_count   INTEGER NOT NULL DEFAULT 0,
    unchanged_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS imports_hash ON imports(file_hash, status);

-- every data line of an upload, so a staged file can be fixed and downloaded again
CREATE TABLE IF NOT EXISTS import_lines (
    import_id INTEGER NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
    line_no   INTEGER NOT NULL,
    raw       TEXT NOT NULL,
    cells     TEXT NOT NULL,                -- json list
    edited    INTEGER NOT NULL DEFAULT 0,
    removed   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (import_id, line_no)
);

CREATE TABLE IF NOT EXISTS import_problems (
    id         {pk},
    import_id  INTEGER NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
    line_no    INTEGER NOT NULL,
    student_id TEXT NOT NULL,
    field      TEXT NOT NULL,
    code       TEXT NOT NULL,
    message    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS problems_import ON import_problems(import_id, line_no);

CREATE TABLE IF NOT EXISTS students (
    student_id      TEXT PRIMARY KEY,
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL,
    date_of_birth   TEXT NOT NULL,
    grade_level     INTEGER NOT NULL,
    section         TEXT NOT NULL,
    maths           {real} NOT NULL,
    science         {real} NOT NULL,
    english         {real} NOT NULL,
    social_studies  {real} NOT NULL,
    second_language {real} NOT NULL,
    total           {real} NOT NULL,
    percentage      {real} NOT NULL,
    grade           TEXT NOT NULL,
    passed          INTEGER NOT NULL,
    search_key      TEXT NOT NULL,          -- lower-case, accent-free name + id
    import_id       INTEGER NOT NULL REFERENCES imports(id),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS students_class ON students(grade_level, section);
CREATE INDEX IF NOT EXISTS students_name ON students(full_name);
CREATE INDEX IF NOT EXISTS students_pct ON students(percentage);
"""


def connect(path: str | None = None):
    if DATABASE_URL and path is None:
        return PgConnection(DATABASE_URL)
    path = path or DB_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init(conn) -> None:
    if isinstance(conn, PgConnection):
        with conn:
            for stmt in SCHEMA.format(pk="SERIAL PRIMARY KEY", real="DOUBLE PRECISION").split(";"):
                if stmt.strip():
                    conn.execute(stmt)
    else:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA.format(pk="INTEGER PRIMARY KEY", real="REAL"))


# ---------- postgres ----------

class Row(dict):
    """A dict that also answers row[0], like sqlite3.Row."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _row_factory(cursor):
    names = [c.name for c in cursor.description or []]
    return lambda values: Row(zip(names, values))


_PLACEHOLDER = re.compile(r"\?")


class PgConnection:
    def __init__(self, url: str):
        import psycopg  # only needed when deployed with Postgres

        self._conn = psycopg.connect(url, row_factory=_row_factory, prepare_threshold=None)

    def execute(self, sql: str, params=()):
        return self._conn.execute(_PLACEHOLDER.sub("%s", sql), params)

    def executemany(self, sql: str, rows):
        rows = list(rows)
        cur = self._conn.cursor()
        if rows:
            cur.executemany(_PLACEHOLDER.sub("%s", sql), rows)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()

    def close(self):
        self._conn.close()
