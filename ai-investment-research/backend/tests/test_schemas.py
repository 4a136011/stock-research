import copy

import pytest
from pydantic import ValidationError

from backend.agents.schemas import (
    AdjudicationOutput,
    AnalystOutput,
    EvidenceValidationError,
    ResearchSnapshot,
    SnapshotItem,
    validate_against_snapshot,
)
from backend.tests.conftest import ANALYST_NAMES


# ------------------------------------------------------------ 範例輸出


@pytest.mark.parametrize("name", ANALYST_NAMES)
def test_analyst_examples_validate_and_cite_real_evidence(name, example, snapshot):
    out = AnalystOutput.model_validate(example(name))
    validate_against_snapshot(out, snapshot)


def test_adjudicator_example_validates(example, snapshot):
    out = AdjudicationOutput.model_validate(example("adjudicator"))
    validate_against_snapshot(out, snapshot)
    assert out.verdict.value == "watch"  # 範例示範「證據不足以給方向時可觀望」


def test_fundamental_and_technical_examples_do_not_share_a_preset_stance(example):
    stances = {AnalystOutput.model_validate(example(n)).stance for n in ("fundamental", "technical")}
    assert len(stances) == 2  # 範例本身不應預設同一立場


# ------------------------------------------------------------ 快照


def test_error_snapshot_item_must_not_carry_a_value(snapshot_data):
    for item in snapshot_data["items"]:
        if item["id"] == "S13":
            item["value"] = 0.5  # 試圖在失敗資料上填入數值
    with pytest.raises(ValidationError):
        ResearchSnapshot.model_validate(snapshot_data)


def test_ok_snapshot_item_requires_a_value():
    with pytest.raises(ValidationError):
        SnapshotItem(id="S1", field="x", source="s", fetched_at="2026-10-22T00:00:00Z", status="ok")


def test_duplicate_snapshot_ids_rejected(snapshot_data):
    snapshot_data["items"].append(copy.deepcopy(snapshot_data["items"][0]))
    with pytest.raises(ValidationError):
        ResearchSnapshot.model_validate(snapshot_data)


# ------------------------------------------------------------ AnalystOutput 規則


def test_extra_fields_are_forbidden(example):
    data = example("macro")
    data["buy_now"] = True
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(data)


@pytest.mark.parametrize("role", ["bull", "bear"])
def test_bull_bear_initial_cannot_have_seen_other_roles(role, example):
    data = example(role)
    data["seen_roles"] = ["bear" if role == "bull" else "bull"]
    with pytest.raises(ValidationError, match="seen_roles"):
        AnalystOutput.model_validate(data)


def test_bull_rebuttal_may_declare_seen_roles(example):
    data = example("bull")
    data["phase"] = "rebuttal"
    data["seen_roles"] = ["bear"]
    assert AnalystOutput.model_validate(data).seen_roles[0].value == "bear"


def test_role_cannot_list_itself_in_seen_roles(example):
    data = example("bull")
    data["phase"] = "rebuttal"
    data["seen_roles"] = ["bull"]
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(data)


def test_bull_cannot_be_bearish_and_bear_cannot_be_bullish(example):
    bull = example("bull")
    bull["stance"] = "bearish"
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(bull)
    bear = example("bear")
    bear["stance"] = "bullish"
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(bear)


def test_adjudicator_role_not_allowed_in_analyst_output(example):
    data = example("macro")
    data["role"] = "adjudicator"
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(data)


@pytest.mark.parametrize("field", ["arguments", "assumptions", "counter_evidence", "risks", "failure_conditions"])
def test_stance_requires_arguments_counter_evidence_risks_and_failure_conditions(field, example):
    data = example("technical")
    data[field] = []
    with pytest.raises(ValidationError, match=field):
        AnalystOutput.model_validate(data)


def test_insufficient_evidence_allows_empty_sections_but_caps_confidence(example):
    data = example("bull")
    data.update(
        stance="insufficient_evidence", confidence=0.3, arguments=[], assumptions=[],
        counter_evidence=[], risks=[], failure_conditions=[], price_levels=[],
        data_gaps=["快照缺少可支持看多的資料"],
    )
    assert AnalystOutput.model_validate(data).confidence == 0.3
    data["confidence"] = 0.8
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(data)


def test_confidence_must_be_between_0_and_1(example):
    data = example("macro")
    data["confidence"] = 1.5
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(data)


def test_price_level_requires_calculation_and_evidence(example):
    data = example("technical")
    data["price_levels"][0]["calculation"] = "x"
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(data)
    data = example("technical")
    data["price_levels"][0]["evidence_ids"] = []
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(data)


# ------------------------------------------------------------ 證據驗證


def test_unknown_evidence_id_is_rejected(example, snapshot):
    data = example("fundamental")
    data["arguments"][0]["evidence_ids"] = ["S99"]
    with pytest.raises(EvidenceValidationError, match="S99"):
        validate_against_snapshot(AnalystOutput.model_validate(data), snapshot)


def test_failed_data_cannot_be_cited(example, snapshot):
    data = example("macro")
    data["arguments"][0]["evidence_ids"] = ["S13"]  # S13 狀態為 error
    with pytest.raises(EvidenceValidationError, match="S13"):
        validate_against_snapshot(AnalystOutput.model_validate(data), snapshot)


def test_price_level_needs_a_numeric_snapshot_item(example, snapshot_data):
    # 把 S10 改成非數值字串，技術面的壓力價位就失去數值計算依據
    for item in snapshot_data["items"]:
        if item["id"] == "S10":
            item["value"] = "n/a"
    snapshot = ResearchSnapshot.model_validate(snapshot_data)
    with pytest.raises(EvidenceValidationError, match="數值"):
        validate_against_snapshot(AnalystOutput.model_validate(example("technical")), snapshot)


def test_symbol_and_snapshot_id_must_match(example, snapshot):
    data = example("macro")
    data["symbol"] = "0000"
    data["snapshot_id"] = "other"
    with pytest.raises(EvidenceValidationError) as info:
        validate_against_snapshot(AnalystOutput.model_validate(data), snapshot)
    assert len(info.value.problems) == 2


# ------------------------------------------------------------ AdjudicationOutput 規則


def directional(example, verdict="bullish_conditional"):
    data = example("adjudicator")
    data["verdict"] = verdict
    data["conditions_to_act"] = ["收盤價站上 108.0 且營收年增率維持 10% 以上"]
    data["invalidation_conditions"] = [
        {"description": "收盤價跌破 94.0 時失效", "metric": "close_price", "comparator": "<", "threshold": 94.0}
    ]
    return data


def test_directional_verdict_with_conditions_is_valid(example, snapshot):
    out = AdjudicationOutput.model_validate(directional(example))
    validate_against_snapshot(out, snapshot)


def test_directional_verdict_needs_conditions_invalidation_and_disagreements(example):
    for field in ("conditions_to_act", "invalidation_conditions", "disagreements"):
        data = directional(example)
        data[field] = []
        with pytest.raises(ValidationError):
            AdjudicationOutput.model_validate(data)


def test_adjudicator_must_review_bull_and_bear(example):
    data = example("adjudicator")
    data["inputs_reviewed"] = ["macro", "fundamental", "technical", "bull"]
    with pytest.raises(ValidationError, match="bull"):
        AdjudicationOutput.model_validate(data)


def test_watch_requires_triggers(example):
    data = example("adjudicator")
    data["watch_triggers"] = []
    with pytest.raises(ValidationError):
        AdjudicationOutput.model_validate(data)


def test_insufficient_evidence_has_no_scenarios_and_low_confidence(example):
    data = example("adjudicator")
    data["verdict"] = "insufficient_evidence"
    data["confidence"] = 0.3
    with pytest.raises(ValidationError, match="情境"):
        AdjudicationOutput.model_validate(data)
    data["scenarios"] = []
    assert AdjudicationOutput.model_validate(data).scenarios == []
    data["confidence"] = 0.7
    with pytest.raises(ValidationError):
        AdjudicationOutput.model_validate(data)


def test_scenarios_must_be_ordered(example):
    data = example("adjudicator")
    data["scenarios"][0]["price"] = 120.0  # conservative 高於 optimistic
    with pytest.raises(ValidationError, match="conservative"):
        AdjudicationOutput.model_validate(data)


def test_scenarios_must_have_all_three_labels(example):
    data = example("adjudicator")
    data["scenarios"] = data["scenarios"][:2]
    with pytest.raises(ValidationError):
        AdjudicationOutput.model_validate(data)


def test_scenario_probabilities_must_sum_to_one(example):
    data = example("adjudicator")
    for s, p in zip(data["scenarios"], (0.3, 0.3, 0.3)):
        s["probability"] = p
    with pytest.raises(ValidationError, match="probability"):
        AdjudicationOutput.model_validate(data)
    for s, p in zip(data["scenarios"], (0.3, 0.4, 0.3)):
        s["probability"] = p
    AdjudicationOutput.model_validate(data)
