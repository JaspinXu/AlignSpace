"""Select the candidate preference analysis provider from the environment.

Selecting the real provider without credentials raises instead of falling back
to the deterministic mock, so a missing key can never be reported as a
successful analysis.
"""

import os
from collections.abc import Mapping

from alignspace.domain.preferences import ProviderMode
from alignspace.providers.deepseek import (
    DeepSeekPreferenceAnalysisProvider,
    ProviderNotConfigured,
)
from alignspace.providers.preference import (
    MockPreferenceAnalysisProvider,
    PreferenceAnalysisProvider,
)

MODE_ENV = "ALIGNSPACE_VISION_MODE"
API_KEY_ENV = "ALIGNSPACE_DEEPSEEK_API_KEY"
MODEL_ENV = "ALIGNSPACE_DEEPSEEK_MODEL"
BASE_URL_ENV = "ALIGNSPACE_DEEPSEEK_BASE_URL"


def build_preference_provider(
    env: Mapping[str, str] | None = None,
) -> PreferenceAnalysisProvider:
    values = os.environ if env is None else env
    mode = ProviderMode(values.get(MODE_ENV, ProviderMode.MOCK.value))
    if mode is ProviderMode.MOCK:
        return MockPreferenceAnalysisProvider()
    api_key = values.get(API_KEY_ENV)
    if not api_key or not api_key.strip():
        raise ProviderNotConfigured(
            "deepseek provider is not configured: set ALIGNSPACE_DEEPSEEK_API_KEY"
        )
    return DeepSeekPreferenceAnalysisProvider(
        api_key=api_key,
        model=values.get(MODEL_ENV) or DeepSeekPreferenceAnalysisProvider.DEFAULT_MODEL,
        base_url=values.get(BASE_URL_ENV)
        or DeepSeekPreferenceAnalysisProvider.DEFAULT_BASE_URL,
    )
