# Real Image Upload and Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a homeowner upload real JPEG/PNG/WebP reference images, store them on the local filesystem, read them back, soft-delete them, and make analysis observations traceable to the source asset.

**Architecture:** A `Storage` protocol with a local content-addressed implementation holds bytes; an image module validates magic bytes, size and decodes with Pillow (re-encoding to strip EXIF/GPS). `ProjectResourceService` orchestrates upload/read/soft-delete inside the existing membership, consent, version and idempotency rules. The deterministic vision provider emits one `proposed` observation per active asset so `Evidence.sourceId` is a real asset id.

**Tech Stack:** Python 3.12, FastAPI (multipart via `UploadFile`/`Form`), SQLAlchemy, SQLite, Pillow; React/TypeScript/Vitest frontend.

## Global Constraints

- Reference images: JPEG / PNG / WebP only, one file per request, max 10 MB, max 10 active assets per project.
- Storage is local filesystem behind a `Storage` interface; root from `ALIGNSPACE_ASSET_DIR`, default `var/assets/` (gitignored). Content-addressed by SHA-256; storage keys never contain user filenames.
- Public asset API accepts real uploads only; the fixture-registration JSON endpoint is removed.
- Upload/delete are homeowner-only; content read is member-only.
- Consent required before upload; analysis requires 3–10 active assets.
- Soft delete: keep the metadata row, delete bytes, never delete the workflow checkpoint or existing observations.
- Strip EXIF/GPS before storing; never trust client `Content-Type` or filename.
- Version/idempotency semantics are preserved: same key + same content returns first result, same key + different content → 409, stale `expectedStateVersion` → 409.
- Frontend copy must say images are real and analysis is still simulated until step 2.
- Python line length 100; `ruff check src tests` must stay clean.

---

### Task 1: Storage interface and local content-addressed storage

**Files:**
- Create: `src/alignspace/storage/__init__.py`
- Create: `src/alignspace/storage/base.py`
- Create: `src/alignspace/storage/local.py`
- Test: `tests/unit/test_local_storage.py`

**Interfaces:**
- Produces: `Storage` protocol with `save(data: bytes, extension: str) -> str`, `open(key: str) -> bytes`, `delete(key: str) -> None`, `exists(key: str) -> bool`; `LocalStorage(root: str | Path)` implementing it.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from alignspace.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(tmp_path / "assets")


def test_save_is_content_addressed_and_round_trips(storage):
    key = storage.save(b"hello world", "jpg")
    assert key.endswith(".jpg")
    assert storage.exists(key) is True
    assert storage.open(key) == b"hello world"


def test_saving_identical_bytes_reuses_one_key(storage):
    assert storage.save(b"same", "png") == storage.save(b"same", "png")


def test_delete_removes_bytes_and_is_idempotent(storage):
    key = storage.save(b"bye", "webp")
    storage.delete(key)
    storage.delete(key)
    assert storage.exists(key) is False


@pytest.mark.parametrize("key", ["", "../escape.jpg", "nested/key.jpg", ".hidden"])
def test_traversal_like_keys_are_rejected(storage, key):
    with pytest.raises(ValueError):
        storage.open(key)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_local_storage.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'alignspace.storage'`

- [ ] **Step 3: Write minimal implementation**

`src/alignspace/storage/__init__.py`:

```python
from alignspace.storage.base import Storage
from alignspace.storage.local import LocalStorage

__all__ = ["Storage", "LocalStorage"]
```

`src/alignspace/storage/base.py`:

```python
from typing import Protocol


class Storage(Protocol):
    def save(self, data: bytes, extension: str) -> str: ...
    def open(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
```

`src/alignspace/storage/local.py`:

```python
import hashlib
import os
from pathlib import Path


class LocalStorage:
    """Content-addressed local filesystem storage.

    Keys are ``<sha256>.<extension>`` and never contain caller-supplied paths,
    so a key can never escape the configured root.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def save(self, data: bytes, extension: str) -> str:
        key = f"{hashlib.sha256(data).hexdigest()}.{extension.lstrip('.').lower()}"
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        return key

    def open(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def _path(self, key: str) -> Path:
        valid = (
            key
            and key[0] not in ".\\"
            and "/" not in key
            and "\\" not in key
        )
        if not valid:
            raise ValueError("invalid storage key")
        return self._root / key
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_local_storage.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/alignspace/storage tests/unit/test_local_storage.py
git commit -m "feat: add content-addressed local asset storage"
```

---

### Task 2: Image validation and EXIF stripping

**Files:**
- Modify: `pyproject.toml` (add `Pillow>=11,<12` to `dependencies`)
- Create: `src/alignspace/storage/images.py`
- Test: `tests/unit/test_image_validation.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `prepare_image(raw: bytes) -> PreparedImage`; `PreparedImage(data, media_type, extension, sha256, width, height)`; `ImageValidationError(code, message)` with codes `ASSET_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `INVALID_IMAGE`; `MAX_BYTES = 10 * 1024 * 1024`.

- [ ] **Step 1: Write the failing test**

```python
from io import BytesIO

import pytest
from PIL import Image

from alignspace.storage.images import MAX_BYTES, ImageValidationError, prepare_image


def encode(image: Image.Image, fmt: str, **kwargs) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("fmt", "media_type", "extension"),
    [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png"), ("WEBP", "image/webp", "webp")],
)
def test_supported_formats_are_normalized(fmt, media_type, extension):
    prepared = prepare_image(encode(Image.new("RGB", (8, 6), "red"), fmt))
    assert prepared.media_type == media_type
    assert prepared.extension == extension
    assert (prepared.width, prepared.height) == (8, 6)
    assert len(prepared.sha256) == 64


def test_oversized_payload_is_rejected():
    with pytest.raises(ImageValidationError) as error:
        prepare_image(b"\x00" * (MAX_BYTES + 1))
    assert error.value.code == "ASSET_TOO_LARGE"


def test_non_image_payload_is_rejected():
    with pytest.raises(ImageValidationError) as error:
        prepare_image(b"definitely not an image")
    assert error.value.code == "INVALID_IMAGE"


def test_unsupported_format_is_rejected():
    with pytest.raises(ImageValidationError) as error:
        prepare_image(encode(Image.new("RGB", (4, 4), "red"), "GIF"))
    assert error.value.code == "UNSUPPORTED_MEDIA_TYPE"


def test_exif_and_gps_are_stripped():
    source = Image.new("RGB", (8, 8), "blue")
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"  # Make
    exif[0x0112] = 3  # Orientation
    raw = encode(source, "JPEG", exif=exif.tobytes())
    assert Image.open(BytesIO(raw)).getexif()

    prepared = prepare_image(raw)

    assert not Image.open(BytesIO(prepared.data)).getexif()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv add "Pillow>=11,<12" && uv run pytest tests/unit/test_image_validation.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'alignspace.storage.images'`

- [ ] **Step 3: Write minimal implementation**

`src/alignspace/storage/images.py`:

```python
import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024

FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


class ImageValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    media_type: str
    extension: str
    sha256: str
    width: int
    height: int


def prepare_image(raw: bytes) -> PreparedImage:
    if len(raw) > MAX_BYTES:
        raise ImageValidationError("ASSET_TOO_LARGE", "图片不得超过 10MB。")
    try:
        with Image.open(BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(BytesIO(raw)) as image:
            image.load()
            image_format = image.format or ""
            if image_format not in FORMATS:
                raise ImageValidationError("UNSUPPORTED_MEDIA_TYPE", "仅支持 JPEG、PNG、WebP。")
            media_type, extension = FORMATS[image_format]
            width, height = image.size
            buffer = BytesIO()
            # Re-encoding without passing exif= drops EXIF/GPS metadata.
            image.save(buffer, format=image_format)
            cleaned = buffer.getvalue()
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageValidationError("INVALID_IMAGE", "无法识别的图片文件。") from None
    return PreparedImage(
        data=cleaned,
        media_type=media_type,
        extension=extension,
        sha256=hashlib.sha256(cleaned).hexdigest(),
        width=width,
        height=height,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_image_validation.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/alignspace/storage/images.py tests/unit/test_image_validation.py
git commit -m "feat: validate and normalise uploaded images with Pillow"
```

---

### Task 3: Migration v2 — soft-delete column

**Files:**
- Modify: `src/alignspace/persistence/tables.py`
- Modify: `src/alignspace/persistence/migrations.py`
- Test: `tests/integration/persistence/test_migrations.py`

**Interfaces:**
- Produces: `ImageAssetRow.deleted_at: int | None` column; migration version 2.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/persistence/test_migrations.py`:

```python
def test_migration_adds_soft_delete_column_and_is_repeatable(tmp_path):
    url = f"sqlite:///{tmp_path / 'soft-delete.db'}"
    first_engine, _ = create_engine_and_session(url)
    first_engine.dispose()

    engine, _ = create_engine_and_session(url)
    try:
        columns = {
            row[1] for row in engine.connect().exec_driver_sql("PRAGMA table_info(image_assets)")
        }
        assert "deleted_at" in columns
        versions = {
            row[0]
            for row in engine.connect().exec_driver_sql(
                "SELECT version FROM schema_migrations"
            )
        }
        assert versions == {1, 2}
    finally:
        engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/persistence/test_migrations.py::test_migration_adds_soft_delete_column_and_is_repeatable -q`
Expected: FAIL — `'deleted_at'` not in columns

- [ ] **Step 3: Write minimal implementation**

In `src/alignspace/persistence/tables.py`, add to `ImageAssetRow`:

```python
    deleted_at: Mapped[int | None] = mapped_column(Integer)
```

In `src/alignspace/persistence/migrations.py`, replace `migrate` with:

```python
def migrate(engine):
    """Additive migrations. Re-running is safe.

    Version 1 adds auth tables and one member per role. Version 2 adds the
    image soft-delete column. Existing development databases are never assigned
    to real users by email/ID heuristics.
    """
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS project_member_role "
            "ON project_members(project_id, role)"
        ))
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(image_assets)"))
        }
        if "deleted_at" not in columns:
            connection.execute(text("ALTER TABLE image_assets ADD COLUMN deleted_at INTEGER"))
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 1},
        )
        connection.execute(
            text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (:version)"),
            {"version": 2},
        )
    assert MigrationRow.__tablename__ in Base.metadata.tables
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/persistence/test_migrations.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/alignspace/persistence/tables.py src/alignspace/persistence/migrations.py tests/integration/persistence/test_migrations.py
git commit -m "feat: add soft-delete column to image assets"
```

---

### Task 4: Asset views, multipart upload, storage wiring

**Files:**
- Modify: `src/alignspace/application/resources.py`
- Modify: `src/alignspace/api/routes/projects.py`
- Modify: `src/alignspace/api/errors.py`
- Modify: `src/alignspace/main.py`
- Modify: `.gitignore`
- Test: `tests/api/test_asset_upload.py`

**Interfaces:**
- Consumes: `Storage`/`LocalStorage` (Task 1), `prepare_image`/`ImageValidationError` (Task 2).
- Produces:
  - `AssetView { id, original_filename, media_type, size_bytes, sha256, deleted, deleted_at }`
  - `AssetWriteView(AssetView) + { state_version }`
  - `ProjectResourceService(session_factory, checkpoint_delete, storage)`
  - `ProjectResourceService.register_asset(project_id, actor, *, expected_state_version, idempotency_key, filename, raw) -> AssetWriteView`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_asset_upload.py`:

```python
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from alignspace.auth.config import AuthConfig

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "a sufficiently long password"
SECRET = "asset-upload-test-secret-long-enough"


@pytest.fixture
def api(tmp_path):
    from alignspace.main import create_app

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'upload.db'}",
        checkpoint_path=str(tmp_path / "checkpoints.db"),
        auth_config=AuthConfig(secret=SECRET, secure_cookie=False),
    )
    with TestClient(app, headers=ORIGIN) as client:
        yield client


def image_bytes(fmt="PNG", color="red"):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format=fmt)
    return buffer.getvalue()


def register(api, email):
    response = api.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def auth(user):
    return {"Authorization": f"Bearer {user['accessToken']}"}


def create_project(api, owner, consent=True):
    response = api.post(
        "/v1/projects",
        headers=auth(owner),
        json={"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": consent},
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(api, owner, project_id, *, key="upload-1", version=0, fmt="PNG", data=None):
    raw = data if data is not None else image_bytes(fmt)
    return api.post(
        f"/v1/projects/{project_id}/assets",
        headers=auth(owner),
        data={"expectedStateVersion": str(version), "idempotencyKey": key},
        files={"file": (f"room.{fmt.lower()}", raw, f"image/{fmt.lower()}")},
    )


def test_homeowner_uploads_a_real_image_and_sees_it_listed(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)

    created = upload(api, owner, project["id"])
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["mediaType"] == "image/png"
    assert body["originalFilename"] == "room.png"
    assert body["sizeBytes"] > 0
    assert body["deleted"] is False
    assert body["stateVersion"] == 1

    listed = api.get(f"/v1/projects/{project['id']}", headers=auth(owner)).json()
    assert [asset["id"] for asset in listed["assets"]] == [body["id"]]
    assert listed["assets"][0]["sha256"] == body["sha256"]


def test_upload_requires_consent_homeowner_and_valid_image(api):
    owner = register(api, "owner@example.com")
    unconsented = create_project(api, owner, consent=False)
    consented = create_project(api, owner, consent=True)

    assert upload(api, owner, unconsented["id"]).status_code == 409
    assert upload(api, owner, consented["id"], fmt="GIF").status_code == 415
    assert upload(api, owner, consented["id"], data=b"not-an-image").status_code == 400
    assert upload(api, owner, consented["id"], data=b"\x00" * (10 * 1024 * 1024 + 1)).status_code == 413


def test_upload_is_idempotent_and_rejects_conflicting_reuse(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)

    first = upload(api, owner, project["id"], key="same")
    replay = upload(api, owner, project["id"], key="same")
    assert replay.json() == first.json()

    conflict = upload(api, owner, project["id"], key="same", data=image_bytes(color="blue"))
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_stale_version_and_non_member_are_rejected(api):
    owner = register(api, "owner@example.com")
    stranger = register(api, "stranger@example.com")
    project = create_project(api, owner)

    stale = upload(api, owner, project["id"], version=5)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STATE_VERSION_STALE"
    assert upload(api, stranger, project["id"]).status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_asset_upload.py -q`
Expected: FAIL — upload returns 422 (multipart not accepted) / storage args missing

- [ ] **Step 3: Write minimal implementation**

In `src/alignspace/application/resources.py`:

Replace the `AssetInput` class and `AssetView`/`AssetWriteView` definitions with:

```python
class AssetView(DomainModel):
    id: str
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    deleted: bool
    deleted_at: int | None = None


class AssetWriteView(AssetView):
    state_version: int
```

Add imports near the top:

```python
import time

from alignspace.storage.base import Storage
from alignspace.storage.images import prepare_image
```

Change `ProjectResourceService.__init__` to accept storage:

```python
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        checkpoint_delete: CheckpointDelete,
        storage: Storage,
    ) -> None:
        self._session_factory = session_factory
        self._checkpoint_delete = checkpoint_delete
        self._storage = storage
```

Replace `register_asset` entirely with:

```python
    def register_asset(
        self,
        project_id: str,
        actor: ActorContext,
        *,
        expected_state_version: int,
        idempotency_key: str,
        filename: str,
        raw: bytes,
    ) -> AssetWriteView:
        self._authorize_homeowner(project_id, actor)
        prepared = prepare_image(raw)
        request_hash = canonical_request_hash(
            {
                "action": "upload_asset",
                "projectId": project_id,
                "actor": actor.model_dump(mode="json", by_alias=True),
                "expectedStateVersion": expected_state_version,
                "idempotencyKey": idempotency_key,
                "sha256": prepared.sha256,
                "mediaType": prepared.media_type,
                "sizeBytes": len(prepared.data),
            }
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            self._authorize_in_session(uow.session, project_id, actor)
            if actor.role != Role.HOMEOWNER:
                raise AuthorizationError("only the homeowner can manage reference assets")
            replay = uow.idempotency.lookup(project_id, idempotency_key, request_hash)
            if replay is not None:
                return AssetWriteView.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, expected_state_version)
            project = self._project(uow.session, project_id)
            if not project.consent:
                raise ConsentRequiredError("image consent is required before registering an asset")
            active = uow.session.scalar(
                select(func.count()).select_from(ImageAssetRow).where(
                    ImageAssetRow.project_id == project_id,
                    ImageAssetRow.deleted_at.is_(None),
                )
            )
            if active >= 10:
                raise AssetLimitError("a project can contain at most ten reference assets")
            storage_key = self._storage.save(prepared.data, prepared.extension)
            asset = AssetWriteView(
                id=str(uuid4()),
                original_filename=filename,
                media_type=prepared.media_type,
                size_bytes=len(prepared.data),
                sha256=prepared.sha256,
                deleted=False,
                deleted_at=None,
                state_version=state.state_version + 1,
            )
            uow.session.add(
                ImageAssetRow(
                    project_id=project_id,
                    id=asset.id,
                    payload={
                        "original_filename": filename,
                        "media_type": prepared.media_type,
                        "size_bytes": len(prepared.data),
                        "sha256": prepared.sha256,
                        "storage_key": storage_key,
                        "width": prepared.width,
                        "height": prepared.height,
                    },
                )
            )
            updated = state.model_copy(update={"state_version": state.state_version + 1})
            uow.projects.save(updated, expected_version=state.state_version)
            uow.idempotency.record(
                project_id=project_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_payload=asset.model_dump(mode="json", by_alias=True),
                resulting_version=asset.state_version,
            )
            uow.commit()
            return asset
```

Add the homeowner helper (used by upload and later delete):

```python
    def _authorize_homeowner(self, project_id: str, actor: ActorContext) -> None:
        with self._session_factory() as session:
            self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            if actor.role != Role.HOMEOWNER:
                raise AuthorizationError("only the homeowner can manage reference assets")
```

In `src/alignspace/api/routes/projects.py`, replace the `register_asset` route with:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
```

```python
@router.post(
    "/{project_id}/assets",
    response_model=AssetWriteView,
    status_code=status.HTTP_201_CREATED,
)
def register_asset(
    project_id: str,
    file: Annotated[UploadFile, File()],
    expected_state_version: Annotated[int, Form()],
    idempotency_key: Annotated[str, Form()],
    actor: Actor,
    container: Container,
) -> AssetWriteView:
    return container.resources.register_asset(
        project_id,
        actor,
        expected_state_version=expected_state_version,
        idempotency_key=idempotency_key,
        filename=file.filename or "upload",
        raw=file.file.read(),
    )
```

Remove the now-unused `AssetInput` import from the route module.

In `src/alignspace/api/errors.py`, add an import and handler:

```python
from alignspace.storage.images import ImageValidationError
```

```python
    @app.exception_handler(ImageValidationError)
    async def image_handler(request: Request, exc: ImageValidationError) -> JSONResponse:
        status_code = {
            "ASSET_TOO_LARGE": 413,
            "UNSUPPORTED_MEDIA_TYPE": 415,
        }.get(exc.code, 400)
        return _response(
            request,
            status_code=status_code,
            code=exc.code,
            message=str(exc),
            recoverable=True,
        )
```

In `src/alignspace/main.py`, create the storage and pass it in:

```python
from alignspace.storage.local import LocalStorage
```

```python
    storage = LocalStorage(os.getenv("ALIGNSPACE_ASSET_DIR", "var/assets"))
    resources = ProjectResourceService(
        session_factory=session_factory,
        checkpoint_delete=graph.checkpointer.delete_thread,
        storage=storage,
    )
```

In `.gitignore`, add:

```
var/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_asset_upload.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add .gitignore src/alignspace/application/resources.py src/alignspace/api/routes/projects.py src/alignspace/api/errors.py src/alignspace/main.py tests/api/test_asset_upload.py
git commit -m "feat: accept real multipart image uploads with validation"
```

---

### Task 5: Asset content read endpoint

**Files:**
- Modify: `src/alignspace/application/resources.py`
- Modify: `src/alignspace/api/routes/projects.py`
- Test: `tests/api/test_asset_upload.py`

**Interfaces:**
- Consumes: stored bytes from Task 4.
- Produces: `ProjectResourceService.asset_content(project_id, asset_id, actor) -> tuple[bytes, str]`; `GET /v1/projects/{projectId}/assets/{assetId}/content`.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_asset_upload.py`:

```python
def test_members_can_read_image_content_but_outsiders_cannot(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)
    asset = upload(api, owner, project["id"]).json()

    fetched = api.get(
        f"/v1/projects/{project['id']}/assets/{asset['id']}/content",
        headers=auth(owner),
    )
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("image/png")
    assert Image.open(BytesIO(fetched.content)).size == (8, 8)

    stranger = register(api, "stranger@example.com")
    denied = api.get(
        f"/v1/projects/{project['id']}/assets/{asset['id']}/content",
        headers=auth(stranger),
    )
    assert denied.status_code == 403

    missing = api.get(
        f"/v1/projects/{project['id']}/assets/does-not-exist/content",
        headers=auth(owner),
    )
    assert missing.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_asset_upload.py::test_members_can_read_image_content_but_outsiders_cannot -q`
Expected: FAIL — 404/405 (route missing)

- [ ] **Step 3: Write minimal implementation**

In `src/alignspace/application/resources.py`, add:

```python
    def asset_content(self, project_id: str, asset_id: str, actor: ActorContext) -> tuple[bytes, str]:
        with read_transaction(self._session_factory) as session:
            self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            asset = session.get(ImageAssetRow, (project_id, asset_id))
            if asset is None or asset.deleted_at is not None:
                raise KeyError(f"asset {asset_id} not found")
            return self._storage.open(asset.payload["storage_key"]), asset.payload["media_type"]
```

In `src/alignspace/api/routes/projects.py`, add (place before `get_project` so it is not shadowed):

```python
@router.get("/{project_id}/assets/{asset_id}/content")
def asset_content(project_id: str, asset_id: str, actor: Actor, container: Container) -> Response:
    data, media_type = container.resources.asset_content(project_id, asset_id, actor)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=0"},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_asset_upload.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/alignspace/application/resources.py src/alignspace/api/routes/projects.py tests/api/test_asset_upload.py
git commit -m "feat: serve stored asset content to project members"
```

---

### Task 6: Soft delete and active-only counts

**Files:**
- Modify: `src/alignspace/application/resources.py`
- Test: `tests/api/test_asset_upload.py`

**Interfaces:**
- Produces: `delete_asset` soft-deletes and removes bytes; `require_analysis_ready` and the upload limit count only `deleted_at IS NULL`.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_asset_upload.py`:

```python
def test_soft_delete_removes_bytes_but_keeps_a_tombstone(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)
    asset = upload(api, owner, project["id"]).json()

    deleted = api.request(
        "DELETE",
        f"/v1/projects/{project['id']}/assets/{asset['id']}",
        headers=auth(owner),
        json={"idempotencyKey": "delete-1", "expectedStateVersion": 1, "data": {}},
    )
    assert deleted.status_code == 200
    assert deleted.json()["stateVersion"] == 2

    listed = api.get(f"/v1/projects/{project['id']}", headers=auth(owner)).json()
    assert listed["assets"][0]["deleted"] is True
    assert listed["assets"][0]["deletedAt"] is not None

    content = api.get(
        f"/v1/projects/{project['id']}/assets/{asset['id']}/content",
        headers=auth(owner),
    )
    assert content.status_code == 404


def test_analysis_readiness_ignores_deleted_assets(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)
    assets = [upload(api, owner, project["id"], key=f"u{i}", version=i).json() for i in range(3)]
    api.request(
        "DELETE",
        f"/v1/projects/{project['id']}/assets/{assets[0]['id']}",
        headers=auth(owner),
        json={"idempotencyKey": "delete-1", "expectedStateVersion": 3, "data": {}},
    )
    started = api.post(
        f"/v1/projects/{project['id']}/analysis-runs",
        headers=auth(owner),
        json={"idempotencyKey": "run-1", "expectedStateVersion": 4, "data": {}},
    )
    assert started.status_code == 409
    assert started.json()["error"]["code"] == "ASSET_COUNT_INVALID"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_asset_upload.py -q`
Expected: FAIL — asset still readable / not marked deleted

- [ ] **Step 3: Write minimal implementation**

Replace `delete_asset` in `src/alignspace/application/resources.py` with:

```python
    def delete_asset(
        self,
        project_id: str,
        asset_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> AssetDeleteView:
        request_hash = self._request_hash(
            "delete_asset",
            project_id,
            actor,
            envelope,
            extra={"assetId": asset_id},
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            self._authorize_in_session(uow.session, project_id, actor)
            if actor.role != Role.HOMEOWNER:
                raise AuthorizationError("only the homeowner can manage reference assets")
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return AssetDeleteView.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            asset = uow.session.get(ImageAssetRow, (project_id, asset_id))
            if asset is None or asset.deleted_at is not None:
                raise KeyError(f"asset {asset_id} not found")
            self._storage.delete(asset.payload["storage_key"])
            asset.deleted_at = int(time.time())
            updated = state.model_copy(update={"state_version": state.state_version + 1})
            uow.projects.save(updated, expected_version=state.state_version)
            response = AssetDeleteView(id=asset_id, state_version=updated.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
        return response
```

Update `require_analysis_ready`'s count query:

```python
            asset_count = session.scalar(
                select(func.count()).select_from(ImageAssetRow).where(
                    ImageAssetRow.project_id == project_id,
                    ImageAssetRow.deleted_at.is_(None),
                )
            )
```

Update `_project_view` to build the new `AssetView`:

```python
    @staticmethod
    def _project_view(session: Session, project: ProjectRow, role: Role) -> ProjectView:
        assets = session.scalars(
            select(ImageAssetRow)
            .where(ImageAssetRow.project_id == project.id)
            .order_by(ImageAssetRow.id)
        ).all()
        designer_joined = session.scalar(
            select(func.count()).select_from(ProjectMemberRow).where(
                ProjectMemberRow.project_id == project.id,
                ProjectMemberRow.role == Role.DESIGNER.value,
            )
        ) > 0
        return ProjectView(
            id=project.id,
            room_type=project.room_type or "unknown",
            budget_band=project.budget_band or "unknown",
            consent=project.consent,
            status=project.status,
            state_version=project.state_version,
            assets=[
                AssetView(
                    id=item.id,
                    original_filename=item.payload["original_filename"],
                    media_type=item.payload["media_type"],
                    size_bytes=item.payload["size_bytes"],
                    sha256=item.payload["sha256"],
                    deleted=item.deleted_at is not None,
                    deleted_at=item.deleted_at,
                )
                for item in assets
            ],
            role=role,
            designer_joined=designer_joined,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_asset_upload.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/alignspace/application/resources.py tests/api/test_asset_upload.py
git commit -m "feat: soft-delete uploaded images and count only active assets"
```

---

### Task 7: Traceable mock vision per active asset

**Files:**
- Modify: `src/alignspace/agents/contracts.py`
- Modify: `src/alignspace/agents/vision.py`
- Modify: `src/alignspace/providers/mock.py`
- Modify: `src/alignspace/workflow/state.py`
- Modify: `src/alignspace/workflow/graph.py`
- Modify: `src/alignspace/application/service.py`
- Test: `tests/api/test_asset_upload.py`

**Interfaces:**
- Produces: `AssetRef` NamedTuple `(id, media_type, sha256)`; `VisionProvider.analyze(state, assets: list[AssetRef]) -> list[Attribute]`; `VisionAnalyst.run(state, assets)`; `WorkflowState["assets"]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_asset_upload.py`:

```python
def test_vision_observations_reference_the_real_asset(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)
    asset_ids = []
    for index in range(3):
        uploaded = upload(
            api, owner, project["id"], key=f"u{index}", version=index
        ).json()
        asset_ids.append(uploaded["id"])

    started = api.post(
        f"/v1/projects/{project['id']}/analysis-runs",
        headers=auth(owner),
        json={"idempotencyKey": "run-1", "expectedStateVersion": 3, "data": {}},
    )
    assert started.status_code == 202, started.text
    attributes = started.json()["projectState"]["attributes"]
    assert attributes
    proposed = [item for item in attributes if item["status"] == "proposed"]
    assert proposed
    sources = {
        evidence["sourceId"]
        for item in proposed
        for evidence in item["evidence"]
        if evidence["sourceType"] == "image"
    }
    assert sources <= set(asset_ids)
    assert sources
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_asset_upload.py::test_vision_observations_reference_the_real_asset -q`
Expected: FAIL — `sourceId` is `living-room-1`

- [ ] **Step 3: Write minimal implementation**

In `src/alignspace/agents/contracts.py`, add:

```python
class AssetRef(NamedTuple):
    id: str
    media_type: str
    sha256: str
```

Change the protocol:

```python
class VisionProvider(Protocol):
    def analyze(self, state: ProjectState, assets: list[AssetRef]) -> list[Attribute]: ...
```

In `src/alignspace/agents/vision.py`:

```python
from alignspace.agents.contracts import AgentResult, AssetRef, VisionProvider
from alignspace.domain.models import ProjectState
from alignspace.domain.patches import StatePatch, UpsertAttribute, apply_patch


class VisionAnalyst:
    def __init__(self, provider: VisionProvider) -> None:
        self._provider = provider

    def run(self, state: ProjectState, assets: list[AssetRef]) -> AgentResult:
        operations = [
            UpsertAttribute(attribute=attribute)
            for attribute in self._provider.analyze(state, assets)
        ]
        if not operations:
            return AgentResult(state=state)
        updated = apply_patch(
            state,
            StatePatch(expected_state_version=state.state_version, operations=operations),
        )
        return AgentResult(state=updated, patches=operations)
```

In `src/alignspace/providers/mock.py`, replace `MockVisionProvider.analyze`:

```python
class MockVisionProvider:
    _OBSERVATIONS = (
        ("wall", "colour", "warm beige", 0.86),
        ("chair", "material", "natural oak", 0.83),
        ("floor", "colour", "pale oak", 0.81),
        ("lighting", "lighting", "warm ambient", 0.84),
    )

    def analyze(self, state: ProjectState, assets: list[AssetRef]) -> list[Attribute]:
        del state
        observations: list[Attribute] = []
        for index, asset in enumerate(assets):
            for target, dimension, value, confidence in self._OBSERVATIONS:
                observations.append(
                    Attribute(
                        id=f"mock-{asset.id}-{target}-{dimension}",
                        target_element=target,
                        dimension=dimension,
                        value=value,
                        status=AttributeStatus.PROPOSED,
                        confidence=confidence,
                        evidence=[
                            Evidence(
                                source_type=EvidenceSource.IMAGE,
                                source_id=asset.id,
                                description=f"Mock image observation: {target} {dimension}",
                            )
                        ],
                        actor=ActorKind.VISION_AGENT,
                    )
                )
        return observations
```

Add `AssetRef` to the mock provider imports:

```python
from alignspace.agents.contracts import AgentBundle, AssetRef
```

In `src/alignspace/workflow/state.py`, add:

```python
    assets: list[dict[str, object]]
```

In `src/alignspace/workflow/graph.py`, change the vision node:

```python
    def vision_analysis(workflow_state: WorkflowState) -> WorkflowState:
        assets = [
            AssetRef(id=item["id"], media_type=item["media_type"], sha256=item["sha256"])
            for item in workflow_state.get("assets", [])
        ]
        result = agents.vision.run(_project_state(workflow_state), assets)
        return {"project_state": _dump(result.state)}
```

Add the import at the top of `graph.py`:

```python
from alignspace.agents.contracts import AssetRef
```

In `src/alignspace/application/service.py`, load active assets for the first graph run. Add imports:

```python
from sqlalchemy import select

from alignspace.persistence.tables import ImageAssetRow
```

Add a helper method and use it in `_run_graph`:

```python
    def _active_assets(self, project_id: str) -> list[dict[str, object]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ImageAssetRow)
                .where(
                    ImageAssetRow.project_id == project_id,
                    ImageAssetRow.deleted_at.is_(None),
                )
                .order_by(ImageAssetRow.id)
            ).all()
            return [
                {
                    "id": row.id,
                    "media_type": row.payload["media_type"],
                    "sha256": row.payload["sha256"],
                }
                for row in rows
            ]
```

In `_run_graph`, replace the non-resume `graph_input`:

```python
            else:
                graph_input = {
                    "project_id": project_id,
                    "project_state": current.model_dump(mode="json", by_alias=True),
                    "assets": self._active_assets(project_id),
                }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_asset_upload.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/alignspace/agents/contracts.py src/alignspace/agents/vision.py src/alignspace/providers/mock.py src/alignspace/workflow/state.py src/alignspace/workflow/graph.py src/alignspace/application/service.py tests/api/test_asset_upload.py
git commit -m "feat: trace vision observations to real uploaded assets"
```

---

### Task 8: Migrate existing fixture-based tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/api/test_assets_and_attributes.py`
- Modify: `tests/api/test_workflow.py`
- Modify: `tests/api/test_membership.py`
- Modify: `tests/acceptance/test_real_accounts_flow.py`

**Interfaces:**
- Consumes: the multipart upload endpoint (Task 4) and soft delete (Task 6).
- Produces: test helpers only; no production code.

- [ ] **Step 1: Add a shared image/upload helper and seed helper to `tests/conftest.py`**

Add near the top imports:

```python
from io import BytesIO

from PIL import Image
```

Add module-level helpers:

```python
def image_bytes(fmt: str = "PNG", color: str = "red") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format=fmt)
    return buffer.getvalue()


def upload_asset(
    client: TestClient,
    project_id: str,
    *,
    headers: dict[str, str],
    key: str,
    version: int,
    fmt: str = "PNG",
) -> dict:
    response = client.post(
        f"/v1/projects/{project_id}/assets",
        headers=headers,
        data={"expectedStateVersion": str(version), "idempotencyKey": key},
        files={"file": (f"room.{fmt.lower()}", image_bytes(fmt), f"image/{fmt.lower()}")},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def upload_image(client: TestClient):
    def _upload(
        project_id: str,
        *,
        headers: dict[str, str],
        key: str,
        version: int,
        fmt: str = "PNG",
        color: str = "red",
    ):
        return client.post(
            f"/v1/projects/{project_id}/assets",
            headers=headers,
            data={"expectedStateVersion": str(version), "idempotencyKey": key},
            files={
                "file": (f"room.{fmt.lower()}", image_bytes(fmt, color), f"image/{fmt.lower()}")
            },
        )

    return _upload
```

Change `_create_project`'s asset seeding block in `analysis_ready_project` so it uploads three images and tracks the version returned by each call (the envelope version must advance). Replace the loop with:

```python
    version = 0
    for index in range(3):
        asset = upload_asset(
            client, project_id, headers=headers, key=f"ready-asset-{index}", version=version
        )
        version = asset["stateVersion"]
```

- [ ] **Step 2: Rewrite `tests/api/test_assets_and_attributes.py` asset tests**

Delete `_asset_envelope` and rewrite the asset tests to upload. Replace the file's asset tests with:

```python
def test_designer_cannot_manage_reference_assets(client, ready_project, upload_image) -> None:
    created = upload_image(ready_project, headers=_headers(), key="homeowner-asset", version=0)
    assert created.status_code == 201
    add_attempt = upload_image(
        ready_project, headers=_headers("designer-1", "designer"),
        key="designer-asset", version=1,
    )
    assert add_attempt.status_code == 403
    remove_attempt = client.request(
        "DELETE",
        f"/v1/projects/{ready_project}/assets/{created.json()['id']}",
        headers=_headers("designer-1", "designer"),
        json={"idempotencyKey": "designer-delete", "expectedStateVersion": 1, "data": {}},
    )
    assert remove_attempt.status_code == 403


def test_asset_registration_requires_consent(client, project_without_consent, upload_image) -> None:
    response = upload_image(
        project_without_consent, headers=_headers(), key="asset-1", version=0
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_register_and_soft_delete_are_versioned_and_idempotent(
    client, ready_project, upload_image
) -> None:
    first = upload_image(ready_project, headers=_headers(), key="asset-create", version=0)
    replay = upload_image(ready_project, headers=_headers(), key="asset-create", version=0)
    assert first.status_code == 201
    assert replay.json() == first.json()

    asset_id = first.json()["id"]
    listed = client.get(f"/v1/projects/{ready_project}", headers=_headers()).json()["assets"]
    assert listed[0]["id"] == asset_id
    assert listed[0]["deleted"] is False

    deleted = client.request(
        "DELETE",
        f"/v1/projects/{ready_project}/assets/{asset_id}",
        headers=_headers(),
        json={"idempotencyKey": "asset-delete", "expectedStateVersion": 1, "data": {}},
    )
    assert deleted.status_code == 200
    assert deleted.json()["stateVersion"] == 2
    after = client.get(f"/v1/projects/{ready_project}", headers=_headers()).json()["assets"]
    assert after[0]["deleted"] is True


def test_asset_conflicting_replay_returns_stable_error(client, ready_project, upload_image) -> None:
    first = upload_image(ready_project, headers=_headers(), key="asset-create", version=0)
    conflict = upload_image(
        ready_project, headers=_headers(), key="asset-create", version=0, color="blue"
    )
    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_project_accepts_at_most_ten_reference_assets(client, ready_project, upload_image) -> None:
    for index in range(10):
        response = upload_image(
            ready_project, headers=_headers(), key=f"asset-{index}", version=index
        )
        assert response.status_code == 201
    rejected = upload_image(ready_project, headers=_headers(), key="asset-11", version=10)
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "ASSET_LIMIT_REACHED"
```

The attribute tests (`test_homeowner_can_correct_an_observed_attribute`, etc.) are unchanged.

- [ ] **Step 3: Update the remaining fixture usage**

In `tests/conftest.py`:
- `WorkflowDriver.complete`: replace the three `POST .../assets` envelope writes with `upload_asset(self.client, project_id, headers=self.homeowner_headers, key=f"asset-{index}", version=<running version>)`, tracking the returned `stateVersion`.
- `project_with_attribute` and `brief_ready_project` fixtures do not touch assets and need no change.

In `tests/api/test_workflow.py` and `tests/api/test_membership.py`: `analysis_ready_project`/`ready_project` now already contain uploaded assets, so their asset-count assertions are unchanged; only calls that previously posted fixture assets are now uploads through the helper.

In `tests/acceptance/test_real_accounts_flow.py`, replace the three fixture writes in `TwoAccountDriver.run` with multipart uploads carrying the owner's Bearer token, advancing `expectedStateVersion` by the returned `stateVersion` each time.

- [ ] **Step 4: Run the full backend suite**

Run: `uv run pytest -q`
Expected: all tests pass (`154 + 8 new - removed asset tests`, exact count printed). If a test still expects `fixtureId`, update it to the new `AssetView` fields.

- [ ] **Step 5: Commit**

```bash
git add tests
git commit -m "test: migrate fixtures to real image uploads"
```

---

### Task 9: Frontend types and API client

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/api.test.ts`
- Modify: `frontend/src/test/fixtures.ts`

**Interfaces:**
- Produces: `Asset { id, originalFilename, mediaType, sizeBytes, sha256, deleted, deletedAt }`; `ApiClient.upload<T>(path, file, fields)`, `ApiClient.blob(path)`, exported `newIdempotencyKey()`.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/api.test.ts`:

```ts
import { newIdempotencyKey } from './api';

describe('asset transfer', () => {
  it('uploads multipart data without a JSON content type', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(auth())
      .mockResolvedValueOnce(json({ id: 'a1' }, 201));
    const client = new ApiClient({ fetcher, locks: null, channel: null });
    await client.restore();

    const file = new Blob(['x'], { type: 'image/png' });
    await client.upload('/v1/projects/p/assets', file, {
      expectedStateVersion: '0',
      idempotencyKey: 'k1',
    });

    const init = fetcher.mock.calls[1][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.headers as Headers).has('Content-Type')).toBe(false);
  });

  it('downloads image bytes as a blob', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(auth())
      .mockResolvedValueOnce(new Response(new Blob(['img']), { status: 200 }));
    const client = new ApiClient({ fetcher, locks: null, channel: null });
    await client.restore();

    const blob = await client.blob('/v1/projects/p/assets/a1/content');
    expect(blob).toBeInstanceOf(Blob);
  });

  it('generates distinct idempotency keys', () => {
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api.test.ts`
Expected: FAIL — `client.upload is not a function`

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/api.ts`, export the key helper (rename the existing private function):

```ts
export function newIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto as Crypto | undefined;
  if (cryptoApi?.randomUUID) return cryptoApi.randomUUID();
  return `key-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
```

Use it inside `prepareWrite` (`idempotencyKey: newIdempotencyKey()`), and add:

```ts
  async upload<T>(path: string, file: Blob, fields: Record<string, string>): Promise<T> {
    const body = new FormData();
    for (const [key, value] of Object.entries(fields)) body.append(key, value);
    body.append('file', file);
    const response = await this.requestWithRefresh(path, { method: 'POST', body });
    return (await response.json()) as T;
  }

  async blob(path: string): Promise<Blob> {
    const response = await this.requestWithRefresh(path, { method: 'GET' });
    return response.blob();
  }
```

In `frontend/src/types.ts`, replace `Asset`:

```ts
export type Asset = {
  id: string;
  originalFilename: string;
  mediaType: string;
  sizeBytes: number;
  sha256: string;
  deleted: boolean;
  deletedAt: number | null;
};
```

In `frontend/src/test/fixtures.ts`, update the asset literal:

```ts
      assets: [
        {
          id: 'a1',
          originalFilename: 'living-room.png',
          mediaType: 'image/png',
          sizeBytes: 1024,
          sha256: 'b'.repeat(64),
          deleted: false,
          deletedAt: null,
        },
      ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api.test.ts`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts frontend/src/api.test.ts frontend/src/types.ts frontend/src/test/fixtures.ts
git commit -m "feat: add multipart upload and blob fetch to the API client"
```

---

### Task 10: Workspace upload, thumbnails and source-deleted marking

**Files:**
- Modify: `frontend/src/workflow/Workspace.tsx`
- Modify: `frontend/src/workflow/Workspace.test.tsx`
- Test: `frontend/src/workflow/Workspace.test.tsx`

**Interfaces:**
- Consumes: `ApiClient.upload`, `ApiClient.blob`, `newIdempotencyKey`, `Asset` (Task 9).

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/workflow/Workspace.test.tsx`:

```ts
describe('real image uploads', () => {
  it('uploads a selected file with the current version and a new key', async () => {
    const env = setup('homeowner');
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    const input = await screen.findByLabelText('上传参考图片');
    const file = new File([new Uint8Array([1, 2, 3])], 'room.png', { type: 'image/png' });
    await userEvent.upload(input, file);
    await waitFor(() => expect(env.writes).toHaveLength(1));
    expect(env.writes[0].method).toBe('POST');
    expect(env.writes[0].body).toBeInstanceOf(FormData);
    expect((env.writes[0].body as FormData).get('expectedStateVersion')).toBe('4');
    expect((env.writes[0].body as FormData).get('file')).toBeInstanceOf(File);
  });

  it('marks observations whose source image was deleted', async () => {
    const base = snapshot('homeowner');
    const initial: ProjectSnapshot = {
      ...base,
      project: {
        ...base.project,
        assets: [{ ...base.project.assets[0], deleted: true, deletedAt: 1 }],
      },
    };
    const env = setup('homeowner', initial);
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    expect(await screen.findByText('来源图片已删除')).toBeInTheDocument();
  });
});
```

Update the test harness in `Workspace.test.tsx` so non-GET requests are recorded even when the body is `FormData` — the existing harness already records `init` for every non-GET, so no change is needed.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/workflow/Workspace.test.tsx`
Expected: FAIL — no file input labelled `上传参考图片`

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/workflow/Workspace.tsx`:

- Import `newIdempotencyKey` and `Asset`: `import { ApiClient, ApiError, newIdempotencyKey, prepareWrite } from '../api';`
- Remove `SAMPLE_FIXTURES` and `registerSample`.
- Add an upload handler:

```tsx
  const uploadAsset = async (file: File) => {
    try {
      await client.upload(`/v1/projects/${projectId}/assets`, file, {
        expectedStateVersion: String(project.stateVersion),
        idempotencyKey: newIdempotencyKey(),
      });
      setNotice('图片已上传。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };
```

- Replace the sample section markup with:

```tsx
        {isHomeowner && (
          <section aria-label="参考图片">
            <h3>参考图片</h3>
            <label htmlFor="asset-upload">上传参考图片</label>
            <input
              id="asset-upload"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = '';
                if (file) void uploadAsset(file);
              }}
            />
            <p className="question-hint">
              支持 JPEG / PNG / WebP，单张不超过 10MB，最多 10 张。
            </p>
            <button type="button" onClick={() => void startAnalysis()}>
              启动分析
            </button>
          </section>
        )}
```

- Change the demo badge copy to:

```tsx
        <p className="demo-badge">真实图片 · 分析为模拟（第 2 步接入）</p>
```

- Add a thumbnail component and render it in the sidebar asset list. Add at module scope:

```tsx
function AssetThumb({ client, asset }: { client: ApiClient; asset: Asset }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (asset.deleted) return;
    let active = true;
    let objectUrl: string | null = null;
    client
      .blob(`/v1/projects/p1/assets/${asset.id}/content`)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (active) setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [client, asset.id, asset.deleted]);
  if (asset.deleted) return <span className="asset-missing">已删除</span>;
  return url ? <img className="asset-thumb" src={url} alt={asset.originalFilename} /> : null;
}
```

Note: the test harness returns the snapshot for every GET, so `blob()` receives JSON, which fails to construct a Blob URL gracefully via the `.catch`. Do not assert on `<img>` presence in unit tests; assert on the file input and the deleted-source label instead.

- Render the asset list (replacing the old `<ul className="assets">`) with:

```tsx
            <ul className="assets">
              {project.assets.map((asset: Asset) => (
                <li key={asset.id}>
                  <AssetThumb client={client} asset={asset} />
                  <span>
                    {asset.originalFilename}（{asset.mediaType}）
                  </span>
                  {isHomeowner && !asset.deleted && (
                    <button
                      type="button"
                      aria-label={`删除 ${asset.originalFilename}`}
                      onClick={() => void deleteAsset(asset)}
                    >
                      删除
                    </button>
                  )}
                </li>
              ))}
            </ul>
```

- Add the delete handler:

```tsx
  const deleteAsset = async (asset: Asset) => {
    if (!window.confirm(`确认删除 ${asset.originalFilename}？`)) return;
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/assets/${asset.id}`,
          'DELETE',
          project.stateVersion,
          {},
        ),
      );
      setNotice('图片已删除，相关观察仍会保留并标注来源已删除。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };
```

- In the sidebar preference list, mark observations whose image source is deleted. Build the set before rendering:

```tsx
  const deletedAssetIds = new Set(project.assets.filter((asset) => asset.deleted).map((asset) => asset.id));
```

and inside each attribute `<li>` after the value text:

```tsx
                  {attribute.evidence.some(
                    (evidence) =>
                      evidence.sourceType === 'image' && deletedAssetIds.has(evidence.sourceId),
                  ) && <span className="asset-missing">来源图片已删除</span>}
```

Add the `Asset` type import: `import type { Asset, Attribute, Conflict, ProjectSnapshot } from '../types';`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test && npm run build`
Expected: all tests pass and the build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/workflow/Workspace.tsx frontend/src/workflow/Workspace.test.tsx
git commit -m "feat: upload, preview and delete real reference images in the workspace"
```

---

### Task 11: Acceptance, runbooks and end-to-end

**Files:**
- Modify: `tests/acceptance/test_real_accounts_flow.py`
- Modify: `README.frontend.md`
- Modify: `README.backend.md`
- Modify: `frontend/e2e/auth-workflow.spec.ts` (only if it registers fixture assets)

- [ ] **Step 1: Update the two-account acceptance flow to upload real bytes**

In `TwoAccountDriver.run`, upload images with the owner token (advance `expectedStateVersion` from each response):

```python
        version = 0
        for index in range(3):
            response = self.api.post(
                f"/v1/projects/{self.project_id}/assets",
                headers=self.owner,
                data={"expectedStateVersion": str(version), "idempotencyKey": f"asset-{index}"},
                files={
                    "file": (
                        f"room-{index}.png",
                        image_bytes(),
                        "image/png",
                    )
                },
            )
            assert response.status_code == 201, response.text
            version = response.json()["stateVersion"]
```

Add `image_bytes` at module scope (same Pillow helper as Task 8) and keep the rest of the flow unchanged. Add an assertion that proposed observations reference the uploaded asset ids.

- [ ] **Step 2: Run the acceptance test**

Run: `uv run pytest tests/acceptance/test_real_accounts_flow.py -q`
Expected: `1 passed`

- [ ] **Step 3: Update the runbooks**

In `README.frontend.md` and `README.backend.md`, replace the "fixture records / no real upload" statements with: uploaded images are real and stored locally under `ALIGNSPACE_ASSET_DIR` (default `var/assets/`); analysis remains simulated until step 2; supported formats and limits; and how to reset the asset directory.

- [ ] **Step 4: Run every suite**

```bash
uv run pytest -q
uv run ruff check src tests
cd frontend && npm test && npm run build
```

Expected: all green. If `frontend/e2e` references the removed fixture endpoint, update it to `setInputFiles` on the upload input and rerun `npx playwright test` if the browsers are installed.

- [ ] **Step 5: Commit**

```bash
git add tests/acceptance README.frontend.md README.backend.md frontend/e2e
git commit -m "test: exercise real image uploads end to end and update runbooks"
```

---

## Self-Review

- **Spec coverage:** local FS behind `Storage` (Task 1), validation + EXIF strip (Task 2), migration (Task 3), multipart upload + views + wiring (Task 4), content read (Task 5), soft delete + active counts (Task 6), traceable mock vision (Task 7), fixture test migration (Task 8), frontend client (Task 9), frontend workspace (Task 10), acceptance + runbooks + e2e (Task 11). Non-goals (S3, real vision, thumbnails, batch upload) are untouched.
- **Placeholder scan:** all code steps contain concrete code; the only deferred judgement is the exact final test count in Task 8 and the optional `frontend/e2e` update, both stated explicitly with the command to run.
- **Type consistency:** `AssetView` fields (`originalFilename`, `sha256`, `deleted`, `deletedAt`) match the TypeScript `Asset` type; `AssetRef(id, media_type, sha256)` is used identically in `contracts.py`, `graph.py` and `service.py`; `newIdempotencyKey` is defined once in `api.ts` and reused by `prepareWrite` and the workspace.
