"""The seed script knows exactly which rows it broke, so the importer must agree with it, row for row."""

import importlib.util
from pathlib import Path

import pytest

from app.validation import check_lines, parse_file
from conftest import TODAY

spec = importlib.util.spec_from_file_location("seed", Path(__file__).resolve().parents[2] / "scripts" / "seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


@pytest.mark.parametrize("rng", [1, 2, 3])
def test_importer_matches_seeded_faults(rng):
    text, rejected, _ = seed.generate(3000, .1, rng, TODAY)
    parsed = parse_file(text.encode())
    results = check_lines(parsed, parsed.lines, TODAY)
    assert len(results) == 3000
    assert sum(1 for r in results if not r.clean) == rejected
