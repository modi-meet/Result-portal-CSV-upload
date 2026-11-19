import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, main

# the sample pack's expected numbers depend on "today" (the 5–25 age rule), so pin it
TODAY = date(2026, 11, 19)
SAMPLES = Path(__file__).resolve().parents[2] / "data-sample"
# the sample pack isn't committed (it's confidential); drop it into data-sample/ to run these too
needs_samples = pytest.mark.skipif(not (SAMPLES / "students_sample.csv").exists(), reason="sample pack not in data-sample/")
HEADER = "student_id,full_name,email,date_of_birth,grade_level,section,maths,science,english,social_studies,second_language"


def row(sid="STU1", name="Asha Rao", email="asha@school.edu", dob="2012-03-14", grade="9", section="B",
        marks=("80", "70", "60", "50", "40")) -> str:
    return ",".join([sid, name, email, dob, grade, section, *marks])


def csv_bytes(*rows: str, header: str = HEADER) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(db, "DATABASE_URL", os.environ.get("TEST_DATABASE_URL"))
    monkeypatch.setattr(main, "_ready", False)
    if db.DATABASE_URL:  # same suite against postgres: start from empty tables
        conn = db.connect()
        with conn:
            conn.execute("DROP TABLE IF EXISTS students, import_problems, import_lines, imports")
        conn.close()
    main.app.dependency_overrides[main.get_today] = lambda: TODAY
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def upload(client, data: bytes, name="results.csv", mode="import"):
    return client.post(f"/api/imports?mode={mode}", files={"file": (name, data, "text/csv")})
