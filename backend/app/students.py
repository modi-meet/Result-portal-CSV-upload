import sqlite3

from .grading import PASS_OVERALL, PASS_PER_SUBJECT
from .imports import fold
from .validation import SUBJECTS

LIST_COLUMNS = "student_id, full_name, grade_level, section, percentage, grade, passed"


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(conn: sqlite3.Connection, *, q: str, grade_level: int | None, section: str | None, sort: str,
           order: str, page: int, page_size: int) -> dict:
    where, args = [], []
    q = " ".join(q.split())
    if q:
        where.append("search_key LIKE ? ESCAPE '\\'")
        args.append(f"%{_escape_like(fold(q))}%")
    if grade_level:
        where.append("grade_level = ?")
        args.append(grade_level)
    if section:
        where.append("section = ?")
        args.append(section.upper())
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = conn.execute(f"SELECT COUNT(*) FROM students {clause}", args).fetchone()[0]
    # sort/order come from a whitelist in the route, so formatting them in is safe
    tie = ", student_id" if sort != "student_id" else ""
    rows = conn.execute(
        f"SELECT {LIST_COLUMNS} FROM students {clause} ORDER BY {sort} {order}{tie} LIMIT ? OFFSET ?",
        [*args, page_size, (page - 1) * page_size]).fetchall()
    return {
        "items": [{**dict(r), "passed": bool(r["passed"])} for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get(conn: sqlite3.Connection, student_id: str) -> dict | None:
    row = conn.execute(
        "SELECT s.*, i.filename AS source_file, i.committed_at AS source_imported_at "
        "FROM students s JOIN imports i ON i.id = s.import_id WHERE s.student_id = ?",
        (student_id.strip().upper(),)).fetchone()
    if not row:
        return None
    s = dict(row)
    s.pop("search_key")
    s["passed"] = bool(s["passed"])
    s["marks"] = [{"subject": subj, "mark": s[subj], "passed": s.pop(subj) >= PASS_PER_SUBJECT} for subj in SUBJECTS]
    s["rules"] = {"pass_overall": PASS_OVERALL, "pass_per_subject": PASS_PER_SUBJECT}
    return s
