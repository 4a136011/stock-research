import pytest

from backend.agents.prompt_loader import (
    REQUIRED_HEADINGS,
    PROMPTS_DIR,
    build_system_prompt,
    prompt_version,
    validate_prompt_files,
)
from backend.agents.schemas import Role

ALL_ROLES = list(Role)


def read(role: Role) -> str:
    return (PROMPTS_DIR / f"{role.value}.md").read_text(encoding="utf-8")


def test_prompt_files_are_complete():
    assert validate_prompt_files() == []


@pytest.mark.parametrize("role", ALL_ROLES)
def test_each_role_has_required_sections(role):
    text = read(role)
    for heading in REQUIRED_HEADINGS:
        assert heading in text, f"{role.value}.md 缺少 {heading}"


@pytest.mark.parametrize("role", ALL_ROLES)
def test_system_prompt_contains_shared_rules_and_schema(role):
    prompt = build_system_prompt(role)
    assert "共用規則" in prompt
    assert "evidence_ids" in prompt
    assert "## JSON Schema" in prompt
    assert ("AdjudicationOutput" if role == Role.adjudicator else "AnalystOutput") in prompt


@pytest.mark.parametrize("role", [Role.fundamental, Role.technical, Role.macro])
def test_professional_roles_do_not_presuppose_a_stance(role):
    assert "不預設立場" in read(role)


@pytest.mark.parametrize("role", [Role.bull, Role.bear])
def test_bull_bear_are_independent_in_initial_phase(role):
    text = read(role)
    assert "獨立" in text
    assert "seen_roles" in text
    assert "不會也不得看到" in text


def test_adjudicator_forbids_majority_vote_and_forced_calls():
    text = read(Role.adjudicator)
    assert "不可用多數決" in text
    assert "觀望" in text
    assert "強行推薦" in text


def test_shared_rules_forbid_untraceable_prices():
    shared = (PROMPTS_DIR / "_shared.md").read_text(encoding="utf-8")
    assert "calculation" in shared
    assert "不得使用快照以外" in shared


def test_prompt_version_is_stable_and_role_specific():
    assert prompt_version(Role.bull) == prompt_version(Role.bull)
    assert len({prompt_version(r) for r in ALL_ROLES}) == len(ALL_ROLES)
    assert len(prompt_version(Role.bull)) == 12
