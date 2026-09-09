import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schemas/design-brief.schema.json").read_text())
EXAMPLE = json.loads((ROOT / "examples/project-haven.design-brief.json").read_text())


def test_attribute_contract_requires_target_element() -> None:
    required = SCHEMA["$defs"]["attribute"]["required"]
    assert "targetElement" in required


def test_conflict_contract_requires_control_fields() -> None:
    required = SCHEMA["$defs"]["conflict"]["required"]
    assert {"severity", "resolutionAttempts"}.issubset(required)


def test_demo_brief_validates_against_contract() -> None:
    errors = list(Draft202012Validator(SCHEMA).iter_errors(EXAMPLE))
    assert errors == []
