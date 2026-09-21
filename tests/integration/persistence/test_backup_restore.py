"""Offline backup and restore: build real data, stop the app, back up, restore
into a new directory, and continue the workflow from the restored data."""

import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from alignspace.auth.config import AuthConfig

REPO = Path(__file__).resolve().parents[3]
ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "a sufficiently long password"
SECRET = "trial-backup-secret-that-is-long-enough"


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / script), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def _image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
    return buffer.getvalue()


class App:
    def __init__(self, database: Path, checkpoint: Path, assets: Path):
        self.database = database
        self.checkpoint = checkpoint
        self.assets = assets
        self.client: TestClient | None = None

    def start(self, monkeypatch) -> TestClient:
        monkeypatch.setenv("ALIGNSPACE_ASSET_DIR", str(self.assets))
        from alignspace.main import create_app

        app = create_app(
            database_url=f"sqlite:///{self.database}",
            checkpoint_path=str(self.checkpoint),
            auth_config=AuthConfig(secret=SECRET, secure_cookie=False),
        )
        self.client = TestClient(app, headers=ORIGIN)
        self.client.__enter__()
        return self.client

    def stop(self) -> None:
        if self.client is not None:
            self.client.__exit__(None, None, None)
            self.client = None


def _register(client, email):
    response = client.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def _login(client, email):
    response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _auth(user):
    return {"Authorization": f"Bearer {user['accessToken']}"}


def _version(client, project_id, user):
    return client.get(f"/v1/projects/{project_id}", headers=_auth(user)).json()["stateVersion"]


def _write(client, method, path, project_id, user, key, data, expected=(200, 202)):
    response = client.request(
        method,
        path,
        headers=_auth(user),
        json={
            "idempotencyKey": key,
            "expectedStateVersion": _version(client, project_id, user),
            "data": data,
        },
    )
    assert response.status_code in expected, response.text
    return response.json()


def _seed_project(client):
    owner = _register(client, "owner@example.com")
    designer = _register(client, "designer@example.com")
    project = client.post(
        "/v1/projects",
        headers=_auth(owner),
        json={"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": True},
    ).json()
    project_id = project["id"]
    code = client.post(f"/v1/projects/{project_id}/join-code", headers=_auth(owner)).json()["code"]
    assert client.post("/v1/projects/join", headers=_auth(designer), json={"code": code}).status_code == 200

    version = 0
    assets = []
    for index in range(3):
        upload = client.post(
            f"/v1/projects/{project_id}/assets",
            headers=_auth(owner),
            data={"expectedStateVersion": str(version), "idempotencyKey": f"asset-{index}"},
            files={"file": (f"room-{index}.png", _image_bytes(), "image/png")},
        )
        assert upload.status_code == 201, upload.text
        version = upload.json()["stateVersion"]
        assets.append(upload.json()["id"])

    started = _write(
        client, "POST", f"/v1/projects/{project_id}/analysis-runs",
        project_id, owner, "analysis-1", {}, expected=(202,),
    )
    parts = [
        {"assetId": option["assetId"], "targetElement": option["targetElement"]}
        for option in started["pendingQuestion"]["options"]
    ]
    broad = _write(
        client, "POST",
        f"/v1/projects/{project_id}/questions/{started['pendingQuestion']['id']}/answer",
        project_id, owner, "answer-broad", {"parts": parts}, expected=(202,),
    )
    response = broad
    for _ in range(12):
        pending = response.get("pendingQuestion")
        if not pending or pending.get("kind") != "detail":
            break
        selection = [
            {"attributeId": option["attributeId"], "decision": "confirmed", "value": option["value"]}
            for option in pending["options"]
        ]
        response = _write(
            client, "POST",
            f"/v1/projects/{project_id}/questions/{pending['id']}/answer",
            project_id, owner, f"detail-{pending['id']}", {"selection": selection}, expected=(202,),
        )
    for dimension, value in {
        "style": "warm modern", "layout": "clear seating", "furniture": "compact",
        "mood": "calm", "function": "reading",
    }.items():
        _write(
            client, "PATCH", f"/v1/projects/{project_id}/attributes/manual-{dimension}",
            project_id, owner, f"manual-{dimension}",
            {"targetElement": "living_room", "dimension": dimension, "value": value, "status": "confirmed"},
        )
    _write(
        client, "POST", f"/v1/projects/{project_id}/constraints",
        project_id, designer, "constraint-1",
        {"category": "budget", "statement": "预算档位已确认", "severity": "advisory", "appliesTo": "living_room"},
    )
    reviewed = _write(
        client, "POST", f"/v1/projects/{project_id}/designer-reviews",
        project_id, designer, "review-1", {"note": "ok"},
    )
    assert reviewed["status"] == "awaiting_approval", reviewed["status"]
    brief = client.get(f"/v1/projects/{project_id}/briefs/latest", headers=_auth(owner)).json()
    return owner, designer, project_id, assets, brief


def test_offline_backup_restore_and_resume(tmp_path, monkeypatch):
    live = App(tmp_path / "live" / "alignspace.db", tmp_path / "live" / "checkpoints.db", tmp_path / "live" / "assets")
    live.database.parent.mkdir(parents=True)
    client = live.start(monkeypatch)
    owner, designer, project_id, assets, brief = _seed_project(client)
    live.stop()

    backup_dir = tmp_path / "backup"
    result = _run(
        "backup_local.py",
        "--database", str(live.database),
        "--checkpoint", str(live.checkpoint),
        "--assets", str(live.assets),
        "--output", str(backup_dir),
        "--confirm-stopped",
    )
    assert result.returncode == 0, result.stderr
    assert (backup_dir / "database.sqlite3").is_file()
    assert (backup_dir / "checkpoints.sqlite3").is_file()
    assert (backup_dir / "assets").is_dir()
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    assert manifest["formatVersion"] == 1
    assert manifest["migrationVersion"] == 6
    assert str(tmp_path) not in json.dumps(manifest)
    assert {entry["path"] for entry in manifest["files"]} >= {
        "database.sqlite3", "checkpoints.sqlite3"
    }
    assert any(entry["path"].startswith("assets/") for entry in manifest["files"])

    restored = tmp_path / "restored"
    result = _run("restore_local.py", "--backup", str(backup_dir), "--destination", str(restored))
    assert result.returncode == 0, result.stderr
    assert str(restored / "database.sqlite3") in result.stdout
    assert str(restored / "assets") in result.stdout

    resumed = App(restored / "database.sqlite3", restored / "checkpoints.sqlite3", restored / "assets")
    client = resumed.start(monkeypatch)
    owner = _login(client, "owner@example.com")
    designer = _login(client, "designer@example.com")

    project = client.get(f"/v1/projects/{project_id}", headers=_auth(designer))
    assert project.status_code == 200
    assert sorted(item["id"] for item in project.json()["assets"]) == sorted(assets)
    content = client.get(
        f"/v1/projects/{project_id}/assets/{assets[0]}/content", headers=_auth(owner)
    )
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/png")

    state = client.get(f"/v1/projects/{project_id}/state", headers=_auth(owner)).json()["projectState"]
    assert len(state["briefVersions"]) == 1
    assert state["approvals"] == []
    restored_brief = client.get(
        f"/v1/projects/{project_id}/briefs/latest", headers=_auth(owner)
    ).json()
    assert restored_brief["version"] == brief["version"]
    assert restored_brief["contentHash"] == brief["contentHash"]

    first = _write(
        client, "POST", f"/v1/projects/{project_id}/briefs/{brief['version']}/approvals",
        project_id, owner, "approve-owner", {"contentHash": brief["contentHash"]},
    )
    assert first["status"] == "awaiting_approval"
    second = _write(
        client, "POST", f"/v1/projects/{project_id}/briefs/{brief['version']}/approvals",
        project_id, designer, "approve-designer", {"contentHash": brief["contentHash"]},
    )
    assert second["status"] == "approved"
    resumed.stop()


def test_backup_validates_arguments(tmp_path, monkeypatch):
    live = App(tmp_path / "live" / "db.sqlite3", tmp_path / "live" / "cp.sqlite3", tmp_path / "live" / "assets")
    live.database.parent.mkdir(parents=True)
    client = live.start(monkeypatch)
    _register(client, "owner@example.com")
    live.stop()

    base = [
        "backup_local.py",
        "--database", str(live.database),
        "--checkpoint", str(live.checkpoint),
        "--assets", str(live.assets),
    ]
    # Without --confirm-stopped.
    assert _run(*base, "--output", str(tmp_path / "out1")).returncode == 1
    assert not (tmp_path / "out1").exists()
    # Existing output.
    existing = tmp_path / "out2"
    existing.mkdir()
    assert _run(*base, "--output", str(existing), "--confirm-stopped").returncode == 1
    # Output inside the asset directory.
    assert _run(
        *base, "--output", str(live.assets / "nested"), "--confirm-stopped"
    ).returncode == 1
    # Missing source.
    assert _run(
        "backup_local.py",
        "--database", str(tmp_path / "missing.db"),
        "--checkpoint", str(live.checkpoint),
        "--assets", str(live.assets),
        "--output", str(tmp_path / "out3"),
        "--confirm-stopped",
    ).returncode == 1
    assert not (tmp_path / "out3").exists()


def test_backup_and_restore_reject_corruption(tmp_path, monkeypatch):
    live = App(tmp_path / "live" / "db.sqlite3", tmp_path / "live" / "cp.sqlite3", tmp_path / "live" / "assets")
    live.database.parent.mkdir(parents=True)
    client = live.start(monkeypatch)
    owner = _register(client, "owner@example.com")
    project = client.post(
        "/v1/projects", headers=_auth(owner),
        json={"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": True},
    ).json()
    upload = client.post(
        f"/v1/projects/{project['id']}/assets", headers=_auth(owner),
        data={"expectedStateVersion": "0", "idempotencyKey": "a"},
        files={"file": ("room.png", _image_bytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    live.stop()
    backup_dir = tmp_path / "backup"
    assert _run(
        "backup_local.py",
        "--database", str(live.database),
        "--checkpoint", str(live.checkpoint),
        "--assets", str(live.assets),
        "--output", str(backup_dir),
        "--confirm-stopped",
    ).returncode == 0
    before = {p.name: p.read_bytes() for p in live.database.parent.rglob("*") if p.is_file()}

    # Missing file in the backup.
    damaged = tmp_path / "damaged"
    import shutil

    shutil.copytree(backup_dir, damaged)
    (damaged / "database.sqlite3").unlink()
    assert _run(
        "restore_local.py", "--backup", str(damaged), "--destination", str(tmp_path / "r1")
    ).returncode == 1
    assert not (tmp_path / "r1").exists()

    # Tampered asset content.
    tampered = tmp_path / "tampered"
    shutil.copytree(backup_dir, tampered)
    asset = next((tampered / "assets").rglob("*"))
    if asset.is_file():
        asset.write_bytes(b"tampered")
    assert _run(
        "restore_local.py", "--backup", str(tampered), "--destination", str(tmp_path / "r2")
    ).returncode == 1
    assert not (tmp_path / "r2").exists()

    # Destination already exists.
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    assert _run(
        "restore_local.py", "--backup", str(backup_dir), "--destination", str(occupied)
    ).returncode == 1

    after = {p.name: p.read_bytes() for p in live.database.parent.rglob("*") if p.is_file()}
    assert after == before


def _seed_one_asset(client):
    owner = _register(client, "owner@example.com")
    project = client.post(
        "/v1/projects", headers=_auth(owner),
        json={"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": True},
    ).json()
    upload = client.post(
        f"/v1/projects/{project['id']}/assets", headers=_auth(owner),
        data={"expectedStateVersion": "0", "idempotencyKey": "a"},
        files={"file": ("room.png", _image_bytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    return project


def _valid_backup(tmp_path, monkeypatch) -> Path:
    live = App(tmp_path / "live" / "db.sqlite3", tmp_path / "live" / "cp.sqlite3", tmp_path / "live" / "assets")
    live.database.parent.mkdir(parents=True)
    client = live.start(monkeypatch)
    _seed_one_asset(client)
    live.stop()
    backup_dir = tmp_path / "backup"
    assert _run(
        "backup_local.py",
        "--database", str(live.database),
        "--checkpoint", str(live.checkpoint),
        "--assets", str(live.assets),
        "--output", str(backup_dir),
        "--confirm-stopped",
    ).returncode == 0
    return backup_dir


def test_backup_rejects_symlinked_directory(tmp_path, monkeypatch):
    live = App(tmp_path / "live" / "db.sqlite3", tmp_path / "live" / "cp.sqlite3", tmp_path / "live" / "assets")
    live.database.parent.mkdir(parents=True)
    client = live.start(monkeypatch)
    _seed_one_asset(client)
    live.stop()

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "hidden.png").write_bytes(b"hidden")
    (live.assets / "linked").symlink_to(outside, target_is_directory=True)

    backup_dir = tmp_path / "backup"
    result = _run(
        "backup_local.py",
        "--database", str(live.database),
        "--checkpoint", str(live.checkpoint),
        "--assets", str(live.assets),
        "--output", str(backup_dir),
        "--confirm-stopped",
    )
    assert result.returncode == 1
    assert "symlink" in result.stderr.lower()
    assert not backup_dir.exists()


def test_restore_rejects_files_that_do_not_match_the_manifest(tmp_path, monkeypatch):
    import shutil

    backup_dir = _valid_backup(tmp_path, monkeypatch)

    # An unregistered file (entry removed from the manifest) must be rejected.
    unregistered = tmp_path / "unregistered"
    shutil.copytree(backup_dir, unregistered)
    manifest = json.loads((unregistered / "manifest.json").read_text())
    entry = next(item for item in manifest["files"] if item["path"].startswith("assets/"))
    manifest["files"] = [item for item in manifest["files"] if item["path"] != entry["path"]]
    (unregistered / "manifest.json").write_text(json.dumps(manifest))
    (unregistered / entry["path"]).write_bytes(b"changed")
    assert _run(
        "restore_local.py", "--backup", str(unregistered), "--destination", str(tmp_path / "r1")
    ).returncode == 1
    assert not (tmp_path / "r1").exists()

    # A database missing from the manifest must be rejected.
    missing = tmp_path / "missing"
    shutil.copytree(backup_dir, missing)
    manifest = json.loads((missing / "manifest.json").read_text())
    manifest["files"] = [
        item for item in manifest["files"] if item["path"] != "checkpoints.sqlite3"
    ]
    (missing / "manifest.json").write_text(json.dumps(manifest))
    assert _run(
        "restore_local.py", "--backup", str(missing), "--destination", str(tmp_path / "r2")
    ).returncode == 1
    assert not (tmp_path / "r2").exists()


def test_restore_rejects_a_destination_inside_the_backup(tmp_path, monkeypatch):
    backup_dir = _valid_backup(tmp_path, monkeypatch)
    result = _run(
        "restore_local.py",
        "--backup", str(backup_dir),
        "--destination", str(backup_dir / "inner"),
    )
    assert result.returncode == 1
    assert not (backup_dir / "inner").exists()


def test_restore_rejects_an_unregistered_nested_manifest(tmp_path, monkeypatch):
    import shutil

    backup_dir = _valid_backup(tmp_path, monkeypatch)
    nested = tmp_path / "nested"
    shutil.copytree(backup_dir, nested)
    (nested / "assets" / "manifest.json").write_text("{}")

    assert _run(
        "restore_local.py", "--backup", str(nested), "--destination", str(tmp_path / "r1")
    ).returncode == 1
    assert not (tmp_path / "r1").exists()


def test_restore_rejects_a_backup_without_the_assets_directory(tmp_path, monkeypatch):
    import shutil

    backup_dir = _valid_backup(tmp_path, monkeypatch)
    stripped = tmp_path / "stripped"
    shutil.copytree(backup_dir, stripped)
    shutil.rmtree(stripped / "assets")
    manifest = json.loads((stripped / "manifest.json").read_text())
    manifest["files"] = [
        item for item in manifest["files"] if not item["path"].startswith("assets/")
    ]
    (stripped / "manifest.json").write_text(json.dumps(manifest))

    assert _run(
        "restore_local.py", "--backup", str(stripped), "--destination", str(tmp_path / "r2")
    ).returncode == 1
    assert not (tmp_path / "r2").exists()
