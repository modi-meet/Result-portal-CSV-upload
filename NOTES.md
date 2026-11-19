# Notes

## Stack
**FastAPI + SQLite + React (Vite).** One container, one process, and no database server to set up. Python's `csv` module and `unicodedata` handle most of the messy parts. SQLite imports 5,000 rows in one transaction in well under a second. React is plain, with no UI kit or state library, because three screens don't need one.

## How an import works
Every upload is first **staged**: the lines are stored and checked, and problems are saved per row. Then it's **committed**: valid rows are upserted into `students` in a single transaction.
- `/import` stages and commits in one request.
- `/import?version=2` stops after staging. The teacher fixes or removes rows, and each edit re-checks the whole file, because changing an ID can create or clear a duplicate elsewhere. They can download the corrected file at any point and import when ready. If they import with rows still broken, they're asked first and those rows are left out. Unfinished checks are deleted after 24 hours.

Both screens share the same rules and code paths. The only difference is when the commit happens.

## Decisions
- **Valid row:** exactly the rules in the sample README. Every problem in a row is reported, not just the first, so a teacher fixes it in one pass. That's why there are 348 problems across 315 rows.
- **Duplicates in a file:** the first row with an ID is the original, even if that row is itself broken. Later rows are rejected and point back to it ("Same student ID as row 14").
- **Same student in a later file:** the latest file wins. The report splits imported rows into new, updated and unchanged.
- **Same file again:** detected by hash and pointed out. It's safe, since every row comes back unchanged.
- **Bad files are rejected whole with a reason, and nothing is imported:**
  - empty file, or header only
  - missing required columns (named in the message), or a column given twice
  - an Excel, PDF or other binary file
  - UTF-16, or non-UTF-8 text (the message gives the line and says to "Save as CSV UTF-8")
  - semicolon- or tab-separated files
  - files over 10 MB

  I don't guess at other encodings, because a wrong guess silently garbles names.
- **One record per physical line.** No column may contain a newline, so this keeps row numbers exact and means one stray quote can't swallow the rest of the file.
- **Strict numbers:** `1e3`, `82/100`, `N/A`, `nan` and `inf` are rejected. `float()` would happily read some of them.
- **Age 5–25 is checked on the import date.** This matters: the sample's 4,685 only holds around now. As of mid-2025 it would be 4,574. Tests pin the date.
- **Names** are trimmed, have repeated spaces collapsed, and are NFC-normalised, so a decomposed "Zoë" matches a composed one. Letters from any script, marks, spaces and `' , . -` are allowed. Digits and emoji are not.
- **Grading:** percentage = total / 500, rounded to one decimal. The grade uses the rounded value so what you see matches it: A ≥ 80, B ≥ 60, C ≥ 50, D ≥ 40, F below 40. **Pass = at least 40% overall and at least 33 in every subject**, so a 95/95/95/95/30 student fails, and the report says why. It all lives in `grading.py`.
- **Search** is case- and accent-insensitive and matches the name or any part of the ID. It runs on the server with paging, and all state is in the URL.
- **Slow imports:** the request is synchronous, with a real upload progress bar and then a "checking" state. At 5,000 rows it's under a second, so a job queue would be overkill.

## Things I noticed in the data
Beyond the obvious traps, some emails don't match the student's name (e.g. "Müller Patel" with `dev.singh10@…`). They aren't against the rules, so they import. Flagging them as warnings would be a nice follow-up.

## Not built
- logins
- deleting or editing students after import
- marks history (only the latest values are kept)
- detecting a file's encoding automatically
- background jobs for very large files

## Next
- **Warnings:** a non-blocking tier for things like name/email mismatches.
- **Column mapping:** for headers like "Maths Marks".
- **Undo an import:** possible, since each student records which import last touched them.
- **Background jobs:** move imports to a job with progress polling once files get much larger.
