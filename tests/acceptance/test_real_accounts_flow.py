"""End-to-end acceptance with two genuine accounts and the public joins API.

Unlike tests/conftest.py's WorkflowDriver, this test never uses the test-only
identity override: the homeowner creates the project, the designer joins with a
one-time code, and every call carries a real Bearer token.
"""

import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from PIL import Image

from alignspace.auth.config import AuthConfig

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "a sufficiently long password"
SECRET = "real-accounts-acceptance-secret-long-enough"


@pytest.fixture
def api(tmp_path):
    from alignspace.main import create_app

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'real-accounts.db'}",
        checkpoint_path=str(tmp_path / "checkpoints.db"),
        auth_config=AuthConfig(secret=SECRET, secure_cookie=False),
    )
    with TestClient(app, headers=ORIGIN) as client:
        yield client


def register(api, email):
    response = api.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def auth(user):
    return {"Authorization": f"Bearer {user['accessToken']}"}


class TwoAccountDriver:
    def __init__(self, api, owner, designer, project_id):
        self.api = api
        self.owner = auth(owner)
        self.designer = auth(designer)
        self.project_id = project_id

    def _version(self, headers):
        response = self.api.get(f"/v1/projects/{self.project_id}", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()["stateVersion"]

    def write(self, method, path, key, data, *, headers, expected=200):
        response = self.api.request(
            method,
            path,
            headers=headers,
            json={
                "idempotencyKey": key,
                "expectedStateVersion": self._version(headers),
                "data": data,
            },
        )
        assert response.status_code == expected, response.text
        return response.json()

    def run(self):
        version = self._version(self.owner)
        for index in range(3):
            buffer = BytesIO()
            Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
            asset = self.api.post(
                f"/v1/projects/{self.project_id}/assets",
                headers=self.owner,
                data={"expectedStateVersion": str(version), "idempotencyKey": f"asset-{index}"},
                files={"file": (f"room-{index}.png", buffer.getvalue(), "image/png")},
            )
            assert asset.status_code == 201, asset.text
            version = asset.json()["stateVersion"]

        started = self.write(
            "POST",
            f"/v1/projects/{self.project_id}/analysis-runs",
            "analysis-1",
            {},
            headers=self.owner,
            expected=202,
        )
        broad = self.write(
            "POST",
            f"/v1/projects/{self.project_id}/questions/{started['pendingQuestion']['id']}/answer",
            "answer-broad",
            {"answer": "I also like the warm lighting"},
            headers=self.owner,
            expected=202,
        )
        for attribute in broad["projectState"]["attributes"]:
            self.write(
                "PATCH",
                f"/v1/projects/{self.project_id}/attributes/{attribute['id']}",
                f"confirm-{attribute['id']}",
                {"status": "confirmed", "value": attribute["value"]},
                headers=self.owner,
            )

        explicit = {
            "style": "warm modern",
            "layout": "clear conversational seating",
            "furniture": "compact rounded furniture",
            "mood": "calm and welcoming",
            "function": "conversation and reading",
        }
        for dimension, value in explicit.items():
            self.write(
                "PATCH",
                f"/v1/projects/{self.project_id}/attributes/manual-{dimension}",
                f"manual-{dimension}",
                {
                    "targetElement": "living_room",
                    "dimension": dimension,
                    "value": value,
                    "status": "confirmed",
                },
                headers=self.owner,
            )

        detail = self.api.get(
            f"/v1/projects/{self.project_id}/questions/next", headers=self.owner
        )
        assert detail.status_code == 200, detail.text
        tradeoff = self.write(
            "POST",
            f"/v1/projects/{self.project_id}/questions/{detail.json()['id']}/answer",
            "answer-detail",
            {"answer": "Warm ambient lighting around 2700K"},
            headers=self.owner,
            expected=202,
        )
        assert tradeoff["pendingQuestion"]["id"].startswith("question-conflict-")

        drafted = self.write(
            "POST",
            (
                f"/v1/projects/{self.project_id}/questions/"
                f"{tradeoff['pendingQuestion']['id']}/answer"
            ),
            "resolve-conflict",
            {"answer": "Use the lower-cost stone-effect finish."},
            headers=self.owner,
        )
        assert drafted["status"] == "awaiting_approval"

        latest = self.api.get(
            f"/v1/projects/{self.project_id}/briefs/latest", headers=self.owner
        ).json()

        self.write(
            "POST",
            f"/v1/projects/{self.project_id}/briefs/{latest['version']}/approvals",
            "approve-owner",
            {"contentHash": latest["contentHash"]},
            headers=self.owner,
        )
        second = self.write(
            "POST",
            f"/v1/projects/{self.project_id}/briefs/{latest['version']}/approvals",
            "approve-designer",
            {"contentHash": latest["contentHash"]},
            headers=self.designer,
        )
        assert second["status"] == "approved"
        assert len(second["projectState"]["approvals"]) == 2

        final = self.api.get(
            f"/v1/projects/{self.project_id}/briefs/latest", headers=self.owner
        ).json()
        schema = json.loads(
            (Path(__file__).resolve().parents[2] / "schemas/design-brief.schema.json").read_text()
        )
        return final, Draft202012Validator(schema).is_valid(final["payload"])


def test_two_real_accounts_reach_a_dual_approved_brief(api):
    owner = register(api, "owner@example.com")
    designer = register(api, "designer@example.com")

    created = api.post(
        "/v1/projects",
        headers=auth(owner),
        json={"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": True},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    issued = api.post(
        f"/v1/projects/{project_id}/join-code", headers=auth(owner)
    ).json()
    joined = api.post(
        "/v1/projects/join", headers=auth(designer), json={"code": issued["code"]}
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["role"] == "designer"

    driver = TwoAccountDriver(api, owner, designer, project_id)
    final, schema_valid = driver.run()

    assert final["version"] >= 1
    assert schema_valid is True
    assert {approval["role"] for approval in final["approvals"]} == {"homeowner", "designer"}
