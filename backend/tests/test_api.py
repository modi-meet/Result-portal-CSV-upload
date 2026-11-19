"""End to end through HTTP: upload, re-upload, the fix-then-import flow, and the student pages."""

from conftest import SAMPLES, csv_bytes, row, upload


def test_import_sample_file(client):
    r = upload(client, (SAMPLES / "students_sample.csv").read_bytes(), "students_sample.csv")
    assert r.status_code == 201
    rep = r.json()
    assert (rep["rows_read"], rep["imported"], rep["rejected"]) == (5000, 4685, 315)
    assert (rep["new"], rep["updated"], rep["unchanged"]) == (4685, 0, 0)
    assert rep["problems_total"] == 348 and len(rep["problems"]) == 50
    assert sum(g["rows"] for g in rep["groups"]) >= 315
    assert client.get("/api/students").json()["total"] == 4685


def test_same_file_again_changes_nothing_and_says_so(client):
    data = (SAMPLES / "students_small.csv").read_bytes()
    first = upload(client, data).json()
    again = upload(client, data).json()
    assert (again["new"], again["updated"], again["unchanged"]) == (0, 0, 16)
    assert again["same_file_as"]["id"] == first["id"]
    assert client.get("/api/students").json()["total"] == 16


def test_later_file_updates_existing_students(client):
    upload(client, csv_bytes(row(sid="S01"), row(sid="S02")))
    rep = upload(client, csv_bytes(row(sid="S01", marks=("90", "90", "90", "90", "90")), row(sid="S03"))).json()
    assert (rep["new"], rep["updated"], rep["unchanged"]) == (1, 1, 0)
    assert client.get("/api/students/S01").json()["percentage"] == 90.0


def test_bad_file_is_a_clear_error_and_imports_nothing(client):
    r = upload(client, b"PK\x03\x04junk", "results.xlsx")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "NOT_CSV"
    assert client.get("/api/students").json()["total"] == 0
    assert client.get("/api/imports").json() == []


def test_problem_report_csv(client):
    rep = upload(client, csv_bytes(row(sid="S01", email="bad"))).json()
    body = client.get(f"/api/imports/{rep['id']}/problems.csv").text
    assert "row,student_id,column,code,problem" in body and "INVALID_FORMAT" in body


def test_fix_then_import_flow(client):
    data = csv_bytes(row(sid="S01"), row(sid="S02", email="bad"), row(sid="S03") + ",extra", row(sid="S04", section="Z"))
    rep = upload(client, data, "class9.csv", mode="check").json()
    iid = rep["id"]
    assert rep["status"] == "staged" and (rep["imported"], rep["rejected"]) == (1, 3)
    assert client.get("/api/students").json()["total"] == 0  # nothing lands until commit

    lines = client.get(f"/api/imports/{iid}/lines").json()["lines"]
    assert [l["line_no"] for l in lines] == [3, 4, 5]
    assert lines[1]["values"] is None  # wrong shape: edited as a raw line

    client.patch(f"/api/imports/{iid}/lines/3", json={"values": {"email": "s02@school.edu"}})
    client.patch(f"/api/imports/{iid}/lines/4", json={"raw": row(sid="S03")})
    res = client.patch(f"/api/imports/{iid}/lines/5", json={"removed": True}).json()
    assert (res["report"]["imported"], res["report"]["rejected"], res["report"]["removed"]) == (3, 0, 1)
    assert all(l["edited"] or l["removed"] for l in res["lines"])  # fixed rows stay visible

    fixed = client.get(f"/api/imports/{iid}/file.csv")
    assert 'attachment; filename="class9-fixed.csv"' == fixed.headers["content-disposition"]
    text = fixed.text.lstrip("﻿")
    assert "s02@school.edu" in text and "extra" not in text and "S04" not in text
    assert text.count("\r\n") == 4  # header + 3 rows

    done = client.post(f"/api/imports/{iid}/commit").json()
    assert (done["status"], done["new"]) == ("committed", 3)
    assert client.patch(f"/api/imports/{iid}/lines/3", json={"removed": True}).status_code == 409
    assert client.post(f"/api/imports/{iid}/commit").status_code == 409


def test_editing_an_id_can_clear_a_duplicate_elsewhere(client):
    iid = upload(client, csv_bytes(row(sid="S01", email="bad"), row(sid="S01")), mode="check").json()["id"]
    res = client.patch(f"/api/imports/{iid}/lines/2", json={"values": {"student_id": "S09", "email": "a@b.edu"}}).json()
    assert res["report"]["rejected"] == 0


def test_student_search_and_paging(client):
    upload(client, csv_bytes(row(sid="S01", name="Zoë Nair", grade="9"), row(sid="S02", name="Arjun Rao", grade="10"),
                             row(sid="X100", name="Zoya Khan", grade="9", section="C")))
    s = lambda **p: client.get("/api/students", params=p).json()
    assert [i["student_id"] for i in s(q="zoe")["items"]] == ["S01"]  # accent-insensitive
    assert [i["student_id"] for i in s(q="ZO")["items"]] == ["S01", "X100"]
    assert [i["student_id"] for i in s(q="x10")["items"]] == ["X100"]
    assert s(q="%")["total"] == 0  # LIKE wildcards are escaped
    assert s(grade_level=9, section="c")["total"] == 1
    page = s(page_size=2, page=2)
    assert (page["total"], len(page["items"])) == (3, 1)
    assert client.get("/api/students", params={"page_size": 1000}).status_code == 422


def test_student_report_and_not_found(client):
    upload(client, csv_bytes(row(sid="STU-9", marks=("95", "95", "95", "95", "30"))))
    st = client.get("/api/students/stu-9").json()
    assert st["student_id"] == "STU-9" and st["grade"] == "A" and st["passed"] is False
    assert [m["passed"] for m in st["marks"]] == [True, True, True, True, False]
    r = client.get("/api/students/NOPE")
    assert r.status_code == 404 and "NOPE" in r.json()["detail"]["message"]
