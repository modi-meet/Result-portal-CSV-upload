# Results Portal

Upload a CSV of term results, see exactly what was accepted and why the rest wasn't, then search any student and open their report.

- **Import** (`/import`): upload a file. Good rows go in, and every problem is listed by row number in plain words. You can download the list as a CSV.
- **Import, check and fix** (`/import?version=2`): the file is only checked at first. You fix or remove problem rows right there, download the corrected file, then import once.
- **Students** (`/students`): search by name or ID (case and accents don't matter), filter by class, sort, and page through.
- **Student report** (`/students/:id`): details, marks, total, percentage, grade and pass/fail. You can print it.

## Run it with Docker

```bash
docker build -t results-portal .
docker run --rm -p 8080:8080 -v results-data:/data results-portal
```

Open http://localhost:8080. The SQLite database lives in the `results-data` volume, so it survives restarts. Drop `-v …` for a throwaway run.

## Load some data

A fresh install starts empty, and every screen shows a clear empty state with a way forward. To fill it, generate a messy file:

```bash
python3 scripts/seed.py --rows 5000 --upload http://localhost:8080
```

It prints how many rows it deliberately broke, then checks that the portal rejected exactly those. Use `--out file.csv` to just write the file. It needs only plain Python 3.10+.

## Run the tests

```bash
cd backend && uv run pytest
```

[uv](https://docs.astral.sh/uv/) installs everything on the first run. Without uv: `pip install fastapi uvicorn python-multipart pytest httpx`, then run `pytest` inside `backend/`.

What's covered:
- every column rule, including its edge cases
- whole-file problems: encodings, Excel files, missing columns, semicolons, blank lines and line endings
- the sample pack's expected numbers (25/16/9 and 5,000/4,685/315). The pack is confidential, so it isn't in the repo: put `students_small.csv` and `students_sample.csv` in `data-sample/` and these tests run, otherwise they're skipped
- the API flows: re-uploads, the fix-then-import flow, and search
- a property-style check that the importer rejects exactly the rows the seed script broke

## Develop locally

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

The Vite dev server (http://localhost:5173) proxies `/api` to port 8000.

## Layout

```
backend/app/validation.py   file + row rules (pure functions, most of the tests live here)
backend/app/imports.py      stage → (fix) → commit pipeline, reports, CSV downloads
backend/app/grading.py      the grading scheme, in one place
backend/app/students.py     search and the report
backend/app/main.py         FastAPI routes, also serves the built frontend
frontend/src/pages/         Import, FixImport (v2), Students, StudentReport
scripts/seed.py             messy data generator + uploader
```

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/api/imports?mode=import\|check` | Upload a CSV (multipart `file`). `import` saves valid rows now; `check` only stages it |
| GET | `/api/imports` | Recent imports |
| GET | `/api/imports/{id}?offset=&limit=` | Report: counts, grouped reasons, problems (paged) |
| GET | `/api/imports/{id}/problems.csv` | Problem list as CSV |
| GET | `/api/imports/{id}/lines` | Rows that need attention (v2) |
| PATCH | `/api/imports/{id}/lines/{row}` | Fix a row: `{values}`, `{raw}` or `{removed}` |
| GET | `/api/imports/{id}/file.csv` | The corrected file |
| POST | `/api/imports/{id}/commit` | Import a staged file |
| GET | `/api/students?q=&grade_level=&section=&sort=&order=&page=&page_size=` | Search |
| GET | `/api/students/{id}` | One student's report |

File-level problems come back as `422` with `{detail: {code, message}}`, and the message is written for a school admin.
