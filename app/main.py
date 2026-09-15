from __future__ import annotations

import json
import os
import secrets
import io
import re
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator
from PIL import Image, ImageOps, UnidentifiedImageError

from app import engine
from app.store import ProjectNotFoundError, ProjectStore, StaleStateError
from app.access import AccessStore, digest
from app.gateway import Gateway, load_local_config
from app.discovery import Discovery

load_local_config()


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"
SCHEMA_PATH = ROOT / "schemas" / "design-brief.schema.json"
class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=2, max_length=80)
    housingType: str | None = Field(default=None, max_length=80)
    inspirationIds: list[str] = Field(default_factory=list, max_length=6)
    inspirationConsent: bool = False

class InspirationResolve(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=6)


class PreferencesUpdate(BaseModel):
    goals: list[str] = Field(default_factory=list, max_length=10)
    antiPreferences: list[str] = Field(default_factory=list, max_length=10)
    expectedStateVersion: int | None = None

    @field_validator('goals','antiPreferences')
    @classmethod
    def bounded_notes(cls, values):
        if any(len(value)>500 for value in values):
            raise ValueError('Each goal or must-avoid note must be at most 500 characters')
        return values


class AnswerCreate(BaseModel):
    role: Literal["homeowner", "designer"]
    value: str = Field(min_length=1, max_length=80)
    expectedStateVersion: int | None = None


class InterviewAction(BaseModel):
    role: Literal["homeowner", "designer"]
    action: Literal["continue", "pause"]
    expectedStateVersion: int = Field(ge=1)


class ConstraintCreate(BaseModel):
    category: Literal["space", "function", "maintenance", "timeline", "safety", "regulatory", "availability", "other"]
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
    expectedStateVersion: int = Field(ge=1)


class InviteClaim(BaseModel):
    token: str = Field(min_length=20, max_length=100)


class AnalysisCreate(BaseModel):
    mode: Literal['configured', 'offline'] = 'configured'
    expectedStateVersion: int | None = None


class ReferenceNoteCreate(BaseModel):
    note: str = Field(min_length=3, max_length=500)
    consent: bool = False
    expectedStateVersion: int | None = None


def _present(state: dict[str, Any]) -> dict[str, Any]:
    return {**state, "nextQuestion": engine.next_question(state), "brief": engine.build_brief(state),
            'questionsByRole':{role:engine.next_question(state,role) for role in ['homeowner','designer']},
            'detailQuestions': [q for q in engine.interview.DETAIL_QUESTIONS if any(a['questionId'] == q['id'] for a in state['answers'])]}


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
    for previous in application.state.store.list():
        if previous.get('schemaVersion') != '1.1.0':
            application.state.store.mutate(previous['id'], 'alignment_schema_updated', 'system',
                                           engine.migrate_project, previous['stateVersion'])
    application.state.discovery = Discovery(application.state.store.database_path)
    application.state.access = AccessStore(application.state.store.database_path)
    application.state.gateway = Gateway()
    configured_uploads = upload_dir or os.getenv("ALIGNSPACE_UPLOAD_DIR", "data/uploads")
    application.state.upload_dir = Path(configured_uploads)
    application.state.upload_dir.mkdir(parents=True, exist_ok=True)

    @application.middleware('http')
    async def session_access(request: Request, call_next):
        token = request.cookies.get('alignspace_session')
        new_session = not token or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token)
        if new_session:
            token = secrets.token_urlsafe(32)
        request.state.session = token
        request.state.actor = digest(token)[:20]
        request.state.role = None
        if request.method not in {'GET','HEAD','OPTIONS'}:
            origin = request.headers.get('origin')
            if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Cross-origin writes are not allowed'}, status_code=403)
        match = re.match(r'^/api/projects/([^/]+)(?:/|$)', request.url.path)
        if match:
            try:
                request.state.role = application.state.access.role(match[1], token)
            except HTTPException as error:
                return JSONResponse({'detail':error.detail}, status_code=error.status_code)
        response = await call_next(request)
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: https://d1hy6t2xeg0mdl.cloudfront.net https://api-neo.qanvast.com; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        elif request.url.path.startswith('/assets/') or request.url.path == '/':
            # Revalidate every asset: without this the browser may keep serving
            # a heuristically cached stylesheet or script after a deployment.
            response.headers['Cache-Control'] = 'no-cache'
        if new_session:
            response.set_cookie('alignspace_session', token, httponly=True, samesite='strict',
                secure=os.getenv('ALIGNSPACE_SECURE_COOKIES','false').lower() == 'true', max_age=604800)
        return response

    def require_role(request, *roles):
        if request.state.role not in roles:
            raise HTTPException(403, 'This action requires the '+ ' or '.join(roles)+' session')

    def created(state, request):
        application.state.access.register(state['id'], request.state.session)
        return {**_present(store(request).create(state, request.state.actor)), 'viewerRole':'homeowner'}

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

    @application.get('/api/inspiration/search')
    def search_inspiration(q: str = Query(default='', max_length=100),
                          style: Literal['All', 'Contemporary', 'Modern', 'Scandinavian', 'Minimalist', 'Industrial', 'Eclectic', 'Japandi', 'Wabi-Sabi'] = 'All',
                          kind: Literal['All', 'HDB', 'Condo', 'Landed'] = 'All'):
        return application.state.discovery.search(q, style, kind)

    @application.post('/api/inspiration/resolve')
    def resolve_inspiration(data: InspirationResolve):
        return {'projects': list(application.state.discovery.find(data.ids).values())}

    @application.get("/api/projects")
    def list_projects(request: Request) -> list[dict[str, Any]]:
        allowed = application.state.access.projects(request.state.session)
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "status": item["status"],
                "updatedAt": item["updatedAt"],
                "readiness": item["readiness"],
            }
            for item in store(request).list(allowed)
        ]

    @application.post("/api/projects", status_code=201)
    def create_project(data: ProjectCreate, request: Request) -> dict[str, Any]:
        homes = application.state.discovery.find(data.inspirationIds)
        if any(item not in homes for item in data.inspirationIds):
            raise HTTPException(422, 'Choose inspiration from the available Singapore collection')
        if data.inspirationIds and not data.inspirationConsent:
            raise HTTPException(422, 'Confirm that you want to add saved inspiration links to this project')
        state = engine.create_project(data.name, data.housingType)
        for item in dict.fromkeys(data.inspirationIds):
            home = homes[item]
            state = engine.add_reference(state, {
                'id': engine.new_id('reference'), 'filename': home['title'],
                'note': 'Saved for discussion. Tell your designer which details you like; saving a home does not confirm any preferences.',
                'status': 'catalogue_link', 'sourceUrl': home['sourceUrl'],
                'catalogueId': item, 'sourceCheckedAt': home.get('checkedAt'),
                'sourceDetails': {key: home.get(key) for key in ['flatType', 'area', 'year', 'designer', 'style', 'features', 'imageUrl']},
                'consentConfirmed': True, 'consentActor': request.state.actor,
                'createdAt': engine.now_iso(),
            })
        return created(state, request)

    @application.post("/api/demo", status_code=201)
    def create_demo(request: Request) -> dict[str, Any]:
        state = engine.create_project("Project Haven", "HDB 4-room")
        state = engine.add_preferences(
            state,
            ["Create a comfortable room for family evenings", "Keep the space visually calm"],
            ["Cold grey surfaces", "Cluttered open shelving"],
        )
        for question_id, role, value in engine.demo_answers():
            state = engine.answer_question(state, question_id, role, value)
        return created(state, request)

    @application.get("/api/projects/{project_id}")
    def get_project(project_id: str, request: Request) -> dict[str, Any]:
        return {**_present(store(request).get(project_id)), 'viewerRole':request.state.role}

    @application.post('/api/projects/{project_id}/invitations')
    def invite_designer(project_id: str, request: Request):
        token = application.state.access.invite(project_id, request.state.session)
        return {'invitationFragment':'#invite='+token, 'expiresInHours':24}

    @application.post('/api/invitations/claim')
    def claim_invitation(data: InviteClaim, request: Request):
        project_id = application.state.access.claim(data.token, request.state.session)
        return {'projectId':project_id}

    @application.post('/api/demo/start', status_code=201)
    def start_demo(request: Request) -> dict[str, Any]:
        state = engine.create_project('Project Haven — guided demo', 'HDB 4-room')
        state = engine.add_preferences(state, ['Comfortable family evenings', 'A calm, warm living room'], ['Cold grey surfaces'])
        state = engine.add_reference(state, {'id': engine.new_id('reference'), 'filename': 'Sample inspiration note', 'note': 'I like warm modern style and soft textiles', 'status': 'demo_note'})
        return created(state, request)

    @application.put('/api/projects/{project_id}/decisions/{question_id}')
    def revise_decision(project_id: str, question_id: str, data: AnswerCreate, request: Request):
        require_role(request, data.role)
        def change(current):
            # Manual revision is not another automated interview question.
            count = current['questionCount']
            current['answers'] = [a for a in current['answers'] if a['questionId'] != question_id]
            current['questionCount'] = 0
            engine.answer_question(current, question_id, data.role, data.value, revision=True)
            current['questionCount'] = count
            return current
        return _present(store(request).mutate(project_id, 'decision_revised', data.role, change, data.expectedStateVersion))

    @application.get('/api/decision-options')
    def decision_options():
        return engine.QUESTION_BANK

    @application.put("/api/projects/{project_id}/preferences")
    def update_preferences(project_id: str, data: PreferencesUpdate, request: Request) -> dict[str, Any]:
        require_role(request, 'homeowner')
        state = store(request).mutate(
            project_id,
            "preferences_updated",
            "homeowner",
            lambda current: engine.add_preferences(current, data.goals, data.antiPreferences),
            data.expectedStateVersion,
        )
        return _present(state)

    @application.post('/api/projects/{project_id}/interview')
    def update_interview(project_id: str, data: InterviewAction, request: Request):
        require_role(request, data.role)
        return _present(store(request).mutate(project_id, 'interview_' + data.action, data.role,
            lambda current: engine.set_interview(current, data.role, data.action), data.expectedStateVersion))

    @application.post("/api/projects/{project_id}/questions/{question_id}/answer")
    def submit_answer(project_id: str, question_id: str, data: AnswerCreate, request: Request) -> dict[str, Any]:
        require_role(request, data.role)
        state = store(request).mutate(
            project_id,
            "question_answered",
            data.role,
            lambda current: engine.answer_question(current, question_id, data.role, data.value),
            data.expectedStateVersion,
        )
        return _present(state)

    @application.post("/api/projects/{project_id}/analysis-runs")
    def run_analysis(project_id: str, request: Request, data: AnalysisCreate = AnalysisCreate()) -> dict[str, Any]:
        require_role(request, 'homeowner')
        snapshot = store(request).get(project_id)
        if data.expectedStateVersion is not None and snapshot['stateVersion'] != data.expectedStateVersion:
            raise StaleStateError('Project changed; refresh before analysing')
        gateway = application.state.gateway
        offline = data.mode == 'offline' or gateway.mode == 'offline'
        if not snapshot['references']:
            raise ValueError('Upload at least one reference')
        run_id = store(request).reserve_analysis(project_id)
        usage = {'mode':'offline_notes' if offline else 'gateway', 'promptVersion':gateway.prompt_version}
        try:
            if offline:
                mutation = engine.analyse_references
            else:
                proposals, usage = gateway.analyse(snapshot, application.state.upload_dir)
                mutation = lambda current: engine.apply_model_proposals(current, proposals)
            result = store(request).mutate(project_id, 'reference_analysis_completed', 'analysis_service', mutation, snapshot['stateVersion'])
            store(request).finish_analysis(run_id,'completed',usage)
            return {**_present(result), 'analysisSummary':usage}
        except Exception as error:
            store(request).finish_analysis(run_id,'failed', {**usage, 'errorType':type(error).__name__})
            raise

    @application.get('/api/projects/{project_id}/analysis-runs')
    def analysis_history(project_id: str, request: Request):
        return store(request).analysis_runs(project_id)

    @application.get('/api/runtime')
    def runtime():
        gateway = application.state.gateway
        return {'analysisMode':gateway.mode, 'imageAnalysisEnabled':gateway.images,
                'projectRunLimit':int(os.getenv('ALIGNSPACE_PROJECT_RUN_LIMIT','20'))}

    @application.post("/api/projects/{project_id}/attributes/{attribute_id}/review")
    def review_attribute(project_id: str, attribute_id: str, data: AttributeReview, request: Request) -> dict[str, Any]:
        require_role(request, 'homeowner')
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
        require_role(request, 'designer')
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
        require_role(request, 'designer')
        state = store(request).mutate(
            project_id,
            "conflict_resolved",
            request.state.actor,
            lambda current: engine.resolve_conflict(current, conflict_id, data.resolution),
            data.expectedStateVersion,
        )
        return _present(state)

    @application.post("/api/projects/{project_id}/approvals")
    def approve_brief(project_id: str, data: ApprovalCreate, request: Request) -> dict[str, Any]:
        require_role(request, data.role)
        state = store(request).mutate(
            project_id,
            "brief_approved",
            data.role,
            lambda current: engine.approve(current, request.state.role, request.state.actor),
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
        consent: bool = Form(default=False),
    ) -> dict[str, Any]:
        require_role(request, 'homeowner')
        project = store(request).get(project_id)
        if not consent:
            raise HTTPException(422, 'Confirm permission to upload and analyse this image')
        if len(project['references']) >= 10:
            raise HTTPException(422, 'Maximum 10 reference images per project')
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
        try:
            with Image.open(io.BytesIO(content)) as picture:
                if picture.width * picture.height > 20_000_000:
                    raise ValueError('Image exceeds 20 megapixels')
                picture.load()
                clean = ImageOps.exif_transpose(picture).convert('RGB')
                clean.thumbnail((1280,1280))
                output = io.BytesIO()
                clean.save(output,format='JPEG',quality=85)
                content = output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(422, 'Image must be decodable and no larger than 20 megapixels')
        reference_id = f"reference_{uuid4().hex[:12]}"
        project_dir = request.app.state.upload_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        path = project_dir / f"{reference_id}.jpg"
        path.write_bytes(content)
        reference = {
            "id": reference_id,
            "filename": Path(file.filename or "reference").name,
            "contentType": 'image/jpeg',
            "size": len(content),
            "storageKey": str(path.relative_to(request.app.state.upload_dir)),
            "note": note.strip()[:500],
            "sourceUrl": source_url.strip()[:1000] or None,
            "status": "uploaded",
            "consentConfirmed": True,
            "consentActor": request.state.actor,
            "createdAt": engine.now_iso(),
        }
        try:
            state = store(request).mutate(project_id,'reference_uploaded',request.state.actor,
                lambda current: engine.add_reference(current, reference), project['stateVersion'])
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return _present(state)

    @application.post('/api/projects/{project_id}/reference-notes', status_code=201)
    def reference_note(project_id: str, data: ReferenceNoteCreate, request: Request):
        require_role(request,'homeowner')
        if not data.consent:
            raise HTTPException(422,'Confirm permission to analyse this note')
        def mutation(current):
            if len(current['references']) >= 10:
                raise ValueError('Maximum 10 references per project')
            return engine.add_reference(current, {'id':engine.new_id('reference'),'filename':'Preference note',
                'note':data.note.strip(),'status':'note','consentConfirmed':True,'consentActor':request.state.actor,
                'createdAt':engine.now_iso()})
        return _present(store(request).mutate(project_id,'reference_note_added',request.state.actor,mutation,data.expectedStateVersion))

    @application.get('/api/projects/{project_id}/references/{reference_id}/image')
    def reference_image(project_id: str, reference_id: str, request: Request):
        project = store(request).get(project_id)
        reference = next((r for r in project['references'] if r['id']==reference_id and r.get('storageKey')), None)
        if not reference:
            raise HTTPException(404, 'Image not found')
        root = application.state.upload_dir.resolve()
        path = (root / reference['storageKey']).resolve()
        if not path.is_relative_to(root):
            raise HTTPException(404, 'Image not found')
        return FileResponse(path, media_type='image/jpeg')

    application.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()
