"""單一角色執行器：組提示詞 → 呼叫 provider → 解析 → Pydantic 驗證 → 證據驗證。

任何一步失敗都 raise AgentOutputError（附 kind 與原文），不回傳半成品、不補預設值。
資料庫寫入（research_runs / debate_messages）於階段 D 接上。
"""

import json
import re
from collections.abc import Mapping
from enum import Enum

from pydantic import ValidationError

from backend.agents.prompt_loader import build_system_prompt, schema_for
from backend.agents.provider import LLMProvider, LLMRequest, ProviderError
from backend.agents.schemas import (
    AdjudicationOutput,
    AnalystOutput,
    EvidenceValidationError,
    Phase,
    ResearchSnapshot,
    Role,
    validate_against_snapshot,
)


class AgentErrorKind(str, Enum):
    provider = "provider"
    invalid_json = "invalid_json"
    schema = "schema"
    evidence = "evidence"
    role_mismatch = "role_mismatch"
    independence = "independence"
    missing_input = "missing_input"
    synthetic_snapshot = "synthetic_snapshot"


class AgentOutputError(Exception):
    def __init__(self, kind: AgentErrorKind, message: str, *, raw: str | None = None):
        self.kind = kind
        self.raw = raw
        super().__init__(f"[{kind.value}] {message}")


_FENCE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def parse_json_object(text: str) -> dict:
    """只接受單一 JSON 物件（可被 ``` 圍欄包住）；不做子字串猜測。"""
    cleaned = text.strip()
    match = _FENCE.match(cleaned)
    if match:
        cleaned = match.group(1).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AgentOutputError(AgentErrorKind.invalid_json, str(exc), raw=text) from exc
    if not isinstance(data, dict):
        raise AgentOutputError(AgentErrorKind.invalid_json, "輸出不是 JSON 物件", raw=text)
    return data


def build_user_prompt(
    snapshot: ResearchSnapshot, context: Mapping[Role, AnalystOutput] | None = None
) -> str:
    context = context or {}
    payload = {
        "instructions": "依系統提示的規則分析下列研究快照，只輸出符合 JSON Schema 的單一 JSON 物件。",
        "research_snapshot": snapshot.model_dump(mode="json"),
        "other_analyst_outputs": {
            role.value: output.model_dump(mode="json")
            for role, output in sorted(context.items(), key=lambda kv: kv[0].value)
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run_role(
    provider: LLMProvider,
    role: Role,
    snapshot: ResearchSnapshot,
    *,
    context: Mapping[Role, AnalystOutput] | None = None,
    phase: Phase = Phase.initial,
    model: str | None = None,
    max_tokens: int = 2000,
    temperature: float = 0.2,
    allow_synthetic: bool = False,
) -> AnalystOutput | AdjudicationOutput:
    role = Role(role)
    context = dict(context or {})

    if snapshot.is_synthetic and not allow_synthetic:
        raise AgentOutputError(
            AgentErrorKind.synthetic_snapshot, "合成（測試用）快照不可用於真實研究流程"
        )
    if role in (Role.bull, Role.bear) and phase == Phase.initial and context:
        raise AgentOutputError(
            AgentErrorKind.independence, f"{role.value} 初始分析不得收到其他角色的輸出"
        )
    if role == Role.adjudicator:
        missing = {Role.bull, Role.bear} - set(context)
        if missing:
            names = ", ".join(sorted(r.value for r in missing))
            raise AgentOutputError(AgentErrorKind.missing_input, f"裁決缺少輸入：{names}")

    request = LLMRequest(
        system=build_system_prompt(role),
        user=build_user_prompt(snapshot, context),
        tag=role.value,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    try:
        response = provider.complete(request)
    except ProviderError as exc:
        raise AgentOutputError(AgentErrorKind.provider, str(exc)) from exc

    data = parse_json_object(response.text)
    try:
        output = schema_for(role).model_validate(data)
    except ValidationError as exc:
        raise AgentOutputError(AgentErrorKind.schema, str(exc), raw=response.text) from exc

    if Role(output.role) != role:
        raise AgentOutputError(
            AgentErrorKind.role_mismatch,
            f"要求角色 {role.value}，輸出角色為 {Role(output.role).value}",
            raw=response.text,
        )
    if isinstance(output, AnalystOutput):
        if output.phase != phase:
            raise AgentOutputError(
                AgentErrorKind.role_mismatch,
                f"要求 phase={phase.value}，輸出 phase={output.phase.value}",
                raw=response.text,
            )
        if set(output.seen_roles) != set(context):
            raise AgentOutputError(
                AgentErrorKind.independence,
                "輸出宣稱的 seen_roles 與實際提供的輸入不一致",
                raw=response.text,
            )

    try:
        validate_against_snapshot(output, snapshot)
    except EvidenceValidationError as exc:
        raise AgentOutputError(AgentErrorKind.evidence, str(exc), raw=response.text) from exc
    return output
