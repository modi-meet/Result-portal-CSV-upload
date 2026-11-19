"""Make a realistic messy results CSV, and optionally upload it to a running portal.

    python scripts/seed.py --rows 5000 --out messy.csv
    python scripts/seed.py --rows 5000 --upload http://localhost:8080

Every row gets at most one deliberate problem, so we know exactly how many rows should be
rejected. The script prints that, and after an upload checks the portal agrees.
Standard library only, so it runs anywhere Python 3.10+ does.
"""

import argparse
import csv
import io
import json
import random
import sys
import unicodedata
import urllib.request
import uuid
from datetime import date, timedelta

FIRST = ["Aarav", "Ananya", "Vivaan", "Diya", "Reyansh", "Saanvi", "Kabir", "Zoë", "Ishaan", "Meera", "Arjun",
         "Anaïs", "Rohan", "Kiara", "Imran", "Sneha", "Bjørn", "Tara", "Farhan", "Ritu", "Dev", "Noël", "Aditi"]
LAST = ["Sharma", "Iyer", "D'Souza", "Khan", "Patel", "Nair", "Gupta", "Kumārī", "Reddy", "Bose", "Menon", "Das"]
SUBJECTS = ["maths", "science", "english", "social_studies", "second_language"]
HEADER = ["student_id", "full_name", "email", "date_of_birth", "grade_level", "section", *SUBJECTS, "parent_phone"]

# deliberate problems, each one makes the row invalid
FAULTS = {
    "bad_email": lambda r, rnd: r.__setitem__("email", rnd.choice(["sana@example", "diya@", "riya@@school.edu", "no email"])),
    "mark_out_of_range": lambda r, rnd: r.__setitem__(rnd.choice(SUBJECTS), rnd.choice(["105", "150", "-5", "100.5"])),
    "mark_not_number": lambda r, rnd: r.__setitem__(rnd.choice(SUBJECTS), rnd.choice(["N/A", "eighty", "1e3", "82/100", "AB"])),
    "mark_missing": lambda r, rnd: r.__setitem__(rnd.choice(SUBJECTS), rnd.choice(["", "  "])),
    "bad_dob": lambda r, rnd: r.__setitem__("date_of_birth", rnd.choice(["tomorrow", "11-30-2010", "14.03.2011", "31/02/2012", "2012-13-01"])),
    "dob_out_of_range": lambda r, rnd: r.__setitem__("date_of_birth", rnd.choice(["1970-01-01", (date.today() - timedelta(days=365 * 2)).isoformat()])),
    "bad_grade": lambda r, rnd: r.__setitem__("grade_level", rnd.choice(["ten", "IX", "9th", "0", "13", "-2"])),
    "bad_section": lambda r, rnd: r.__setitem__("section", rnd.choice(["Z", "G", "AB", "1"])),
    "missing_name": lambda r, rnd: r.__setitem__("full_name", rnd.choice(["", "   "])),
    "bad_id": lambda r, rnd: r.__setitem__("student_id", rnd.choice(["S1", "STU 0001", "STU_0001", "X" * 25])),
}


def ascii_only(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().replace("'", "")


def clean_row(i: int, rnd: random.Random, today: date) -> dict:
    first, last = rnd.choice(FIRST), rnd.choice(LAST)
    grade = rnd.randint(1, 12)
    dob = date(today.year - grade - 5, 1, 1) + timedelta(days=rnd.randint(-200, 200))
    row = {
        "student_id": f"STU{i:05d}",
        "full_name": f"{first} {last}",
        "email": ascii_only(f"{first}.{last}{rnd.randint(1, 99)}@example.edu".lower()),
        "date_of_birth": dob.isoformat() if rnd.random() < .75 else dob.strftime("%d/%m/%Y"),
        "grade_level": str(grade),
        "section": rnd.choice("ABCDEF"),
        "parent_phone": f"+91 9{rnd.randint(100000000, 999999999)}",
    }
    for s in SUBJECTS:
        m = min(100, max(0, rnd.gauss(62, 16)))
        row[s] = str(round(m)) if rnd.random() < .6 else f"{m:.1f}"
    return row


def add_harmless_noise(row: dict, rnd: random.Random) -> None:
    """Things that look messy but are valid and should be cleaned up, not rejected."""
    roll = rnd.random()
    if roll < .05:
        row["email"] = row["email"].upper()
    elif roll < .10:
        for k in ("full_name", "email", "section", "maths"):
            row[k] = f"  {row[k]} "
    elif roll < .13:
        row["section"] = row["section"].lower()
    elif roll < .15:
        row["student_id"] = row["student_id"].lower()
    elif roll < .17:
        first, last = row["full_name"].split(" ", 1)
        row["full_name"] = f"{last}, {first}"
    elif roll < .19:
        row["grade_level"] = row["grade_level"].zfill(2)


def generate(rows: int, fault_rate: float, seed: int, today: date) -> tuple[str, int, dict]:
    rnd = random.Random(seed)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(HEADER)
    used_ids, counts, rejected = [], {}, 0

    for i in range(1, rows + 1):
        row = clean_row(i, rnd, today)
        add_harmless_noise(row, rnd)
        fault = None
        if rnd.random() < fault_rate:
            fault = rnd.choice([*FAULTS, "duplicate_id", "extra_field", "missing_field"])
            if fault == "duplicate_id" and used_ids:
                row["student_id"] = rnd.choice(used_ids).lower()
            elif fault in FAULTS:
                FAULTS[fault](row, rnd)
            elif fault == "duplicate_id":
                fault = None
        if fault is None:
            used_ids.append(row["student_id"].strip().upper())
        else:
            counts[fault] = counts.get(fault, 0) + 1
            rejected += 1

        cells = [row[h] for h in HEADER]
        if fault == "extra_field":
            cells.insert(-1, "extra")
        elif fault == "missing_field":
            cells.pop(rnd.randint(6, 10))
        w.writerow(cells)
        if rnd.random() < .002:
            buf.write("\r\n" if rnd.random() < .5 else ",,,,,,,,,,,\r\n")  # blank lines are skipped, not errors
    return "﻿" + buf.getvalue(), rejected, counts


def upload(base: str, name: str, body: bytes) -> dict:
    boundary = uuid.uuid4().hex
    data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: text/csv\r\n\r\n").encode() + body + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{base.rstrip('/')}/api/imports?mode=import", data=data, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as res:
        return json.load(res)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rows", type=int, default=5000)
    p.add_argument("--fault-rate", type=float, default=.07, help="share of rows with a deliberate problem")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", help="write the CSV here")
    p.add_argument("--upload", metavar="URL", help="portal to upload to, e.g. http://localhost:8080")
    a = p.parse_args()

    text, rejected, counts = generate(a.rows, a.fault_rate, a.seed, date.today())
    print(f"generated {a.rows} rows: expect {a.rows - rejected} imported, {rejected} rejected")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<20} {v}")

    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print(f"wrote {a.out}")
    if a.upload:
        rep = upload(a.upload, f"seed-{a.seed}.csv", text.encode())
        print(f"portal says: {rep['rows_read']} read, {rep['imported']} imported, {rep['rejected']} rejected "
              f"({rep['new']} new, {rep['updated']} updated, {rep['unchanged']} unchanged)")
        if (rep["rows_read"], rep["rejected"]) != (a.rows, rejected):
            sys.exit("mismatch between what we generated and what the portal reported")


if __name__ == "__main__":
    main()
