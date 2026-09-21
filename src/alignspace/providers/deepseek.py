"""DeepSeek chat-completions adapter for candidate preference analysis.

This adapter is implemented but **not called in this round**. Real use requires
the user to configure ``ALIGNSPACE_DEEPSEEK_API_KEY`` and is pending acceptance;
see ``docs/references/deepseek.md`` for the protocol assumptions that must be
re-verified against the official documentation before enabling it.

Local write idempotency says nothing about external billing: retrying a request
here can be charged more than once, and the API deliberately distinguishes
retryable transport failures from a locally idempotent business write.
"""

import base64
import json
import urllib.error
import urllib.request
from typing import NamedTuple, Protocol

from pydantic import ValidationError

from alignspace.domain.preferences import ProviderMode
from alignspace.providers.preference import (
    PreferenceAnalysisRequest,
    PreferenceAnalysisResult,
)

SYSTEM_PROMPT = (
    "You extract candidate design preferences from reference images.\n"
    "Separate three facts and never conflate them:\n"
    "1. attentionDimensions: the dimensions the homeowner's description mentions.\n"
    "2. candidates: what you observe or infer, with certainty 'inferred' when you "
    "can read a value and 'uncertain' with a null value when you cannot.\n"
    "3. Do not decide what the homeowner wants; confirmation happens elsewhere.\n"
    "Only cover parts and dimensions the description mentions. Never assume the "
    "homeowner likes an entire image. Cite the source image id in evidence.\n"
    "Reply with json only, matching this example shape exactly:\n"
    '{"entries":[{"sourceAssetId":"asset-1","targetElement":"bed",'
    '"attentionDimensions":["colour"],"candidates":[{"dimension":"colour",'
    '"certainty":"inferred","proposedValue":"warm grey","evidence":'
    '[{"sourceType":"image","sourceId":"asset-1","description":"..."}]}]}]}'
)


class ProviderError(RuntimeError):
    """Base class for provider failures."""


class ProviderNotConfigured(ProviderError):
    """Raised when a real provider is selected without credentials."""


class ProviderAuthError(ProviderError):
    """Raised when the provider rejects our credentials (never retryable)."""


class ProviderOutputError(ProviderError):
    """Raised when provider output stays invalid after the repair attempt."""


class ProviderRequestError(ProviderError):
    """Raised for transport/HTTP failures, tagged with retryability."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class TransportResponse(NamedTuple):
    status_code: int
    text: str


class Transport(Protocol):
    def post(
        self, url: str, *, headers: dict[str, str], payload: dict, timeout: float
    ) -> TransportResponse: ...


class UrllibTransport:
    """Dependency-free default transport (no httpx runtime requirement)."""

    def post(
        self, url: str, *, headers: dict[str, str], payload: dict, timeout: float
    ) -> TransportResponse:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return TransportResponse(response.status, response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return TransportResponse(error.code, error.read().decode("utf-8"))


class DeepSeekPreferenceAnalysisProvider:
    DEFAULT_MODEL = "deepseek-flash"
    DEFAULT_BASE_URL = "https://api.deepseek.com"
    provider_mode = ProviderMode.DEEPSEEK
    # Official error codes: 400 invalid format, 401 auth, 402 insufficient balance,
    # 422 invalid parameters are terminal; 429/5xx are retryable.
    _TERMINAL_STATUSES = frozenset({400, 401, 402, 403, 422})

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        transport: Transport | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ProviderNotConfigured(
                "deepseek provider is not configured: set ALIGNSPACE_DEEPSEEK_API_KEY"
            )
        self.model = model
        self._api_key = api_key
        self._base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._transport = transport or UrllibTransport()
        self._timeout = timeout
        self._max_retries = max(0, max_retries)

    @property
    def endpoint(self) -> str:
        return f"{self._base_url}/chat/completions"

    def analyze(self, request: PreferenceAnalysisRequest) -> PreferenceAnalysisResult:
        messages = self._messages(request)
        for attempt in range(self._max_retries + 1):
            response = self._transport.post(
                self.endpoint,
                headers=self._headers(),
                payload=self._payload(messages),
                timeout=self._timeout,
            )
            if response.status_code == 200:
                return self._parse(request, messages, response)
            if response.status_code in self._TERMINAL_STATUSES:
                if response.status_code in {401, 403}:
                    raise ProviderAuthError(
                        f"deepseek rejected the credentials (status {response.status_code})"
                    )
                if response.status_code == 402:
                    raise ProviderRequestError(
                        "deepseek account has insufficient balance (status 402)",
                        retryable=False,
                    )
                raise ProviderRequestError(
                    f"deepseek rejected the request (status {response.status_code})",
                    retryable=False,
                )
            if attempt >= self._max_retries:
                raise ProviderRequestError(
                    f"deepseek request failed (status {response.status_code})",
                    retryable=response.status_code == 429 or response.status_code >= 500,
                )
        raise AssertionError("retry loop must return or raise")

    def _parse(
        self,
        request: PreferenceAnalysisRequest,
        messages: list[dict],
        response: TransportResponse,
    ) -> PreferenceAnalysisResult:
        del request
        try:
            return self._validate(response)
        except (ValidationError, ProviderOutputError) as first_error:
            repair = self._transport.post(
                self.endpoint,
                headers=self._headers(),
                payload=self._payload(
                    [*messages, self._repair_message(first_error)]
                ),
                timeout=self._timeout,
            )
            if repair.status_code != 200:
                raise ProviderRequestError(
                    f"deepseek repair attempt failed (status {repair.status_code})",
                    retryable=False,
                )
            try:
                return self._validate(repair)
            except (ValidationError, ProviderOutputError) as second_error:
                raise ProviderOutputError(
                    "deepseek output invalid after two attempts"
                ) from second_error

    def _validate(self, response: TransportResponse) -> PreferenceAnalysisResult:
        content = self._content(response)
        try:
            data = json.loads(content)
        except ValueError as error:
            raise ProviderOutputError("deepseek content was not JSON") from error
        if not isinstance(data, dict):
            raise ProviderOutputError("deepseek content was not a JSON object")
        entries = data.get("entries", [])
        return PreferenceAnalysisResult.model_validate(
            {
                "entries": entries,
                "model": self.model,
                "provider_mode": ProviderMode.DEEPSEEK.value,
            }
        )

    @staticmethod
    def _content(response: TransportResponse) -> str:
        try:
            envelope = json.loads(response.text)
            content = envelope["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderOutputError("deepseek response was not a chat completion") from error
        if not isinstance(content, str):
            raise ProviderOutputError("deepseek message content was not text")
        return content

    def _messages(self, request: PreferenceAnalysisRequest) -> list[dict]:
        parts: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"{request.description}\n\n"
                    f"prompt_version={request.prompt_version} "
                    f"schema_version={request.schema_version}"
                ),
            }
        ]
        for asset in request.assets:
            encoded = base64.b64encode(asset.data).decode("ascii")
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{asset.media_type};base64,{encoded}"},
                }
            )
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": parts},
        ]

    def _repair_message(self, error: Exception) -> dict:
        return {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Your previous answer was invalid "
                        f"({type(error).__name__}). Return a JSON object with "
                        'an "entries" array matching the agreed schema.'
                    ),
                }
            ],
        }

    def _payload(self, messages: list[dict]) -> dict:
        # JSON output per the official guide: response_format json_object, the word
        # "json" plus a format example in the prompt, and a bounded max_tokens so a
        # long answer cannot be truncated into invalid JSON.
        return {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 4096,
            "stream": False,
        }

    def _headers(self) -> dict[str, str]:
        # The key is only ever sent to the provider; it must not be logged or echoed.
        return {"Authorization": f"Bearer {self._api_key}"}
