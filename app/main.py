from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, field_validator

from app import engine
from app.store import ProjectNotFoundError, ProjectStore, StaleStateError


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"
SCHEMA_PATH = ROOT / "schemas" / "design-brief.schema.json"
BUDGET_BANDS = {
    "under_15k_sgd",
    "15k_to_30k_sgd",
    "30k_to_50k_sgd",
    "over_50k_sgd",
    "prefer_not_to_say",
}


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    budgetBand: str
    housingType: str | None = Field(default=None, max_length=80)

    @field_validator("budgetBand")
    @classmethod
    def valid_budget(cls, value: str) -> str:
        if value not in BUDGET_BANDS:
            raise ValueError("Unsupported budget band")
        return value


class PreferencesUpdate(BaseModel):
    goals: list[str] = Field(default_factory=list, max_length=10)
    antiPreferences: list[str] = Field(default_factory=list, max_length=10)
    expectedStateVersion: int | None = None


class AnswerCreate(BaseModel):
    role: Literal["homeowner", "designer"]
    value: str = Field(min_length=1, max_length=80)
    expectedStateVersion: int | None = None


class ConstraintCreate(BaseModel):
    category: Literal["budget", "space", "function", "maintenance", "timeline", "safety", "regulatory", "availability", "other"]
    statement: str = Field(min_length=3, max_length=500)
    rationale: str = Field(default="", max_length=500)
    severity: Literal["advisory", "important", "critical"] = "important"
    affectedDimension: Literal["style", "colour", "material", "lighting", "layout", "mood", "function", "maintenance"] | None = None
    incompatibleValue: str | None = Field(default=None, max_length=80)
    expectedStateVersion: int | None = None


class AttributeReview(BaseModel):
    decision: Literal["confirm", "reject", "edit"]
    value: str | None = Field(default=None, max_length=80)
    expectedStateVersion: int | None = None


class ConflictResolution(BaseModel):
    resolution: str = Field(min_length=2, max_length=500)
    expectedStateVersion: int | None = None


class ApprovalCreate(BaseModel):
    role: Literal["homeowner", "designer"]
    actorId: str = Field(min_length=2, max_length=80)
    expectedStateVersion: int | None = None


def _present(state: dict[str, Any]) -> dict[str, Any]:
    return {**state, "nextQuestion": engine.next_question(state), "brief": engine.build_brief(state)}


def _has_valid_image_signature(content: bytes, content_type: str) -> bool:
    signatures = {
        "image/jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
        "image/png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": lambda value: len(value) >= 12 and value[:4] == b"RIFF" and value[8:12] == b"WEBP",
    }
    return signatures[content_type](content)


def create_app(database_path: str | Path | None = None, upload_dir: str | Path | None = None) -> FastAPI:
    application = FastAPI(
        title="AlignSpace API",
        version="0.1.0",
        description="Two-sided, evidence-backed design requirements alignment.",
    )
    application.state.store = ProjectStore(database_path)
    configured_uploads = upload_dir or os.getenv("ALIGNSPACE_UPLOAD_DIR", "data/uploads")
    application.state.upload_dir = Path(configured_uploads)
    application.state.upload_dir.mkdir(parents=True, exist_ok=True)

    @application.exception_handler(ProjectNotFoundError)
    async def not_found(_: Request, exc: ProjectNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "PROJECT_NOT_FOUND", "message": str(exc.args[0]), "recoverable": False}},
        )

    @application.exception_handler(StaleStateError)
    async def stale_state(_: Request, exc: StaleStateError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "BRIEF_VERSION_STALE", "message": str(exc), "recoverable": True}},
        )

    @application.exception_handler(ValueError)
    async def invalid_operation(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_OPERATION", "message": str(exc), "recoverable": True}},
        )

    def store(request: Request) -> ProjectStore:
        return request.app.state.store

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "alignspace"}

    @application.get("/api/projects")
    def list_projects(request: Request) -> list[dict[str, Any]]:
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "status": item["status"],
                "updatedAt": item["updatedAt"],
                "readiness": item["readiness"],
            }
            for item in store(request).list()
        ]

    @application.post("/api/projects", status_code=201)
    def create_project(data: ProjectCreate, request: Request) -> dict[str, Any]:
        state = engine.create_project(data.name, data.budgetBand, data.housingType)
        return _present(store(request).create(state, "homeowner"))

    @application.post("/api/demo", status_code=201)
    def create_demo(request: Request) -> dict[str, Any]:
        state = engine.create_project("Project Haven", "15k_to_30k_sgd", "HDB 4-room")
        state = engine.add_preferences(
            state,
            ["Create a comfortable room for family evenings", "Keep the space visually calm"],
            ["Cold grey surfaces", "Cluttered open shelving"],
        )
        for question_id, role, value in engine.demo_answers():
            state = engine.answer_question(state, question_id, role, value)
        return _present(store(request).create(state, "demo_seed"))

    @application.get("/api/projects/{project_id}")
    def get_project(project_id: str, request: Request) -> dict[str, Any]:
        return _present(store(request).get(project_id))

    @application.put("/api/projects/{project_id}/preferences")
    def update_preferences(project_id: str, data: PreferencesUpdate, request: Request) -> dict[str, Any]:
        state = store(request).mutate(
            project_id,
            "preferences_updated",
            "homeowner",
            lambda current: engine.add_preferences(current, data.goals, data.antiPreferences),
            data.expectedStateVersion,
        )
        return _present(state)

    @application.post("/api/projects/{project_id}/questions/{question_id}/answer")
    def submit_answer(project_id: str, question_id: str, data: AnswerCreate, request: Request) -> dict[str, Any]:
        state = store(request).mutate(
            project_id,
            "question_answered",
            data.role,
            lambda current: engine.answer_question(current, question_id, data.role, data.value),
            data.expectedStateVersion,
        )
        return _present(state)

    @application.post("/api/projects/{project_id}/analysis-runs")
    def run_analysis(project_id: str, request: Request) -> dict[str, Any]:
        state = store(request).mutate(
            project_id,
            "reference_analysis_completed",
            "vision_agent",
            engine.analyse_references,
        )
        return _present(state)

    @application.post("/api/projects/{project_id}/attributes/{attribute_id}/review")
    def review_attribute(project_id: str, attribute_id: str, data: AttributeReview, request: Request) -> dict[str, Any]:
        state = store(request).mutate(
            project_id,
            "attribute_reviewed",
            "homeowner",
            lambda current: engine.review_attribute(current, attribute_id, data.decision, data.value),
            data.expectedStateVersion,
        )
        return _present(state)

    @application.post("/api/projects/{project_id}/constraints", status_code=201)
    def create_constraint(project_id: str, data: ConstraintCreate, request: Request) -> dict[str, Any]:
        state = store(request).mutate(
            project_id,
            "designer_constraint_added",
            "designer",
            lambda current: engine.add_constraint(current, data.model_dump(exclude_none=True)),
            data.expectedStateVersion,
        )
        return _present(state)

    @application.post("/api/projects/{project_id}/conflicts/{conflict_id}/resolve")
    def resolve_conflict(project_id: str, conflict_id: str, data: ConflictResolution, request: Request) -> dict[str, Any]:
        state = store(request).mutate(
            project_id,
            "conflict_resolved",
            "homeowner_and_designer",
            lambda current: engine.resolve_conflict(current, conflict_id, data.resolution),
            data.expectedStateVersion,
        )
        return _present(state)

    @application.post("/api/projects/{project_id}/approvals")
    def approve_brief(project_id: str, data: ApprovalCreate, request: Request) -> dict[str, Any]:
        state = store(request).mutate(
            project_id,
            "brief_approved",
            data.role,
            lambda current: engine.approve(current, data.role, data.actorId),
            data.expectedStateVersion,
        )
        return _present(state)

    @application.get("/api/projects/{project_id}/brief")
    def get_brief(project_id: str, request: Request) -> dict[str, Any]:
        brief = engine.build_brief(store(request).get(project_id))
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema).iter_errors(brief), key=lambda item: list(item.path))
        if errors:
            raise HTTPException(
                status_code=500,
                detail={"code": "BRIEF_SCHEMA_INVALID", "errors": [error.message for error in errors]},
            )
        return brief

    @application.get("/api/projects/{project_id}/audit")
    def get_audit(project_id: str, request: Request, limit: int = 50) -> list[dict[str, Any]]:
        return store(request).audit(project_id, limit)

    @application.post("/api/projects/{project_id}/references", status_code=201)
    async def upload_reference(
        project_id: str,
        request: Request,
        file: UploadFile = File(...),
        note: str = Form(default=""),
        source_url: str = Form(default=""),
    ) -> dict[str, Any]:
        allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
        if file.content_type not in allowed:
            raise HTTPException(status_code=415, detail="Only JPG, PNG, and WebP images are supported")
        content = await file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Images must be no larger than 10 MB")
        if not content:
            raise HTTPException(status_code=422, detail="The uploaded image is empty")
        if not _has_valid_image_signature(content, file.content_type):
            raise HTTPException(status_code=422, detail="The file content does not match its declared image type")
        reference_id = f"reference_{uuid4().hex[:12]}"
        project_dir = request.app.state.upload_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        path = project_dir / f"{reference_id}{allowed[file.content_type]}"
        path.write_bytes(content)
        reference = {
            "id": reference_id,
            "filename": Path(file.filename or "reference").name,
            "contentType": file.content_type,
            "size": len(content),
            "storageKey": str(path.relative_to(request.app.state.upload_dir)),
            "note": note.strip()[:500],
            "sourceUrl": source_url.strip()[:1000] or None,
            "status": "uploaded",
            "consentConfirmed": True,
            "createdAt": engine.now_iso(),
        }
        state = store(request).mutate(
            project_id,
            "reference_uploaded",
            "homeowner",
            lambda current: engine.add_reference(current, reference),
        )
        return _present(state)

    application.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()
