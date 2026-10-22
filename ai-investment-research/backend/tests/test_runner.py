import json

import pytest

from backend.agents.provider import LLMProvider, MockProvider, ProviderError, get_provider
from backend.agents.runner import (
    AgentErrorKind,
    AgentOutputError,
    build_user_prompt,
    parse_json_object,
    run_role,
)
from backend.agents.schemas import AdjudicationOutput, AnalystOutput, Phase, Role, Stance


def text(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def run(provider, role, snapshot, **kw):
    return run_role(provider, role, snapshot, allow_synthetic=True, **kw)


# ------------------------------------------------------------ 正常流程


def test_run_role_returns_validated_output(example, snapshot):
    provider = MockProvider({"macro": text(example("macro"))})
    out = run(provider, Role.macro, snapshot)
    assert isinstance(out, AnalystOutput)
    assert out.stance == Stance.neutral
    assert provider.requests[0].tag == "macro"


def test_json_inside_code_fence_is_accepted(example, snapshot):
    provider = MockProvider({"macro": "```json\n" + text(example("macro")) + "\n```"})
    assert run(provider, Role.macro, snapshot).role == Role.macro


def test_bull_and_bear_initial_prompts_do_not_contain_other_outputs(example, snapshot):
    provider = MockProvider({"bull": text(example("bull")), "bear": text(example("bear"))})
    run(provider, Role.bull, snapshot)
    run(provider, Role.bear, snapshot)
    for request in provider.requests:
        payload = json.loads(request.user)
        assert payload["other_analyst_outputs"] == {}
        assert payload["research_snapshot"]["snapshot_id"] == snapshot.snapshot_id


def test_bull_rebuttal_receives_bear_output(example, snapshot):
    bear = AnalystOutput.model_validate(example("bear"))
    data = example("bull")
    data["phase"] = "rebuttal"
    data["seen_roles"] = ["bear"]
    provider = MockProvider({"bull": text(data)})
    out = run(provider, Role.bull, snapshot, context={Role.bear: bear}, phase=Phase.rebuttal)
    assert [r.value for r in out.seen_roles] == ["bear"]
    assert "bear" in json.loads(provider.requests[0].user)["other_analyst_outputs"]


def test_adjudicator_receives_all_analyst_outputs(example, snapshot):
    context = {Role(n): AnalystOutput.model_validate(example(n)) for n in
               ("macro", "fundamental", "technical", "bull", "bear")}
    provider = MockProvider({"adjudicator": text(example("adjudicator"))})
    out = run(provider, Role.adjudicator, snapshot, context=context)
    assert isinstance(out, AdjudicationOutput)
    assert set(json.loads(provider.requests[0].user)["other_analyst_outputs"]) == {
        "macro", "fundamental", "technical", "bull", "bear"}


# ------------------------------------------------------------ 失敗路徑：一律報錯，不補預設值


def expect_error(kind, provider, role, snapshot, **kw):
    with pytest.raises(AgentOutputError) as info:
        run(provider, role, snapshot, **kw)
    assert info.value.kind == kind
    return info.value


def test_invalid_json_is_an_error(snapshot):
    err = expect_error(AgentErrorKind.invalid_json, MockProvider({"macro": "not json"}), Role.macro, snapshot)
    assert err.raw == "not json"


def test_json_array_is_an_error(snapshot):
    expect_error(AgentErrorKind.invalid_json, MockProvider({"macro": "[1, 2]"}), Role.macro, snapshot)


def test_schema_violation_is_an_error(example, snapshot):
    data = example("macro")
    data["extra_field"] = 1
    expect_error(AgentErrorKind.schema, MockProvider({"macro": text(data)}), Role.macro, snapshot)


def test_fabricated_evidence_is_an_error(example, snapshot):
    data = example("fundamental")
    data["arguments"][0]["evidence_ids"] = ["S99"]
    expect_error(AgentErrorKind.evidence, MockProvider({"fundamental": text(data)}), Role.fundamental, snapshot)


def test_citing_failed_data_is_an_error(example, snapshot):
    data = example("macro")
    data["arguments"][0]["evidence_ids"] = ["S13"]
    expect_error(AgentErrorKind.evidence, MockProvider({"macro": text(data)}), Role.macro, snapshot)


def test_wrong_role_output_is_an_error(example, snapshot):
    expect_error(AgentErrorKind.role_mismatch, MockProvider({"bull": text(example("bear"))}), Role.bull, snapshot)


def test_wrong_phase_is_an_error(example, snapshot):
    data = example("macro")
    data["phase"] = "rebuttal"
    expect_error(AgentErrorKind.role_mismatch, MockProvider({"macro": text(data)}), Role.macro, snapshot)


def test_bull_initial_with_context_is_blocked_before_calling_provider(example, snapshot):
    bear = AnalystOutput.model_validate(example("bear"))
    provider = MockProvider({"bull": text(example("bull"))})
    expect_error(AgentErrorKind.independence, provider, Role.bull, snapshot, context={Role.bear: bear})
    assert provider.requests == []


def test_misdeclared_seen_roles_is_an_error(example, snapshot):
    bear = AnalystOutput.model_validate(example("bear"))
    data = example("bull")
    data["phase"] = "rebuttal"  # 但 seen_roles 沒有如實列出 bear
    provider = MockProvider({"bull": text(data)})
    expect_error(AgentErrorKind.independence, provider, Role.bull, snapshot,
                 context={Role.bear: bear}, phase=Phase.rebuttal)


def test_adjudicator_without_bull_and_bear_is_blocked(example, snapshot):
    provider = MockProvider({"adjudicator": text(example("adjudicator"))})
    expect_error(AgentErrorKind.missing_input, provider, Role.adjudicator, snapshot)
    assert provider.requests == []


def test_synthetic_snapshot_blocked_by_default(example, snapshot):
    provider = MockProvider({"macro": text(example("macro"))})
    with pytest.raises(AgentOutputError) as info:
        run_role(provider, Role.macro, snapshot)  # 未傳 allow_synthetic
    assert info.value.kind == AgentErrorKind.synthetic_snapshot
    assert provider.requests == []


def test_provider_failure_is_an_error_not_a_default(snapshot):
    expect_error(AgentErrorKind.provider, MockProvider({}), Role.macro, snapshot)


# ------------------------------------------------------------ 其他


def test_parse_json_object_rejects_prose_around_json():
    with pytest.raises(AgentOutputError):
        parse_json_object('好的，以下是結果：{"a": 1}')


def test_provider_registry():
    assert isinstance(get_provider("mock"), LLMProvider)
    with pytest.raises(ProviderError):
        get_provider("nope")


def test_user_prompt_is_pure_json(snapshot):
    payload = json.loads(build_user_prompt(snapshot))
    assert set(payload) == {"instructions", "research_snapshot", "other_analyst_outputs"}
