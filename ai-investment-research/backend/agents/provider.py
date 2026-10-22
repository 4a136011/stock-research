"""可替換的 LLM provider adapter。

階段 A 只提供抽象介面與 MockProvider（供測試）。真實 provider 於階段 D 實作，
且啟用前需先確認用量上限（見 README）。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field


class ProviderError(Exception):
    """provider 呼叫失敗。呼叫端必須處理，不可以用虛構內容取代。"""


@dataclass(frozen=True)
class LLMRequest:
    system: str
    user: str
    tag: str  # 例如角色名稱，用於日誌與 mock 路由
    model: str | None = None
    max_tokens: int = 2000
    temperature: float = 0.2


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """送出請求並回傳文字。失敗時 raise ProviderError。"""


class MockProvider(LLMProvider):
    """依 tag 回傳預先指定的文字；沒有對應內容時報錯，絕不自行編造。"""

    name = "mock"

    def __init__(self, responses: Mapping[str, str] | None = None):
        self._responses = dict(responses or {})
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        text = self._responses.get(request.tag)
        if text is None:
            raise ProviderError(f"MockProvider 沒有 tag={request.tag!r} 的預設回應")
        return LLMResponse(text=text, model="mock")


PROVIDERS: dict[str, Callable[[], LLMProvider]] = {
    "mock": MockProvider,
}


def get_provider(name: str) -> LLMProvider:
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise ProviderError(
            f"未知的 LLM_PROVIDER={name!r}；可用：{', '.join(sorted(PROVIDERS))}。真實 provider 於階段 D 加入。"
        ) from None
