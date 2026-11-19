from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, main

# the sample pack's expected numbers depend on "today" (the 5–25 age rule), so pin it
TODAY = date(2026, 11, 19)
SAMPLES = Path(__file__).resolve().parents[2] / "data-sample"
HEADER = "student_id,full_name,email,date_of_birth,grade_level,section,maths,science,english,social_studies,second_language"


def row(sid="STU1", name="Asha Rao", email="asha@school.edu", dob="2012-03-14", grade="9", section="B",
        marks=("80", "70", "60", "50", "40")) -> str:
    return ",".join([sid, name, email, dob, grade, section, *marks])


def csv_bytes(*rows: str, header: str = HEADER) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    main.app.dependency_overrides[main.get_today] = lambda: TODAY
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def upload(client, data: bytes, name="results.csv", mode="import"):
    return client.post(f"/api/imports?mode={mode}", files={"file": (name, data, "text/csv")})
