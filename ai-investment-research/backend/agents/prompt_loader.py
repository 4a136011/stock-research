"""載入提示詞並組出完整 system prompt（共用規則 + 角色提示詞 + 輸出 JSON Schema）。"""

import hashlib
import json
from pathlib import Path

from backend.agents.schemas import AdjudicationOutput, AnalystOutput, Role

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
SHARED_FILE = "_shared.md"
REQUIRED_HEADINGS = ("## 角色定位", "## 輸入", "## 分析要求", "## 禁止事項", "## 輸出重點")


class PromptError(Exception):
    pass


def _read(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.is_file():
        raise PromptError(f"找不到提示詞檔：{path}")
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()


def schema_for(role: Role) -> type[AnalystOutput] | type[AdjudicationOutput]:
    return AdjudicationOutput if Role(role) == Role.adjudicator else AnalystOutput


def build_system_prompt(role: Role) -> str:
    role = Role(role)
    schema = json.dumps(schema_for(role).model_json_schema(), ensure_ascii=False, indent=2)
    return "\n\n".join(
        [_read(SHARED_FILE), _read(f"{role.value}.md"), f"## JSON Schema\n\n```json\n{schema}\n```"]
    )


def prompt_version(role: Role) -> str:
    """共用規則與角色提示詞內容的雜湊，寫入 research_runs.prompt_versions 以便追溯。"""
    role = Role(role)
    raw = (_read(SHARED_FILE) + "\n" + _read(f"{role.value}.md")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def validate_prompt_files() -> list[str]:
    problems: list[str] = []
    for name in [SHARED_FILE, *(f"{r.value}.md" for r in Role)]:
        try:
            text = _read(name)
        except PromptError as exc:
            problems.append(str(exc))
            continue
        if not text:
            problems.append(f"{name} 是空的")
        if name != SHARED_FILE:
            problems += [f"{name} 缺少段落 {h}" for h in REQUIRED_HEADINGS if h not in text]
    return problems
