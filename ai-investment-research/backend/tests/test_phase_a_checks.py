"""把 scripts/check_phase_a.py（僅用標準庫的結構驗收）納入 pytest。"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_phase_a.py"
spec = importlib.util.spec_from_file_location("check_phase_a", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


@pytest.mark.parametrize("name,func", check.CHECKS)
def test_phase_a_check(name, func):
    problems = func()
    assert problems == [], "\n".join(problems)
