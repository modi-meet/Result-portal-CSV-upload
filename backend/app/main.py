import os
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, imports, students
from .validation import MAX_FILE_BYTES, FileError

STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))


_ready = False


def get_conn():
    # create tables on first use; serverless hosts don't always run startup hooks
    global _ready
    conn = db.connect()
    if not _ready:
        db.init(conn)
        _ready = True
    try:
        yield conn
    finally:
        conn.close()


def get_today() -> date:
    return date.today()


app = FastAPI(title="Results Portal")


@app.exception_handler(FileError)
def _file_error(_, exc: FileError):
    return JSONResponse(status_code=422, content={"detail": {"code": exc.code, "message": exc.message}})


@app.exception_handler(imports.NotFound)
def _not_found(_, __):
    return JSONResponse(status_code=404, content={"detail": {"code": "NOT_FOUND", "message": "Not found."}})


@app.exception_handler(imports.Conflict)
def _conflict(_, exc):
    return JSONResponse(status_code=409, content={"detail": {"code": "CONFLICT", "message": str(exc)}})


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------- imports ----------

@app.post("/api/imports", status_code=201)
def upload(file: UploadFile = File(...), mode: Literal["import", "check"] = "import",
           conn=Depends(get_conn), today: date = Depends(get_today)):
    """mode=import stages and commits in one go (v1). mode=check only stages, so lines can be fixed first (v2)."""
    data = file.file.read(MAX_FILE_BYTES + 1)
    name = file.filename or "upload.csv"
    with conn:  # one transaction: if anything blows up, nothing is half-imported
        import_id = imports.stage(conn, name, data, today)
        if mode == "import":
            imports.commit(conn, import_id, today)
    return imports.report(conn, import_id)


@app.get("/api/imports")
def import_history(conn=Depends(get_conn)):
    return imports.history(conn)


@app.get("/api/imports/{import_id}")
def import_report(import_id: int, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                  conn=Depends(get_conn)):
    return imports.report(conn, import_id, limit, offset)


@app.get("/api/imports/{import_id}/problems.csv")
def import_problems_csv(import_id: int, conn=Depends(get_conn)):
    return _csv(imports.problems_csv(conn, import_id), f"import-{import_id}-problems.csv")


@app.get("/api/imports/{import_id}/lines")
def import_lines(import_id: int, conn=Depends(get_conn)):
    return imports.attention_lines(conn, import_id)


class LineEdit(BaseModel):
    values: dict[str, str] | None = None
    raw: str | None = None
    removed: bool | None = None


@app.patch("/api/imports/{import_id}/lines/{line_no}")
def edit_import_line(import_id: int, line_no: int, edit: LineEdit, conn=Depends(get_conn), today=Depends(get_today)):
    with conn:
        imports.edit_line(conn, import_id, line_no, today, values=edit.values, raw=edit.raw, removed=edit.removed)
    return {"report": imports.report(conn, import_id), **imports.attention_lines(conn, import_id)}


@app.post("/api/imports/{import_id}/commit")
def commit_import(import_id: int, conn=Depends(get_conn), today=Depends(get_today)):
    with conn:
        imports.commit(conn, import_id, today)
    return imports.report(conn, import_id)


@app.get("/api/imports/{import_id}/file.csv")
def corrected_file(import_id: int, conn=Depends(get_conn)):
    imp = conn.execute("SELECT filename FROM imports WHERE id = ?", (import_id,)).fetchone()
    if not imp:
        raise imports.NotFound()
    stem = Path(imp["filename"]).stem
    return _csv(imports.corrected_csv(conn, import_id), f"{stem}-fixed.csv")


def _csv(body: str, filename: str) -> Response:
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# set ALLOW_CLEAR_DATA=0 to hide the "clear all data" action (there are no logins)
ALLOW_CLEAR = os.environ.get("ALLOW_CLEAR_DATA", "1") != "0"


@app.get("/api/config")
def config():
    return {"allow_clear": ALLOW_CLEAR, "max_upload_mb": MAX_FILE_BYTES / 1024 / 1024}


@app.delete("/api/data")
def clear_data(conn=Depends(get_conn)):
    if not ALLOW_CLEAR:
        raise HTTPException(403, {"code": "FORBIDDEN", "message": "Clearing data is turned off on this portal."})
    with conn:
        return {"deleted": imports.clear_all(conn)}


# ---------- students ----------

@app.get("/api/students")
def list_students(q: str = "", grade_level: int | None = Query(None, ge=1, le=12),
                  section: str | None = Query(None, pattern="^[A-Fa-f]$"),
                  sort: Literal["student_id", "full_name", "grade_level", "percentage"] = "student_id",
                  order: Literal["asc", "desc"] = "asc",
                  page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), conn=Depends(get_conn)):
    return students.search(conn, q=q, grade_level=grade_level, section=section, sort=sort, order=order,
                           page=page, page_size=page_size)


@app.get("/api/students/{student_id}")
def get_student(student_id: str, conn=Depends(get_conn)):
    s = students.get(conn, student_id)
    if not s:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": f"No student with ID {student_id.upper()}."})
    return s


# ---------- frontend ----------

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, {"code": "NOT_FOUND", "message": "Not found."})
        file = STATIC_DIR / path
        if path and file.is_file() and STATIC_DIR in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")
