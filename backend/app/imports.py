"""The import pipeline: stage a file, (optionally) fix lines, then commit valid rows into students.

v1 does stage + commit in one go. v2 stages, lets the teacher fix lines, then commits.
"""

import csv
import hashlib
import io
import json
import unicodedata
from datetime import date, datetime, timedelta, timezone

from . import grading
from .validation import (DUPLICATE_ID, INVALID_FORMAT, LABELS, MISSING_REQUIRED, OUT_OF_RANGE, REQUIRED,
                         WRONG_FIELD_COUNT, Line, ParsedFile, check_lines, parse_file)

STAGE_TTL = timedelta(hours=24)
STUDENT_FIELDS = ["full_name", "email", "date_of_birth", "grade_level", "section", "maths", "science", "english",
                  "social_studies", "second_language"]


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fold(text: str) -> str:
    """Lower-case and strip accents, so “zoe” finds “Zoë”."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


# ---------- staging ----------

def stage(conn, filename: str, data: bytes, today: date) -> int:
    """Parse and store an upload as 'staged'. Raises FileError for files we can't read at all."""
    parsed = parse_file(data)
    cutoff = (datetime.now(timezone.utc) - STAGE_TTL).isoformat(timespec="seconds").replace("+00:00", "Z")
    conn.execute("DELETE FROM imports WHERE status = 'staged' AND created_at < ?", (cutoff,))

    import_id = conn.execute(
        "INSERT INTO imports (filename, file_hash, header, header_raw, status, created_at) VALUES (?,?,?,?,?,?) "
        "RETURNING id",
        (filename, hashlib.sha256(data).hexdigest(), json.dumps(parsed.header), parsed.header_raw, "staged", _now()),
    ).fetchone()[0]
    conn.executemany(
        "INSERT INTO import_lines (import_id, line_no, raw, cells) VALUES (?,?,?,?)",
        [(import_id, l.line_no, l.raw, json.dumps(l.cells)) for l in parsed.lines])
    revalidate(conn, import_id, today)
    return import_id


def _load(conn, import_id: int) -> tuple:
    imp = conn.execute("SELECT * FROM imports WHERE id = ?", (import_id,)).fetchone()
    if not imp:
        raise NotFound()
    rows = conn.execute("SELECT * FROM import_lines WHERE import_id = ? ORDER BY line_no", (import_id,)).fetchall()
    parsed = ParsedFile(header=json.loads(imp["header"]), header_raw=imp["header_raw"],
                        lines=[Line(r["line_no"], r["raw"], json.loads(r["cells"])) for r in rows if not r["removed"]])
    return imp, parsed, rows


def revalidate(conn, import_id: int, today: date):
    """Re-check every line (edits can create or clear duplicates elsewhere) and refresh the stored problems."""
    imp, parsed, rows = _load(conn, import_id)
    results = check_lines(parsed, parsed.lines, today)
    conn.execute("DELETE FROM import_problems WHERE import_id = ?", (import_id,))
    conn.executemany(
        "INSERT INTO import_problems (import_id, line_no, student_id, field, code, message) VALUES (?,?,?,?,?,?)",
        [(import_id, r.line_no, r.student_id, p.field, p.code, p.message) for r in results for p in r.problems])
    valid = sum(1 for r in results if r.clean)
    conn.execute("UPDATE imports SET rows_read = ?, imported = ?, rejected = ?, removed = ? WHERE id = ?",
                 (len(results), valid, len(results) - valid, sum(1 for r in rows if r["removed"]), import_id))
    return results


def edit_line(conn, import_id: int, line_no: int, today: date, *, values: dict | None = None,
              raw: str | None = None, removed: bool | None = None) -> None:
    imp = conn.execute("SELECT status, header FROM imports WHERE id = ?", (import_id,)).fetchone()
    if not imp:
        raise NotFound()
    if imp["status"] != "staged":
        raise Conflict("This import is already done, so its rows can't be changed.")
    line = conn.execute("SELECT * FROM import_lines WHERE import_id = ? AND line_no = ?",
                        (import_id, line_no)).fetchone()
    if not line:
        raise NotFound()

    header = json.loads(imp["header"])
    cells = json.loads(line["cells"])
    new_raw = line["raw"]
    if raw is not None:
        new_raw = raw.replace("\r", " ").replace("\n", " ")
        cells = next(csv.reader([new_raw]))
    if values:
        if len(cells) != len(header):
            raise Conflict("This row has the wrong number of values. Fix the whole line instead.")
        for col, val in values.items():
            if col not in REQUIRED:
                raise Conflict(f"Unknown column: {col}")
            cells[header.index(col)] = str(val)

    conn.execute("UPDATE import_lines SET raw = ?, cells = ?, edited = ?, removed = ? WHERE import_id = ? AND line_no = ?",
                 (new_raw, json.dumps(cells), int(line["edited"] or raw is not None or bool(values)),
                  int(line["removed"] if removed is None else removed), import_id, line_no))
    revalidate(conn, import_id, today)


# ---------- commit ----------

def commit(conn, import_id: int, today: date) -> None:
    imp = conn.execute("SELECT status FROM imports WHERE id = ?", (import_id,)).fetchone()
    if not imp:
        raise NotFound()
    if imp["status"] != "staged":
        raise Conflict("This file has already been imported.")

    results = revalidate(conn, import_id, today)
    valid = [r.clean for r in results if r.clean]
    existing = {}
    ids = [c["student_id"] for c in valid]
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = f"SELECT * FROM students WHERE student_id IN ({','.join('?' * len(chunk))})"
        existing.update({r["student_id"]: r for r in conn.execute(q, chunk)})

    now = _now()
    inserts, updates, unchanged = [], [], 0
    for c in valid:
        summary = grading.summarize(c)
        record = {**c, **summary, "passed": int(summary["passed"]), "import_id": import_id, "updated_at": now,
                  "search_key": fold(f"{c['full_name']} {c['student_id']}")}
        old = existing.get(c["student_id"])
        if old is None:
            inserts.append({**record, "created_at": now})
        elif all(old[f] == c[f] for f in STUDENT_FIELDS):
            unchanged += 1
        else:
            updates.append(record)

    # batched, so a hosted database isn't hit with one round trip per row
    if inserts:
        cols = list(inserts[0])
        conn.executemany(f"INSERT INTO students ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                         [[r[k] for k in cols] for r in inserts])
    if updates:
        cols = [k for k in updates[0] if k != "student_id"]
        conn.executemany(f"UPDATE students SET {', '.join(f'{k} = ?' for k in cols)} WHERE student_id = ?",
                         [[*[r[k] for k in cols], r["student_id"]] for r in updates])
    counts = {"new": len(inserts), "updated": len(updates), "unchanged": unchanged}

    conn.execute("UPDATE imports SET status = 'committed', committed_at = ?, new_count = ?, updated_count = ?, "
                 "unchanged_count = ? WHERE id = ?",
                 (now, counts["new"], counts["updated"], counts["unchanged"], import_id))


# ---------- reading back ----------

GROUP_LABELS = {
    MISSING_REQUIRED: "{label} is empty",
    INVALID_FORMAT: "{label} isn't in the right format",
    OUT_OF_RANGE: "{label} is out of range",
    DUPLICATE_ID: "Student ID repeats an earlier row",
    WRONG_FIELD_COUNT: "Row has the wrong number of values",
}


def report(conn, import_id: int, limit: int = 50, offset: int = 0) -> dict:
    imp = conn.execute("SELECT * FROM imports WHERE id = ?", (import_id,)).fetchone()
    if not imp:
        raise NotFound()
    same = conn.execute(
        "SELECT id, committed_at FROM imports WHERE file_hash = ? AND status = 'committed' AND id < ? "
        "ORDER BY id DESC LIMIT 1", (imp["file_hash"], import_id)).fetchone()
    groups = conn.execute(
        "SELECT field, code, COUNT(DISTINCT line_no) AS rows FROM import_problems WHERE import_id = ? "
        "GROUP BY field, code ORDER BY rows DESC, field", (import_id,)).fetchall()
    total_problems = conn.execute("SELECT COUNT(*) FROM import_problems WHERE import_id = ?", (import_id,)).fetchone()[0]
    problems = conn.execute(
        "SELECT line_no, student_id, field, code, message FROM import_problems WHERE import_id = ? "
        "ORDER BY line_no, id LIMIT ? OFFSET ?", (import_id, limit, offset)).fetchall()

    return {
        **summary(imp),
        "same_file_as": dict(same) if same else None,
        "groups": [{"field": g["field"], "code": g["code"], "rows": g["rows"],
                    "label": GROUP_LABELS[g["code"]].format(label=LABELS.get(g["field"], "Row"))} for g in groups],
        "problems_total": total_problems,
        "problems": [dict(p) for p in problems],
    }


def summary(imp) -> dict:
    return {
        "id": imp["id"],
        "filename": imp["filename"],
        "status": imp["status"],
        "created_at": imp["created_at"],
        "committed_at": imp["committed_at"],
        "rows_read": imp["rows_read"],
        "imported": imp["imported"],
        "rejected": imp["rejected"],
        "removed": imp["removed"],
        "new": imp["new_count"],
        "updated": imp["updated_count"],
        "unchanged": imp["unchanged_count"],
    }


def attention_lines(conn, import_id: int) -> dict:
    """Lines the teacher needs to look at in v2: anything with a problem, plus anything they've touched."""
    imp, parsed, rows = _load(conn, import_id)
    problems: dict[int, list] = {}
    for p in conn.execute("SELECT line_no, field, code, message FROM import_problems WHERE import_id = ? "
                          "ORDER BY line_no, id", (import_id,)):
        problems.setdefault(p["line_no"], []).append({"field": p["field"], "code": p["code"], "message": p["message"]})

    header = parsed.header
    out = []
    for r in rows:
        if not (r["line_no"] in problems or r["edited"] or r["removed"]):
            continue
        cells = json.loads(r["cells"])
        shaped = len(cells) == len(header)
        out.append({
            "line_no": r["line_no"],
            "raw": r["raw"],
            "values": {c: cells[header.index(c)] for c in REQUIRED} if shaped else None,
            "edited": bool(r["edited"]),
            "removed": bool(r["removed"]),
            "problems": problems.get(r["line_no"], []),
        })
    return {"columns": REQUIRED, "lines": out}


def corrected_csv(conn, import_id: int) -> str:
    """The whole file with fixes applied and removed rows left out. Untouched lines are copied as they were."""
    imp, _, rows = _load(conn, import_id)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    buf.write("﻿" + imp["header_raw"] + "\r\n")  # BOM so Excel opens it as UTF-8
    for r in rows:
        if r["removed"]:
            continue
        if r["edited"]:
            writer.writerow(json.loads(r["cells"]))
        else:
            buf.write(r["raw"] + "\r\n")
    return buf.getvalue()


def problems_csv(conn, import_id: int) -> str:
    if not conn.execute("SELECT 1 FROM imports WHERE id = ?", (import_id,)).fetchone():
        raise NotFound()
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    buf.write("﻿")
    writer.writerow(["row", "student_id", "column", "code", "problem"])
    for p in conn.execute("SELECT line_no, student_id, field, code, message FROM import_problems WHERE import_id = ? "
                          "ORDER BY line_no, id", (import_id,)):
        writer.writerow([p["line_no"], p["student_id"], p["field"], p["code"], p["message"]])
    return buf.getvalue()


def history(conn, limit: int = 20) -> list[dict]:
    return [summary(r) for r in conn.execute(
        "SELECT * FROM imports WHERE status = 'committed' ORDER BY id DESC LIMIT ?", (limit,))]
