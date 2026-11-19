"""Grading scheme. Kept in one place so it's easy to find and change.

- percentage = total / 500, rounded to one decimal (the grade uses the rounded value, so what you see matches)
- grade: A >= 80, B >= 60, C >= 50, D >= 40, F below 40
- pass: at least 40% overall AND at least 33 in every subject
"""

from .validation import SUBJECTS

MAX_PER_SUBJECT = 100
PASS_OVERALL = 40.0
PASS_PER_SUBJECT = 33.0
GRADE_BANDS = [(80.0, "A"), (60.0, "B"), (50.0, "C"), (40.0, "D")]


def summarize(marks: dict) -> dict:
    values = [marks[s] for s in SUBJECTS]
    total = round(sum(values), 2)
    percentage = round(total / (MAX_PER_SUBJECT * len(SUBJECTS)) * 100, 1)
    grade = next((g for cutoff, g in GRADE_BANDS if percentage >= cutoff), "F")
    passed = percentage >= PASS_OVERALL and all(v >= PASS_PER_SUBJECT for v in values)
    return {"total": total, "percentage": percentage, "grade": grade, "passed": passed}
