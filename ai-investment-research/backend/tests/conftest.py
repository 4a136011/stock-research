import copy
import json
from pathlib import Path

import pytest

from backend.agents.schemas import ResearchSnapshot

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = ROOT / "prompts" / "examples"

ANALYST_NAMES = ["macro", "fundamental", "technical", "bull", "bear"]


def load_json(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def snapshot_data() -> dict:
    return load_json("snapshot.synthetic.json")


@pytest.fixture
def snapshot(snapshot_data) -> ResearchSnapshot:
    return ResearchSnapshot.model_validate(snapshot_data)


@pytest.fixture
def example():
    """example('bull') 回傳該角色範例輸出的深拷貝，可安全修改。"""

    def _load(role: str) -> dict:
        return copy.deepcopy(load_json(f"{role}.example.json"))

    return _load
