"""六個角色共用的輸出 schema，以及研究快照模型。

設計重點：
  * 所有模型 extra="forbid"：模型多給欄位就視為驗證失敗，不靜默接受。
  * 證據只以「快照項目 id」引用；validate_against_snapshot 驗證 id 存在、狀態可用、
    價位至少引用一個數值項目。
  * bull / bear 的 initial 階段 seen_roles 必須為空（獨立分析），資料庫層亦有 CHECK。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DISCLAIMER = "本內容為研究輔助資訊，不構成投資建議；價位皆來自快照資料與所列計算，請自行查證後決策。"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Role(str, Enum):
    macro = "macro"
    fundamental = "fundamental"
    technical = "technical"
    bull = "bull"
    bear = "bear"
    adjudicator = "adjudicator"


ANALYST_ROLES = (Role.macro, Role.fundamental, Role.technical, Role.bull, Role.bear)


class Phase(str, Enum):
    initial = "initial"
    rebuttal = "rebuttal"


class Stance(str, Enum):
    bullish = "bullish"
    bearish = "bearish"
    neutral = "neutral"
    insufficient_evidence = "insufficient_evidence"


class Verdict(str, Enum):
    bullish_conditional = "bullish_conditional"
    bearish_conditional = "bearish_conditional"
    watch = "watch"
    insufficient_evidence = "insufficient_evidence"


DIRECTIONAL_VERDICTS = (Verdict.bullish_conditional, Verdict.bearish_conditional)


class DataStatus(str, Enum):
    ok = "ok"
    stale = "stale"
    partial = "partial"
    error = "error"
    missing = "missing"


UNUSABLE_STATUSES = (DataStatus.error, DataStatus.missing)


class Level(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Category(str, Enum):
    fundamental = "fundamental"
    valuation = "valuation"
    technical = "technical"
    macro = "macro"
    catalyst = "catalyst"
    scenario = "scenario"
    other = "other"


class PriceKind(str, Enum):
    support = "support"
    resistance = "resistance"
    target = "target"
    entry_zone = "entry_zone"
    stop = "stop"
    fair_value = "fair_value"


class ScenarioLabel(str, Enum):
    conservative = "conservative"
    neutral = "neutral"
    optimistic = "optimistic"


Comparator = Literal[">", "<", ">=", "<=", "=="]


# ---------------------------------------------------------------- 研究快照


class SnapshotItem(StrictModel):
    id: str = Field(pattern=r"^S\d+$")
    field: str = Field(min_length=1)
    value: float | str | None = None
    unit: str | None = None
    source: str = Field(min_length=1)
    source_url: str | None = None
    as_of: datetime | None = None
    fetched_at: datetime
    status: DataStatus

    @model_validator(mode="after")
    def _value_matches_status(self) -> "SnapshotItem":
        has_value = self.value is not None
        if self.status in UNUSABLE_STATUSES and has_value:
            raise ValueError(f"{self.id}: status={self.status.value} 的項目不可帶數值（不得填入替代資料）")
        if self.status not in UNUSABLE_STATUSES and not has_value:
            raise ValueError(f"{self.id}: status={self.status.value} 的項目必須有數值")
        return self

    @property
    def is_numeric(self) -> bool:
        return isinstance(self.value, (int, float)) and not isinstance(self.value, bool)


class ResearchSnapshot(StrictModel):
    snapshot_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    market: Literal["TW", "US", "MACRO"]
    created_at: datetime
    is_synthetic: bool = False
    items: list[SnapshotItem]

    @model_validator(mode="after")
    def _unique_ids(self) -> "ResearchSnapshot":
        ids = [i.id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("快照項目 id 不可重複")
        return self

    def get(self, item_id: str) -> SnapshotItem | None:
        return next((i for i in self.items if i.id == item_id), None)


# ---------------------------------------------------------------- 共用區塊


class Argument(StrictModel):
    claim: str = Field(min_length=5)
    category: Category = Category.other
    strength: Level = Level.medium
    evidence_ids: list[str] = Field(min_length=1)


class Risk(StrictModel):
    description: str = Field(min_length=5)
    severity: Level
    evidence_ids: list[str] = []


class FailureCondition(StrictModel):
    description: str = Field(min_length=5)
    metric: str = Field(min_length=1)
    comparator: Comparator
    threshold: float
    evidence_ids: list[str] = []


class PriceLevel(StrictModel):
    label: str = Field(min_length=1)
    kind: PriceKind
    price: float = Field(gt=0)
    calculation: str = Field(min_length=10)
    evidence_ids: list[str] = Field(min_length=1)


# ---------------------------------------------------------------- 分析師輸出


class AnalystOutput(StrictModel):
    """macro / fundamental / technical / bull / bear 共用。"""

    role: Role
    phase: Phase = Phase.initial
    seen_roles: list[Role] = []
    symbol: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    stance: Stance
    confidence: float = Field(ge=0, le=1)
    confidence_rationale: str = Field(min_length=5)
    thesis: str = Field(min_length=10)
    arguments: list[Argument] = []
    assumptions: list[str] = []
    counter_evidence: list[Argument] = []
    risks: list[Risk] = []
    failure_conditions: list[FailureCondition] = []
    price_levels: list[PriceLevel] = []
    data_gaps: list[str] = []

    @model_validator(mode="after")
    def _check_rules(self) -> "AnalystOutput":
        if self.role == Role.adjudicator:
            raise ValueError("adjudicator 請使用 AdjudicationOutput")
        if self.role in (Role.bull, Role.bear) and self.phase == Phase.initial and self.seen_roles:
            raise ValueError("bull/bear 初始分析不得看過任何角色的輸出（seen_roles 必須為空）")
        if self.role in self.seen_roles:
            raise ValueError("seen_roles 不可包含自己")
        if self.role == Role.bull and self.stance not in (Stance.bullish, Stance.insufficient_evidence):
            raise ValueError("bull 的 stance 只能是 bullish 或 insufficient_evidence")
        if self.role == Role.bear and self.stance not in (Stance.bearish, Stance.insufficient_evidence):
            raise ValueError("bear 的 stance 只能是 bearish 或 insufficient_evidence")

        if self.stance == Stance.insufficient_evidence:
            if self.confidence > 0.4:
                raise ValueError("insufficient_evidence 時 confidence 不得高於 0.4")
        else:
            required = {
                "arguments": self.arguments,
                "assumptions": self.assumptions,
                "counter_evidence": self.counter_evidence,
                "risks": self.risks,
                "failure_conditions": self.failure_conditions,
            }
            empty = [name for name, value in required.items() if not value]
            if empty:
                raise ValueError(f"有明確立場時必須提供：{', '.join(empty)}")
        return self


# ---------------------------------------------------------------- 裁決輸出


class Disagreement(StrictModel):
    topic: str = Field(min_length=3)
    bull_position: str = Field(min_length=3)
    bear_position: str = Field(min_length=3)
    resolution: str = Field(min_length=5)
    resolved: bool
    evidence_ids: list[str] = Field(min_length=1)


class RejectedClaim(StrictModel):
    role: Role
    claim: str = Field(min_length=3)
    reason: str = Field(min_length=5)


class Scenario(StrictModel):
    label: ScenarioLabel
    price: float = Field(gt=0)
    calculation: str = Field(min_length=10)
    evidence_ids: list[str] = Field(min_length=1)
    probability: float | None = Field(default=None, ge=0, le=1)


class AdjudicationOutput(StrictModel):
    role: Literal["adjudicator"] = "adjudicator"
    symbol: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    confidence_rationale: str = Field(min_length=5)
    summary: str = Field(min_length=10)
    decision_rationale: str = Field(min_length=20)
    inputs_reviewed: list[Role]
    disagreements: list[Disagreement] = []
    rejected_claims: list[RejectedClaim] = []
    scenarios: list[Scenario] = []
    conditions_to_act: list[str] = []
    invalidation_conditions: list[FailureCondition] = []
    watch_triggers: list[str] = []
    data_gaps: list[str] = []
    disclaimer: str = DISCLAIMER

    @model_validator(mode="after")
    def _check_rules(self) -> "AdjudicationOutput":
        if not {Role.bull, Role.bear} <= set(self.inputs_reviewed):
            raise ValueError("裁決必須審閱 bull 與 bear 兩方的輸出")

        labels = [s.label for s in self.scenarios]
        if self.scenarios:
            if sorted(l.value for l in labels) != sorted(l.value for l in ScenarioLabel):
                raise ValueError("scenarios 必須剛好包含 conservative / neutral / optimistic 各一個")
            price = {s.label: s.price for s in self.scenarios}
            if not (
                price[ScenarioLabel.conservative]
                <= price[ScenarioLabel.neutral]
                <= price[ScenarioLabel.optimistic]
            ):
                raise ValueError("情境價位須滿足 conservative <= neutral <= optimistic")
            probs = [s.probability for s in self.scenarios]
            if any(p is not None for p in probs):
                if any(p is None for p in probs) or abs(sum(probs) - 1) > 0.01:
                    raise ValueError("probability 若提供，三個情境都要有且總和為 1")

        if self.verdict == Verdict.insufficient_evidence:
            if self.confidence > 0.4:
                raise ValueError("insufficient_evidence 時 confidence 不得高於 0.4")
            if not self.data_gaps:
                raise ValueError("insufficient_evidence 必須列出 data_gaps")
            if self.scenarios:
                raise ValueError("證據不足時不得給出情境價位")
        elif self.verdict == Verdict.watch:
            if not self.watch_triggers:
                raise ValueError("watch 必須提供 watch_triggers（何時重新評估）")
        else:
            missing = []
            if len(self.scenarios) != 3:
                missing.append("scenarios(3)")
            if not self.conditions_to_act:
                missing.append("conditions_to_act")
            if not self.invalidation_conditions:
                missing.append("invalidation_conditions")
            if not self.disagreements:
                missing.append("disagreements")
            if missing:
                raise ValueError(f"方向性結論必須提供：{', '.join(missing)}")
        return self


# ---------------------------------------------------------------- 快照驗證

EVIDENCE_FIELDS = (
    "arguments",
    "counter_evidence",
    "risks",
    "failure_conditions",
    "price_levels",
    "disagreements",
    "scenarios",
    "invalidation_conditions",
)
NUMERIC_EVIDENCE_FIELDS = ("price_levels", "scenarios")


class EvidenceValidationError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def validate_against_snapshot(
    output: AnalystOutput | AdjudicationOutput, snapshot: ResearchSnapshot
) -> None:
    """驗證輸出引用的證據都真實存在於快照且可用；任何問題一次列出。"""
    problems: list[str] = []
    if output.symbol != snapshot.symbol:
        problems.append(f"symbol 不一致：輸出 {output.symbol} / 快照 {snapshot.symbol}")
    if output.snapshot_id != snapshot.snapshot_id:
        problems.append(f"snapshot_id 不一致：輸出 {output.snapshot_id} / 快照 {snapshot.snapshot_id}")

    for name in EVIDENCE_FIELDS:
        for index, obj in enumerate(getattr(output, name, [])):
            where = f"{name}[{index}]"
            for eid in obj.evidence_ids:
                item = snapshot.get(eid)
                if item is None:
                    problems.append(f"{where} 引用不存在的快照項目 {eid}")
                elif item.status in UNUSABLE_STATUSES:
                    problems.append(f"{where} 引用狀態為 {item.status.value} 的項目 {eid}")
            if name in NUMERIC_EVIDENCE_FIELDS:
                numeric = [
                    snapshot.get(e) for e in obj.evidence_ids if snapshot.get(e) is not None
                ]
                if not any(i.is_numeric for i in numeric):
                    problems.append(f"{where} 價位至少需引用一個數值型快照項目作為計算依據")

    if problems:
        raise EvidenceValidationError(problems)


def snapshot_to_json(snapshot: ResearchSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(mode="json")
