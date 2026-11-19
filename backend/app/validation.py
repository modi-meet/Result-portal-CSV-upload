"""CSV parsing and row rules. Pure functions, no database, so it's easy to test."""

import csv
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

# Vercel caps request bodies at 4.5 MB, so the deployed app sets MAX_UPLOAD_MB=4
MAX_FILE_BYTES = int(float(os.environ.get("MAX_UPLOAD_MB", "10")) * 1024 * 1024)

SUBJECTS = ["maths", "science", "english", "social_studies", "second_language"]
REQUIRED = ["student_id", "full_name", "email", "date_of_birth", "grade_level", "section", *SUBJECTS]

LABELS = {
    "student_id": "Student ID",
    "full_name": "Name",
    "email": "Email",
    "date_of_birth": "Date of birth",
    "grade_level": "Class",
    "section": "Section",
    "maths": "Maths",
    "science": "Science",
    "english": "English",
    "social_studies": "Social studies",
    "second_language": "Second language",
}

# row error codes (from the brief)
MISSING_REQUIRED = "MISSING_REQUIRED"
INVALID_FORMAT = "INVALID_FORMAT"
OUT_OF_RANGE = "OUT_OF_RANGE"
DUPLICATE_ID = "DUPLICATE_ID"
WRONG_FIELD_COUNT = "WRONG_FIELD_COUNT"

ID_RE = re.compile(r"[A-Z0-9-]{3,20}")
EMAIL_RE = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
                      r"@([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}")
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
DMY_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
WHOLE_RE = re.compile(r"\d+")
# plain decimals only: "72", "72.5", "-5". Excel-isms like "1e3" or "82/100" don't count.
MARK_RE = re.compile(r"-?(\d+(\.\d*)?|\.\d+)")
NAME_PUNCT = set(" '’,.-")


class FileError(Exception):
    """The whole file can't be imported. `message` is meant for a school admin."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Problem:
    field: str  # a column name, or "row" for whole-row problems
    code: str
    message: str


@dataclass
class Line:
    """One non-blank data line from the file."""
    line_no: int
    raw: str
    cells: list[str]


@dataclass
class ParsedFile:
    header: list[str]  # normalised names, same order as the file
    header_raw: str
    lines: list[Line]

    def index_of(self, column: str) -> int:
        return self.header.index(column)


@dataclass
class RowResult:
    line_no: int
    student_id: str  # as best we can tell, for showing in the report
    clean: dict | None  # set only when the row is valid
    problems: list[Problem] = field(default_factory=list)


# ---------- file level ----------

def _decode(data: bytes) -> str:
    if not data.strip():
        raise FileError("EMPTY_FILE", "The file is empty.")
    head = data[:8]
    if head.startswith(b"PK\x03\x04") or head.startswith(b"\xd0\xcf\x11\xe0"):
        raise FileError("NOT_CSV", "This is an Excel workbook, not a CSV. In Excel use File → Save As → "
                                   "“CSV UTF-8 (comma delimited)” and upload that file.")
    if head.startswith(b"%PDF"):
        raise FileError("NOT_CSV", "This is a PDF, not a CSV. Export the spreadsheet as CSV UTF-8 and upload that.")
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise FileError("NOT_UTF8", "This file is saved as “Unicode text” (UTF-16). Save it as "
                                    "“CSV UTF-8 (comma delimited)” and upload it again.")
    if b"\x00" in data[:8192]:
        raise FileError("NOT_CSV", "This doesn't look like a CSV file. Export the spreadsheet as CSV UTF-8 and try again.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        line = data[: e.start].count(b"\n") + 1
        raise FileError("NOT_UTF8", f"Line {line} has characters that aren't UTF-8. This usually means the file was "
                                    "saved as plain “CSV” in Excel. Save it as “CSV UTF-8 (comma delimited)” and "
                                    "upload it again, so names with accents aren't garbled.")


def _split_cells(line: str) -> list[str]:
    return next(csv.reader([line]))


def _is_blank(cells: list[str]) -> bool:
    return all(not c.strip() for c in cells)


def parse_file(data: bytes) -> ParsedFile:
    """Read the bytes into a header and data lines, or raise FileError.

    Each physical line is one record. No column is allowed to contain a newline, so this
    keeps line numbers exact and stops one stray quote from swallowing the rest of the file.
    """
    if len(data) > MAX_FILE_BYTES:
        raise FileError("TOO_LARGE", f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB. "
                                     "Split it into smaller files and upload them one by one.")
    text = _decode(data)
    physical = re.split(r"\r\n|\n|\r", text)

    header_idx = next((i for i, l in enumerate(physical) if l.strip() and not _is_blank(_split_cells(l))), None)
    if header_idx is None:
        raise FileError("EMPTY_FILE", "The file is empty.")

    header_raw = physical[header_idx]
    header = [h.strip().lower() for h in _split_cells(header_raw)]
    _check_header(header, header_raw)

    lines = []
    for i in range(header_idx + 1, len(physical)):
        raw = physical[i]
        if not raw.strip():
            continue
        cells = _split_cells(raw)
        if _is_blank(cells):
            continue
        lines.append(Line(line_no=i + 1, raw=raw, cells=cells))

    if not lines:
        raise FileError("NO_ROWS", "The file has a header row but no student rows under it.")
    return ParsedFile(header=header, header_raw=header_raw, lines=lines)


def _check_header(header: list[str], header_raw: str) -> None:
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        for sep, name in ((";", "semicolons"), ("\t", "tabs")):
            if sep in header_raw and all(c in [h.strip().lower() for h in header_raw.split(sep)] for c in REQUIRED):
                raise FileError("WRONG_DELIMITER", f"The columns are separated by {name}, not commas. "
                                                   "Save the file as “CSV UTF-8 (comma delimited)” and try again.")
        if len(missing) == len(REQUIRED):
            raise FileError("MISSING_COLUMNS", "The first row should be the column headings (student_id, full_name, "
                                               "email, …) but none of them were found.")
        raise FileError("MISSING_COLUMNS", "These required columns are missing: " + ", ".join(missing) + ".")
    dupes = sorted({c for c in REQUIRED if header.count(c) > 1})
    if dupes:
        raise FileError("DUPLICATE_COLUMNS", "These columns appear more than once, so we can't tell which to use: "
                                             + ", ".join(dupes) + ".")


# ---------- row level ----------

def _show(value: str) -> str:
    value = value.strip()
    return f"“{value[:40]}…”" if len(value) > 40 else f"“{value}”"


def _age_on(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _parse_date(value: str) -> date | None:
    """Returns a date, or None if it's not one of the two allowed formats. Raises ValueError if it's not a real date."""
    if m := ISO_DATE_RE.fullmatch(value):
        y, mo, d = map(int, m.groups())
    elif m := DMY_DATE_RE.fullmatch(value):
        d, mo, y = map(int, m.groups())
    else:
        return None
    return date(y, mo, d)


def _valid_name_chars(name: str) -> bool:
    has_letter = False
    for ch in name:
        cat = unicodedata.category(ch)
        if cat[0] == "L":
            has_letter = True
        elif cat[0] != "M" and ch not in NAME_PUNCT:
            return False
    return has_letter


def validate_values(values: dict[str, str], today: date) -> tuple[dict | None, list[Problem]]:
    """Check one row's required columns. Returns (clean record or None, problems)."""
    problems: list[Problem] = []
    clean: dict = {}

    def problem(col, code, msg):
        problems.append(Problem(col, code, msg))

    v = {k: values.get(k, "").strip() for k in REQUIRED}
    for col in REQUIRED:
        if not v[col]:
            problem(col, MISSING_REQUIRED, f"{LABELS[col]} is empty.")

    if v["student_id"]:
        sid = v["student_id"].upper()
        if ID_RE.fullmatch(sid):
            clean["student_id"] = sid
        else:
            problem("student_id", INVALID_FORMAT,
                    f"Student ID {_show(v['student_id'])} should be 3–20 letters, digits or hyphens.")

    if v["full_name"]:
        name = unicodedata.normalize("NFC", re.sub(r"\s+", " ", v["full_name"]))
        if not 2 <= len(name) <= 100:
            problem("full_name", OUT_OF_RANGE, f"Name {_show(name)} should be 2 to 100 characters long.")
        elif not _valid_name_chars(name):
            problem("full_name", INVALID_FORMAT,
                    f"Name {_show(name)} can only have letters, spaces, apostrophes, commas, hyphens and full stops.")
        else:
            clean["full_name"] = name

    if v["email"]:
        if EMAIL_RE.fullmatch(v["email"]):
            clean["email"] = v["email"].lower()
        else:
            problem("email", INVALID_FORMAT, f"{_show(v['email'])} isn't a valid email address.")

    if v["date_of_birth"]:
        raw = v["date_of_birth"]
        try:
            dob = _parse_date(raw)
            if dob is None:
                problem("date_of_birth", INVALID_FORMAT,
                        f"Date of birth {_show(raw)} isn't in a format we accept. Use YYYY-MM-DD or DD/MM/YYYY.")
            else:
                age = _age_on(dob, today)
                if 5 <= age <= 25:
                    clean["date_of_birth"] = dob.isoformat()
                else:
                    problem("date_of_birth", OUT_OF_RANGE,
                            f"Date of birth {_show(raw)} makes the student {age} years old. Students must be 5 to 25.")
        except ValueError:
            problem("date_of_birth", INVALID_FORMAT, f"Date of birth {_show(raw)} isn't a real date.")

    if v["grade_level"]:
        if not WHOLE_RE.fullmatch(v["grade_level"]):
            problem("grade_level", INVALID_FORMAT, f"Class {_show(v['grade_level'])} should be a whole number from 1 to 12.")
        elif not 1 <= int(v["grade_level"]) <= 12:
            problem("grade_level", OUT_OF_RANGE, f"Class {int(v['grade_level'])} is outside 1 to 12.")
        else:
            clean["grade_level"] = int(v["grade_level"])

    if v["section"]:
        if re.fullmatch(r"[A-Fa-f]", v["section"]):
            clean["section"] = v["section"].upper()
        else:
            problem("section", INVALID_FORMAT, f"Section {_show(v['section'])} should be one letter from A to F.")

    for subj in SUBJECTS:
        raw = v[subj]
        if not raw:
            continue
        if not MARK_RE.fullmatch(raw):
            problem(subj, INVALID_FORMAT, f"{LABELS[subj]} mark {_show(raw)} isn't a number. Use something like 72 or 72.5.")
            continue
        mark = float(raw)
        if 0 <= mark <= 100:
            clean[subj] = mark
        else:
            problem(subj, OUT_OF_RANGE, f"{LABELS[subj]} mark {raw} is outside 0 to 100.")

    return (None, problems) if problems else (clean, [])


def check_lines(parsed: ParsedFile, lines: list[Line], today: date) -> list[RowResult]:
    """Validate lines in file order. The first line with a given ID is the original; later ones are duplicates,
    even if the original itself had problems."""
    width = len(parsed.header)
    first_seen: dict[str, int] = {}
    id_col = parsed.index_of("student_id")
    results = []

    for line in lines:
        if len(line.cells) != width:
            guess = line.cells[id_col].strip().upper() if len(line.cells) > id_col else ""
            results.append(RowResult(line.line_no, guess, None, [Problem(
                "row", WRONG_FIELD_COUNT,
                f"Expected {width} values but found {len(line.cells)}. Usually a stray comma or an extra column.")]))
            continue

        values = {col: line.cells[i] for i, col in enumerate(parsed.header) if col in REQUIRED}
        clean, problems = validate_values(values, today)
        sid = values["student_id"].strip().upper()

        if sid:
            if sid in first_seen:
                problems.append(Problem("student_id", DUPLICATE_ID,
                                        f"Same student ID as row {first_seen[sid]}. Only the first one is kept."))
                clean = None
            else:
                first_seen[sid] = line.line_no
        results.append(RowResult(line.line_no, sid, clean, problems))
    return results
