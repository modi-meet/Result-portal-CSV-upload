import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "portal.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    id              INTEGER PRIMARY KEY,
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
    maths           REAL NOT NULL,
    science         REAL NOT NULL,
    english         REAL NOT NULL,
    social_studies  REAL NOT NULL,
    second_language REAL NOT NULL,
    total           REAL NOT NULL,
    percentage      REAL NOT NULL,
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


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
