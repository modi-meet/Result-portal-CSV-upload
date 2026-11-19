"""Whole-file behaviour: encodings, line endings, headers, blank lines and broken files."""

import pytest

from app.validation import FileError, check_lines, parse_file
from conftest import HEADER, SAMPLES, TODAY, csv_bytes, row


def run(data: bytes):
    parsed = parse_file(data)
    results = check_lines(parsed, parsed.lines, TODAY)
    return parsed, results


@pytest.mark.parametrize("name,read,imported,rejected,problems", [
    ("students_small.csv", 25, 16, 9, 9),
    ("students_sample.csv", 5000, 4685, 315, 348),
])
def test_sample_pack_numbers(name, read, imported, rejected, problems):
    _, results = run((SAMPLES / name).read_bytes())
    assert len(results) == read
    assert sum(1 for r in results if r.clean) == imported
    assert sum(1 for r in results if not r.clean) == rejected
    assert sum(len(r.problems) for r in results) == problems


def test_bom_crlf_and_quoted_commas():
    data = "﻿" + HEADER + "\r\n" + row(name='"Singh, Aarav"') + "\r\n"
    _, [r] = run(data.encode())
    assert r.clean["full_name"] == "Singh, Aarav"


def test_old_mac_line_endings():
    _, results = run((HEADER + "\r" + row(sid="S01") + "\r" + row(sid="S02")).encode())
    assert [r.line_no for r in results] == [2, 3]


def test_blank_lines_are_skipped_but_counted_in_line_numbers():
    data = csv_bytes(row(sid="S01"), "", "   ", ",,,,,,,,,,", row(sid="S02"))
    _, results = run(data)
    assert [r.line_no for r in results] == [2, 6]


def test_header_case_order_spaces_and_extra_columns():
    cols = HEADER.split(",")
    header = ",".join(f"  {c.upper()} " for c in reversed(cols)) + ",parent_phone"
    values = row().split(",")
    data = (header + "\n" + ",".join(reversed(values)) + ",+91 99999\n").encode()
    _, [r] = run(data)
    assert r.clean["student_id"] == "STU1"


def test_unclosed_quote_only_affects_its_own_line():
    data = csv_bytes(row(sid="S01", name='"Asha Rao'), row(sid="S02"))
    _, results = run(data)
    assert not results[0].clean and results[1].clean


@pytest.mark.parametrize("data,code", [
    (b"", "EMPTY_FILE"),
    (b"\n\n  \n", "EMPTY_FILE"),
    (HEADER.encode() + b"\n", "NO_ROWS"),
    (b"name,marks\nAsha,50\n", "MISSING_COLUMNS"),
    (HEADER.replace(",email", "").encode() + b"\nx\n", "MISSING_COLUMNS"),
    ((HEADER + ",email").encode() + b"\nx\n", "DUPLICATE_COLUMNS"),
    (HEADER.replace(",", ";").encode() + b"\nx\n", "WRONG_DELIMITER"),
    (b"PK\x03\x04rest-of-an-xlsx", "NOT_CSV"),
    (b"%PDF-1.7 ...", "NOT_CSV"),
    (b"\x89PNG\r\n\x1a\n\x00\x00\x00", "NOT_CSV"),
    ("﻿".encode("utf-16") + HEADER.encode("utf-16-le"), "NOT_UTF8"),
    (HEADER.encode() + "\nS1,Zoë".encode("latin-1"), "NOT_UTF8"),
    (b"x" * (10 * 1024 * 1024 + 1), "TOO_LARGE"),
])
def test_bad_files(data, code):
    with pytest.raises(FileError) as e:
        parse_file(data)
    assert e.value.code == code
    assert e.value.message  # always something the admin can read


def test_missing_columns_are_named():
    with pytest.raises(FileError) as e:
        parse_file(HEADER.replace(",email", "").replace(",section", "").encode() + b"\nx\n")
    assert "email" in e.value.message and "section" in e.value.message


def test_non_utf8_error_says_which_line():
    with pytest.raises(FileError) as e:
        parse_file(csv_bytes(row(sid="S01")) + "S02,Zoë".encode("latin-1"))
    assert "Line 3" in e.value.message
