import pytest
from pydantic import ValidationError

from alignspace.domain.preferences import (
    AnalysisRun,
    AnalysisStatus,
    CandidateDimension,
    CandidatePreference,
    CandidateStatus,
    Certainty,
    DesignEntry,
    EntryStatus,
    calculate_analysis_fingerprint,
)


def candidate(**overrides):
    base = {
        "id": "cand-1",
        "entry_id": "entry-1",
        "dimension": CandidateDimension.MATERIAL,
        "proposed_value": "microcement",
        "certainty": Certainty.INFERRED,
    }
    return CandidatePreference(**{**base, **overrides})


def test_uncertain_material_may_have_no_value():
    assert candidate(certainty=Certainty.UNCERTAIN, proposed_value=None).proposed_value is None


def test_inferred_candidate_requires_a_value():
    with pytest.raises(ValidationError):
        candidate(certainty=Certainty.INFERRED, proposed_value=None)
    with pytest.raises(ValidationError):
        candidate(certainty=Certainty.INFERRED, proposed_value="   ")


def test_confirmed_candidate_requires_confirmed_value():
    with pytest.raises(ValidationError):
        candidate(status=CandidateStatus.CONFIRMED)
    confirmed = candidate(status=CandidateStatus.CONFIRMED, confirmed_value="microcement")
    assert confirmed.confirmed_value == "microcement"
    # Confirming a preference is not a claim about the real material in the photo.
    assert confirmed.certainty == Certainty.INFERRED


def test_candidate_dimension_must_be_supported():
    with pytest.raises(ValidationError):
        candidate(dimension="texture")


def test_proposed_candidate_cannot_carry_a_confirmed_value_or_attribute():
    with pytest.raises(ValidationError):
        candidate(confirmed_value="microcement")
    with pytest.raises(ValidationError):
        candidate(attribute_id="pref-cand-1")


def test_design_entry_tracks_attention_separately_from_candidates():
    entry = DesignEntry(
        id="entry-1",
        analysis_run_id="run-1",
        source_asset_id="asset-1",
        target_element="wall",
        attention_dimensions=[CandidateDimension.COLOUR, CandidateDimension.MATERIAL],
    )
    assert entry.status == EntryStatus.OPEN
    assert entry.attention_dimensions == [
        CandidateDimension.COLOUR,
        CandidateDimension.MATERIAL,
    ]


def test_design_entry_rejects_unsupported_attention_dimension():
    with pytest.raises(ValidationError):
        DesignEntry(
            id="entry-1",
            analysis_run_id="run-1",
            source_asset_id="asset-1",
            target_element="wall",
            attention_dimensions=["texture"],
        )


def test_design_entry_status_vocabulary_is_bounded():
    with pytest.raises(ValidationError):
        DesignEntry(
            id="entry-1",
            analysis_run_id="run-1",
            source_asset_id="asset-1",
            target_element="wall",
            status="pending",
        )


def test_analysis_fingerprint_is_stable_and_input_sensitive():
    first = calculate_analysis_fingerprint(
        [("asset-1", "aaa"), ("asset-2", "bbb")], "喜欢床的颜色和样式", "prompt-v1"
    )
    assert first == calculate_analysis_fingerprint(
        [("asset-1", "aaa"), ("asset-2", "bbb")], "喜欢床的颜色和样式", "prompt-v1"
    )
    assert first != calculate_analysis_fingerprint(
        [("asset-1", "aaa"), ("asset-2", "ccc")], "喜欢床的颜色和样式", "prompt-v1"
    )
    assert first != calculate_analysis_fingerprint(
        [("asset-1", "aaa"), ("asset-2", "bbb")], "喜欢墙壁的材质", "prompt-v1"
    )
    assert first != calculate_analysis_fingerprint(
        [("asset-1", "aaa"), ("asset-2", "bbb")], "喜欢床的颜色和样式", "prompt-v2"
    )


def test_analysis_fingerprint_ignores_asset_order_but_not_membership():
    assert calculate_analysis_fingerprint(
        [("asset-2", "bbb"), ("asset-1", "aaa")], "描述", "prompt-v1"
    ) == calculate_analysis_fingerprint(
        [("asset-1", "aaa"), ("asset-2", "bbb")], "描述", "prompt-v1"
    )


def test_analysis_run_requires_provider_traceability():
    run = AnalysisRun(
        id="run-1",
        status=AnalysisStatus.COMPLETED,
        requested_by="homeowner-1",
        description="喜欢床的颜色和样式",
        input_assets=[{"assetId": "asset-1", "sha256": "aaa"}],
        input_fingerprint="fingerprint",
        provider_mode="mock",
        model="mock-deterministic",
        prompt_version="prompt-v1",
        schema_version="1.0.0",
    )
    assert run.third_party_consent is False
    with pytest.raises(ValidationError):
        AnalysisRun(
            id="run-2",
            status=AnalysisStatus.COMPLETED,
            requested_by="homeowner-1",
            description="x",
            input_assets=[{"assetId": "asset-1", "sha256": "aaa"}],
            input_fingerprint="fingerprint",
            provider_mode="klingon",
            model="m",
            prompt_version="p",
            schema_version="1.0.0",
        )
