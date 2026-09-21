import pytest

from alignspace.domain.preferences import CandidateDimension, Certainty, ProviderMode
from alignspace.providers.preference import (
    AnalysisAsset,
    MockPreferenceAnalysisProvider,
    PreferenceAnalysisRequest,
)


def asset(asset_id: str, digest: str = "aaa", data: bytes = b"image-bytes") -> AnalysisAsset:
    return AnalysisAsset(id=asset_id, media_type="image/png", sha256=digest, data=data)


def request(description: str, assets: list[AnalysisAsset] | None = None) -> PreferenceAnalysisRequest:
    return PreferenceAnalysisRequest(
        assets=assets or [asset("asset-1")],
        description=description,
        prompt_version="prompt-v1",
        schema_version="1.0.0",
    )


@pytest.fixture
def provider() -> MockPreferenceAnalysisProvider:
    return MockPreferenceAnalysisProvider()


def test_mock_output_is_deterministic(provider):
    first = provider.analyze(request("喜欢床的颜色和样式"))
    second = provider.analyze(request("喜欢床的颜色和样式"))
    assert first.model_dump() == second.model_dump()
    assert first.provider_mode == ProviderMode.MOCK
    assert first.model == MockPreferenceAnalysisProvider.MODEL


def test_mock_only_covers_mentioned_parts_and_dimensions(provider):
    result = provider.analyze(request("喜欢床的颜色和样式"))
    pairs = {
        (entry.target_element, candidate.dimension)
        for entry in result.entries
        for candidate in entry.candidates
    }
    assert pairs == {
        ("bed", CandidateDimension.COLOUR),
        ("bed", CandidateDimension.STYLE),
    }


def test_mock_does_not_default_to_liking_the_whole_image(provider):
    assert provider.analyze(request("这张图整体很好看")).entries == []


def test_mock_keeps_attention_separate_from_proposed_values(provider):
    result = provider.analyze(request("墙壁的颜色和样式"))
    entry = next(item for item in result.entries if item.target_element == "wall")
    assert set(entry.attention_dimensions) == {CandidateDimension.COLOUR, CandidateDimension.STYLE}
    assert all(candidate.proposed_value is not None for candidate in entry.candidates)


def test_mock_marks_uncertain_material_without_inventing_a_value(provider):
    result = provider.analyze(request("墙壁的材质"))
    materials = [
        candidate
        for entry in result.entries
        for candidate in entry.candidates
        if candidate.dimension == CandidateDimension.MATERIAL
    ]
    assert materials
    assert all(
        candidate.certainty == Certainty.UNCERTAIN and candidate.proposed_value is None
        for candidate in materials
    )


def test_mock_creates_one_entry_per_source_image_and_part(provider):
    result = provider.analyze(
        request("墙壁的颜色", assets=[asset("asset-1", "aaa"), asset("asset-2", "bbb")])
    )
    assert {
        (entry.source_asset_id, entry.target_element) for entry in result.entries
    } == {("asset-1", "wall"), ("asset-2", "wall")}
    for entry in result.entries:
        for candidate in entry.candidates:
            assert [item.source_id for item in candidate.evidence] == [entry.source_asset_id]


def test_mock_is_sensitive_to_image_content(provider):
    left = provider.analyze(request("地板的铺设方式", assets=[asset("asset-1", "aaa")]))
    right = provider.analyze(request("地板的铺设方式", assets=[asset("asset-1", "zzz")]))
    assert left.model_dump() != right.model_dump()
