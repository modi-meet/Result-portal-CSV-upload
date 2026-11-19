"""One row at a time: does each column rule accept what it should and reject what it shouldn't?"""

import pytest

from app.grading import summarize
from app.validation import parse_file, check_lines
from conftest import TODAY, csv_bytes, row


def check(*rows):
    parsed = parse_file(csv_bytes(*rows))
    return check_lines(parsed, parsed.lines, TODAY)


def codes(result):
    return {(p.field, p.code) for p in result.problems}


def test_clean_row_is_normalised():
    [r] = check(row(sid=" stu-01 ", name="  Zoë   D'Souza ", email=" ZOE@School.EDU ", dob="14/03/2012",
                    grade="09", section=" b ", marks=("100", "0", "72.5", " 33 ", "40.0")))
    assert r.problems == []
    assert r.clean == {"student_id": "STU-01", "full_name": "Zoë D'Souza", "email": "zoe@school.edu",
                       "date_of_birth": "2012-03-14", "grade_level": 9, "section": "B",
                       "maths": 100.0, "science": 0.0, "english": 72.5, "social_studies": 33.0,
                       "second_language": 40.0}


@pytest.mark.parametrize("col,kwargs", [
    ("student_id", {"sid": ""}), ("full_name", {"name": "  "}), ("email", {"email": ""}),
    ("date_of_birth", {"dob": ""}), ("grade_level", {"grade": ""}), ("section", {"section": ""}),
    ("maths", {"marks": ("", "1", "1", "1", "1")}),
])
def test_missing_required(col, kwargs):
    [r] = check(row(**kwargs))
    assert (col, "MISSING_REQUIRED") in codes(r) and r.clean is None


@pytest.mark.parametrize("sid,ok", [("AB", False), ("ABC", True), ("A" * 20, True), ("A" * 21, False),
                                    ("STU_01", False), ("STU 01", False), ("stu-01", True)])
def test_student_id(sid, ok):
    [r] = check(row(sid=sid))
    assert (r.clean is not None) == ok


@pytest.mark.parametrize("name,ok", [("Singh, Aarav", True), ("O'Brien", True), ("Ritu Kumārī", True),
                                     ("Zoë Nair", True), ("A", False), ("x" * 101, False),
                                     ("R2D2", False), ("Asha 🙂", False), ("--", False)])
def test_name(name, ok):
    [r] = check(row(name=f'"{name}"'))
    assert (r.clean is not None) == ok


def test_name_is_nfc_normalised():
    [r] = check(row(name="Zoë"))
    assert r.clean["full_name"] == "Zoë"


@pytest.mark.parametrize("email,ok", [("a.b@x.edu", True), ("sana@example", False), ("diya@", False),
                                      ("riya@@example.edu", False), ("a b@x.edu", False), ("a..b@x.edu", False)])
def test_email(email, ok):
    [r] = check(row(email=email))
    assert (r.clean is not None) == ok


@pytest.mark.parametrize("dob,code", [
    ("2012-03-14", None), ("14/03/2012", None),
    ("tomorrow", "INVALID_FORMAT"), ("11-30-2010", "INVALID_FORMAT"), ("14.03.2011", "INVALID_FORMAT"),
    ("03/14/2012", "INVALID_FORMAT"),  # US order -> month 14 isn't real
    ("2011-02-29", "INVALID_FORMAT"), ("4/3/2012", "INVALID_FORMAT"),
    ("2023-06-01", "OUT_OF_RANGE"), ("1970-01-01", "OUT_OF_RANGE"),
])
def test_date_of_birth(dob, code):
    [r] = check(row(dob=dob))
    assert ([p.code for p in r.problems] or [None]) == [code]


def test_age_boundaries_are_inclusive():
    # TODAY is 2026-11-19: turning 5 today is fine, turning 26 today is not
    assert check(row(dob="2021-11-19"))[0].clean
    assert not check(row(dob="2021-11-20"))[0].clean
    assert check(row(dob="2001-11-20"))[0].clean
    assert not check(row(dob="2000-11-19"))[0].clean


@pytest.mark.parametrize("grade,code", [("9", None), ("09", None), ("12", None), ("0", "OUT_OF_RANGE"),
                                        ("13", "OUT_OF_RANGE"), ("-2", "INVALID_FORMAT"), ("ten", "INVALID_FORMAT"),
                                        ("IX", "INVALID_FORMAT"), ("9th", "INVALID_FORMAT"), ("9.0", "INVALID_FORMAT")])
def test_grade_level(grade, code):
    [r] = check(row(grade=grade))
    assert ([p.code for p in r.problems] or [None]) == [code]


@pytest.mark.parametrize("section,ok", [("a", True), ("F", True), ("G", False), ("Z", False), ("AB", False), ("1", False)])
def test_section(section, ok):
    [r] = check(row(section=section))
    assert (r.clean is not None) == ok


@pytest.mark.parametrize("mark,code", [
    ("0", None), ("100", None), ("99.5", None), ("100.0", None),
    ("100.5", "OUT_OF_RANGE"), ("150", "OUT_OF_RANGE"), ("-5", "OUT_OF_RANGE"),
    ("1e3", "INVALID_FORMAT"),  # float() would happily read this as 1000
    ("82/100", "INVALID_FORMAT"), ("N/A", "INVALID_FORMAT"), ("eighty", "INVALID_FORMAT"), ("nan", "INVALID_FORMAT"),
    ("inf", "INVALID_FORMAT"),
])
def test_marks(mark, code):
    [r] = check(row(marks=(mark, "50", "50", "50", "50")))
    assert ([p.code for p in r.problems] or [None]) == [code]


def test_all_problems_in_a_row_are_reported():
    [r] = check(row(email="nope", section="Z", marks=("150", "x", "50", "50", "50")))
    assert codes(r) == {("email", "INVALID_FORMAT"), ("section", "INVALID_FORMAT"),
                        ("maths", "OUT_OF_RANGE"), ("science", "INVALID_FORMAT")}


def test_duplicates_are_case_insensitive_and_first_row_wins():
    a, b, c = check(row(sid="STU1"), row(sid="stu1", name="Other Kid"), row(sid="STU2"))
    assert a.clean and not b.clean and c.clean
    assert codes(b) == {("student_id", "DUPLICATE_ID")}
    assert "row 2" in b.problems[0].message


def test_duplicate_of_an_invalid_first_row_is_still_a_duplicate():
    a, b = check(row(sid="STU1", email="bad"), row(sid="STU1"))
    assert not a.clean and codes(b) == {("student_id", "DUPLICATE_ID")}


def test_wrong_field_count():
    short, long_ = check(row()[: row().rfind(",")], row() + ",extra")
    assert codes(short) == {("row", "WRONG_FIELD_COUNT")} and codes(long_) == {("row", "WRONG_FIELD_COUNT")}


def test_wrong_field_count_row_does_not_claim_its_id():
    bad, good = check(row(sid="STU1") + ",extra", row(sid="STU1"))
    assert not bad.clean and good.clean


@pytest.mark.parametrize("marks,pct,grade,passed", [
    ((80, 80, 80, 80, 80), 80.0, "A", True),
    ((79.9, 80, 80, 80, 80), 80.0, "A", True),  # 79.98 shows as 80.0%, so it's an A
    ((60, 60, 60, 60, 59), 59.8, "C", True),
    ((40, 40, 40, 40, 40), 40.0, "D", True),
    ((95, 95, 95, 95, 32), 82.4, "A", False),  # great overall, but failed one subject
    ((39, 39, 39, 39, 39), 39.0, "F", False),
])
def test_grading(marks, pct, grade, passed):
    subjects = ["maths", "science", "english", "social_studies", "second_language"]
    s = summarize(dict(zip(subjects, marks)))
    assert (s["percentage"], s["grade"], s["passed"]) == (pct, grade, passed)
