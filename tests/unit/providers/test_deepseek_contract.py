import base64
import json

import pytest

from alignspace.providers.deepseek import (
    DeepSeekPreferenceAnalysisProvider,
    ProviderAuthError,
    ProviderOutputError,
    ProviderRequestError,
    TransportResponse,
)
from alignspace.providers.factory import build_preference_provider
from alignspace.providers.preference import (
    AnalysisAsset,
    MockPreferenceAnalysisProvider,
    PreferenceAnalysisRequest,
)

VALID = {
    "entries": [
        {
            "sourceAssetId": "asset-1",
            "targetElement": "bed",
            "attentionDimensions": ["colour"],
            "candidates": [
                {
                    "dimension": "colour",
                    "certainty": "inferred",
                    "proposedValue": "warm grey",
                    "evidence": [
                        {
                            "sourceType": "image",
                            "sourceId": "asset-1",
                            "description": "Observed bed colour.",
                        }
                    ],
                }
            ],
        }
    ]
}


class StubTransport:
    def __init__(self, *responses: TransportResponse) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, *, headers, payload, timeout) -> TransportResponse:
        self.calls.append(
            {"url": url, "headers": headers, "payload": payload, "timeout": timeout}
        )
        return self.responses.pop(0)


def ok(content: object) -> TransportResponse:
    body = {"choices": [{"message": {"content": json.dumps(content)}}]}
    return TransportResponse(200, json.dumps(body))


def request() -> PreferenceAnalysisRequest:
    return PreferenceAnalysisRequest(
        assets=[
            AnalysisAsset(
                id="asset-1", media_type="image/png", sha256="aaa", data=b"image-bytes"
            )
        ],
        description="喜欢床的颜色",
        prompt_version="prompt-v1",
        schema_version="1.0.0",
    )


def test_sends_model_images_and_a_structured_output_request():
    transport = StubTransport(ok(VALID))
    provider = DeepSeekPreferenceAnalysisProvider(api_key="test-key", transport=transport)

    result = provider.analyze(request())

    call = transport.calls[0]
    assert call["payload"]["model"] == "deepseek-flash"
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["payload"]["response_format"]["type"] in {"json_object", "json_schema"}
    content = call["payload"]["messages"][-1]["content"]
    images = [part for part in content if part["type"] == "image_url"]
    assert images
    uri = images[0]["image_url"]["url"]
    assert uri.startswith("data:image/png;base64,")
    assert base64.b64encode(b"image-bytes").decode() in uri
    assert any(part["type"] == "text" and "床" in part["text"] for part in content)
    assert result.model == "deepseek-flash"


def test_retries_transient_failures_then_succeeds():
    transport = StubTransport(TransportResponse(429, "{}"), ok(VALID))
    provider = DeepSeekPreferenceAnalysisProvider(
        api_key="k", transport=transport, max_retries=2
    )
    provider.analyze(request())
    assert len(transport.calls) == 2


def test_terminal_failure_is_not_retried_and_never_leaks_the_key():
    transport = StubTransport(TransportResponse(401, "{}"))
    provider = DeepSeekPreferenceAnalysisProvider(api_key="super-secret", transport=transport)
    with pytest.raises(ProviderAuthError) as error:
        provider.analyze(request())
    assert len(transport.calls) == 1
    assert "super-secret" not in str(error.value)


def test_exhausted_retries_surface_a_retryable_error():
    transport = StubTransport(*[TransportResponse(503, "{}") for _ in range(3)])
    provider = DeepSeekPreferenceAnalysisProvider(
        api_key="k", transport=transport, max_retries=2
    )
    with pytest.raises(ProviderRequestError) as error:
        provider.analyze(request())
    assert error.value.retryable is True
    assert len(transport.calls) == 3


def test_invalid_structured_output_is_repaired_once_then_rejected():
    bad = ok({"entries": "not-a-list"})
    transport = StubTransport(bad, bad)
    provider = DeepSeekPreferenceAnalysisProvider(api_key="k", transport=transport)
    with pytest.raises(ProviderOutputError):
        provider.analyze(request())
    assert len(transport.calls) == 2


def test_factory_defaults_to_mock_and_never_silently_degrades():
    default = build_preference_provider({})
    assert isinstance(default, MockPreferenceAnalysisProvider)

    with pytest.raises(Exception) as missing:
        build_preference_provider({"ALIGNSPACE_VISION_MODE": "deepseek"})
    assert "not configured" in str(missing.value).lower()

    configured = build_preference_provider(
        {
            "ALIGNSPACE_VISION_MODE": "deepseek",
            "ALIGNSPACE_DEEPSEEK_API_KEY": "k",
            "ALIGNSPACE_DEEPSEEK_MODEL": "deepseek-v3",
        }
    )
    assert isinstance(configured, DeepSeekPreferenceAnalysisProvider)
    assert configured.model == "deepseek-v3"


def test_prompt_and_payload_enable_json_output_per_official_protocol():
    transport = StubTransport(ok(VALID))
    DeepSeekPreferenceAnalysisProvider(api_key="k", transport=transport).analyze(request())
    payload = transport.calls[0]["payload"]
    system = payload["messages"][0]["content"]
    assert "json" in system.lower()
    assert "entries" in system
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] > 0


@pytest.mark.parametrize("status", [400, 402, 422])
def test_invalid_parameters_and_balance_are_terminal(status):
    transport = StubTransport(TransportResponse(status, "{}"))
    provider = DeepSeekPreferenceAnalysisProvider(
        api_key="k", transport=transport, max_retries=2
    )
    with pytest.raises(ProviderRequestError) as error:
        provider.analyze(request())
    assert error.value.retryable is False
    assert len(transport.calls) == 1
