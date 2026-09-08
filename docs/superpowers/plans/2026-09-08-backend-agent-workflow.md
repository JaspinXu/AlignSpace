# AlignSpace Backend Agent Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally runnable, test-first backend that coordinates five logical agents through LangGraph, persists canonical project data in SQLite, exposes the approved FastAPI surface, and produces a reviewed, dual-approved design brief with deterministic mock providers.

**Architecture:** FastAPI delegates commands to an application service, which loads canonical domain state from SQLAlchemy repositories, invokes or resumes one LangGraph workflow, validates typed patches, and commits accepted changes with audit and idempotency records. SQLite domain records remain authoritative; LangGraph checkpoints persist workflow position and human interrupts but never bypass domain validation.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic 2, LangGraph 1.x, `langgraph-checkpoint-sqlite` 3.x, SQLAlchemy 2, SQLite, jsonschema, pytest, HTTPX, Ruff.

## Global Constraints

- Implement only the local backend MVP; do not add a frontend, generated room images, visual directions, or a Visualization Agent.
- Do not require network access, model credentials, AWS resources, or external services during tests.
- Use exactly five logical agent roles: Vision Analyst, Homeowner Interview Agent, Designer Agent, Alignment Agent, and Review Agent.
- Agents return typed results and patches; they never receive database sessions or persist canonical state directly.
- Explicit homeowner preferences may become `confirmed`; visual-only observations remain `proposed` until a human confirms them.
- Do not create records for ordinary unmentioned attributes. Use `unresolved` only for a tracked, meaningful decision.
- Keep homeowner preferences and designer constraints distinct and preserve provenance.
- Enforce at most 10 homeowner questions, at most 2 provider attempts per step, and at most 2 conflict-resolution loops.
- Require completeness of at least `0.85` and no open critical conflict before brief approval.
- Approve a project only when homeowner and designer approve the same brief version and SHA-256 content hash.
- Every accepted write must check `expectedStateVersion`, enforce idempotency, increment `stateVersion`, and append an audit event.
- Treat image content, metadata, user text, and retrieved text as untrusted evidence; block unsupported structural, electrical, regulatory, safety-critical, exact-price, and live-availability claims.
- Use the canonical brief contract at `schemas/design-brief.schema.json` and keep `examples/project-haven.design-brief.json` valid.

## File Structure

```text
pyproject.toml                         Python project, dependencies, pytest and Ruff configuration
uv.lock                               Reproducible dependency lock
src/alignspace/main.py                FastAPI application factory
src/alignspace/api/dependencies.py    Actor and application-container dependencies
src/alignspace/api/errors.py          Domain-to-HTTP error mapping
src/alignspace/api/routes/projects.py Project, membership, asset, and attribute endpoints
src/alignspace/api/routes/workflow.py Analysis, question, designer-review, and conflict endpoints
src/alignspace/api/routes/briefs.py    Brief edit and approval endpoints
src/alignspace/application/commands.py Actor context and write-envelope commands
src/alignspace/application/service.py  Authorization, idempotency, graph invocation, and transaction orchestration
src/alignspace/domain/enums.py         Stable domain enumerations
src/alignspace/domain/models.py        Evidence, attribute, constraint, question, conflict, brief, approval, and state models
src/alignspace/domain/patches.py       Typed patch operations and patch application
src/alignspace/domain/policies.py      State, safety, completeness, and approval invariants
src/alignspace/agents/contracts.py     Provider and agent protocols plus AgentBundle
src/alignspace/agents/vision.py        Vision Analyst
src/alignspace/agents/homeowner.py     Homeowner Interview Agent
src/alignspace/agents/designer.py      Designer Agent
src/alignspace/agents/alignment.py     Alignment Agent
src/alignspace/agents/review.py        Review Agent
src/alignspace/agents/question_selector.py Deterministic question ranking and repetition control
src/alignspace/providers/mock.py       Fixture-driven vision and language-model providers
src/alignspace/workflow/state.py       LangGraph runtime state
src/alignspace/workflow/graph.py       Nodes, conditional edges, and interrupts
src/alignspace/workflow/runtime.py     In-memory and SQLite checkpointer construction
src/alignspace/persistence/database.py Engine and session factory
src/alignspace/persistence/tables.py   SQLAlchemy tables
src/alignspace/persistence/repository.py Project-state assembly and persistence
src/alignspace/persistence/uow.py      Unit-of-work transaction boundary
tests/conftest.py                      Temporary database and application fixtures
tests/unit/                            Pure domain and agent tests
tests/integration/                     Repository and graph tests
tests/api/                             FastAPI contract tests
tests/acceptance/                      Complete backend workflow tests
```

---

### Task 1: Bootstrap the Python Project and Extend the Brief Contract

**Files:**
- Create: `pyproject.toml`
- Create: `src/alignspace/__init__.py`
- Create: `tests/unit/test_brief_schema.py`
- Modify: `schemas/design-brief.schema.json`
- Modify: `examples/project-haven.design-brief.json`
- Generate: `uv.lock`

**Interfaces:**
- Consumes: Existing JSON Schema and demo brief.
- Produces: Python 3.12 project environment and a brief contract where every attribute has `targetElement: str`.

- [ ] **Step 1: Add project configuration and the failing schema test**

```toml
[project]
name = "alignspace"
version = "0.1.0"
description = "Reference-driven homeowner and designer alignment backend"
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi>=0.116,<1",
  "langgraph>=1.1,<2",
  "langgraph-checkpoint-sqlite>=3.1,<4",
  "pydantic>=2.11,<3",
  "sqlalchemy>=2.0,<3",
  "uvicorn>=0.35,<1",
]

[project.optional-dependencies]
dev = [
  "httpx>=0.28,<1",
  "jsonschema>=4.25,<5",
  "pytest>=8.4,<9",
  "pytest-cov>=7,<8",
  "ruff>=0.12,<1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/alignspace"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

```python
# tests/unit/test_brief_schema.py
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
```

- [ ] **Step 2: Run the test and verify the intended failure**

Run: `uv sync --extra dev && uv run pytest tests/unit/test_brief_schema.py -v`  
Expected: the target-element and conflict-control contract tests fail because the required fields are absent.

- [ ] **Step 3: Add `targetElement` to the schema and example**

Update the attribute contract to contain this required property:

```json
"required": ["id", "targetElement", "dimension", "value", "status", "confidence", "evidence", "actor"],
"properties": {
  "targetElement": { "type": "string", "minLength": 1 }
}
```

Add `severity` to the conflict contract using the existing `advisory`, `important`, and `critical` values. Add `resolutionAttempts` as an integer with minimum `0`. Require both fields and add these exact values to the example:

```json
{ "id": "attr-pale-oak", "targetElement": "general_finish" }
{ "id": "attr-warm-light", "targetElement": "lighting" }
{ "id": "attr-light-sofa", "targetElement": "sofa" }
{ "id": "conflict-sofa-maintenance", "severity": "important", "resolutionAttempts": 0 }
```

Preserve all existing fields beside each added `targetElement`.

- [ ] **Step 4: Verify schema tests and formatting**

Run: `uv run pytest tests/unit/test_brief_schema.py -v && uv run ruff check src tests`  
Expected: 3 tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit the contract foundation**

```bash
git add pyproject.toml uv.lock src/alignspace/__init__.py tests/unit/test_brief_schema.py schemas/design-brief.schema.json examples/project-haven.design-brief.json
git commit -m "build: bootstrap backend contract"
```

---

### Task 2: Define Canonical Domain Models and Sparse Attribute Rules

**Files:**
- Create: `src/alignspace/domain/__init__.py`
- Create: `src/alignspace/domain/enums.py`
- Create: `src/alignspace/domain/models.py`
- Create: `src/alignspace/domain/patches.py`
- Create: `src/alignspace/domain/policies.py`
- Create: `tests/unit/domain/test_attribute_policies.py`
- Create: `tests/unit/domain/test_patch_versioning.py`

**Interfaces:**
- Consumes: `targetElement` brief contract from Task 1.
- Produces: `ProjectState`, `StatePatch`, `apply_patch(state, patch)`, `DomainRuleError`, and `StaleStateError`.

- [ ] **Step 1: Write failing tests for sparse storage and actor authority**

```python
# tests/unit/domain/test_attribute_policies.py
from uuid import uuid4

import pytest

from alignspace.domain.enums import ActorKind, AttributeStatus, EvidenceSource
from alignspace.domain.models import Attribute, Evidence, ProjectState
from alignspace.domain.patches import StatePatch, UpsertAttribute, apply_patch
from alignspace.domain.policies import DomainRuleError


def make_attribute(actor: ActorKind, status: AttributeStatus) -> Attribute:
    source_type = (
        EvidenceSource.IMAGE
        if actor == ActorKind.VISION_AGENT
        else EvidenceSource.HOMEOWNER_ANSWER
    )
    return Attribute(
        id=str(uuid4()),
        target_element="wall",
        dimension="colour",
        value="warm beige",
        status=status,
        confidence=1.0 if actor == ActorKind.HOMEOWNER else 0.82,
        evidence=[Evidence(source_type=source_type, source_id="source-1", description="Recorded evidence")],
        actor=actor,
    )


def test_unmentioned_attribute_is_not_materialised() -> None:
    state = ProjectState(project_id="project-1")
    assert state.attributes == []


def test_homeowner_can_confirm_explicit_preference() -> None:
    state = ProjectState(project_id="project-1")
    attribute = make_attribute(ActorKind.HOMEOWNER, AttributeStatus.CONFIRMED)
    patch = StatePatch(expected_state_version=0, operations=[UpsertAttribute(attribute=attribute)])
    updated = apply_patch(state, patch)
    assert updated.attributes == [attribute]
    assert updated.state_version == 1


def test_vision_agent_cannot_confirm_preference() -> None:
    state = ProjectState(project_id="project-1")
    attribute = make_attribute(ActorKind.VISION_AGENT, AttributeStatus.CONFIRMED)
    patch = StatePatch(expected_state_version=0, operations=[UpsertAttribute(attribute=attribute)])
    with pytest.raises(DomainRuleError, match="vision observations must remain proposed"):
        apply_patch(state, patch)
```

```python
# tests/unit/domain/test_patch_versioning.py
import pytest

from alignspace.domain.models import ProjectState
from alignspace.domain.patches import StatePatch, apply_patch
from alignspace.domain.policies import StaleStateError


def test_stale_patch_is_rejected() -> None:
    state = ProjectState(project_id="project-1", state_version=4)
    patch = StatePatch(expected_state_version=3, operations=[])
    with pytest.raises(StaleStateError, match="expected version 3, current version 4"):
        apply_patch(state, patch)
```

- [ ] **Step 2: Run the tests and verify missing-domain failures**

Run: `uv run pytest tests/unit/domain -v`  
Expected: collection fails with `ModuleNotFoundError: No module named 'alignspace.domain'`.

- [ ] **Step 3: Implement the domain vocabulary and patch policy**

Use string enums for project status, actor, attribute status, evidence source, role, conflict status, next action, and review decision. Define Pydantic models with snake-case Python fields and camel-case aliases for API output.

The core patch implementation must have these exact signatures:

```python
# src/alignspace/domain/patches.py
from typing import Literal

from pydantic import BaseModel

from alignspace.domain.enums import ActorKind, AttributeStatus
from alignspace.domain.models import Attribute, ProjectState
from alignspace.domain.policies import DomainRuleError, StaleStateError


class UpsertAttribute(BaseModel):
    op: Literal["upsert_attribute"] = "upsert_attribute"
    attribute: Attribute


PatchOperation = UpsertAttribute


class StatePatch(BaseModel):
    expected_state_version: int
    operations: list[PatchOperation]


def apply_patch(state: ProjectState, patch: StatePatch) -> ProjectState:
    if patch.expected_state_version != state.state_version:
        raise StaleStateError(
            f"expected version {patch.expected_state_version}, current version {state.state_version}"
        )
    attributes = list(state.attributes)
    for operation in patch.operations:
        attribute = operation.attribute
        if attribute.actor == ActorKind.VISION_AGENT and attribute.status != AttributeStatus.PROPOSED:
            raise DomainRuleError("vision observations must remain proposed")
        attributes = [item for item in attributes if item.id != attribute.id]
        attributes.append(attribute)
    return state.model_copy(update={"attributes": attributes, "state_version": state.state_version + 1})
```

`ProjectState` must default every collection to an empty list with `Field(default_factory=list)` so absence never creates records. `Evidence` and `Attribute` must expose the fields used in the tests and validate confidence from `0` through `1`.

- [ ] **Step 4: Run domain tests and Ruff**

Run: `uv run pytest tests/unit/domain -v && uv run ruff check src tests`  
Expected: all domain tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit domain semantics**

```bash
git add src/alignspace/domain tests/unit/domain
git commit -m "feat: define canonical project state"
```

---

### Task 3: Add Questions, Constraints, Conflicts, Briefs, and Approval Invariants

**Files:**
- Modify: `src/alignspace/domain/enums.py`
- Modify: `src/alignspace/domain/models.py`
- Modify: `src/alignspace/domain/patches.py`
- Modify: `src/alignspace/domain/policies.py`
- Create: `tests/unit/domain/test_alignment_policies.py`
- Create: `tests/unit/domain/test_approval_policy.py`

**Interfaces:**
- Consumes: `ProjectState` and `StatePatch` from Task 2.
- Produces: `Question`, `Constraint`, `Conflict`, `BriefVersion`, `Approval`, typed upsert operations, `calculate_completeness(state)`, `can_draft_brief(state)`, and `can_approve(state, brief)`.

- [ ] **Step 1: Write failing tests for question limits and dual approval**

```python
# tests/unit/domain/test_alignment_policies.py
from alignspace.domain.models import ProjectState, Question
from alignspace.domain.enums import ActorKind, AttributeStatus, ConflictStatus, ConstraintSeverity, EvidenceSource
from alignspace.domain.models import Attribute, Conflict, Evidence
from alignspace.domain.policies import DomainRuleError, add_question, calculate_completeness, can_draft_brief, record_conflict_attempt


def test_eleventh_homeowner_question_is_rejected() -> None:
    state = ProjectState(
        project_id="project-1",
        questions=[Question(id=f"q-{index}", target_role="homeowner", text=f"Question {index}") for index in range(10)],
    )
    question = Question(id="q-10", target_role="homeowner", text="Question 10")
    try:
        add_question(state, question)
    except DomainRuleError as error:
        assert str(error) == "homeowner question budget exhausted"
    else:
        raise AssertionError("Expected the homeowner question budget to be enforced")


def test_brief_requires_completeness_threshold() -> None:
    state = ProjectState(project_id="project-1", completeness=0.84)
    assert can_draft_brief(state) is False


def test_completeness_uses_required_dimensions_without_materialising_missing_rows() -> None:
    attributes = [
        Attribute(
            id=f"attr-{dimension}",
            target_element="room",
            dimension=dimension,
            value=f"decided {dimension}",
            status=AttributeStatus.CONFIRMED,
            confidence=1,
            evidence=[Evidence(source_type=EvidenceSource.HOMEOWNER_ANSWER, source_id=f"answer-{dimension}", description="Explicit decision")],
            actor=ActorKind.HOMEOWNER,
        )
        for dimension in ["style", "colour", "material", "lighting"]
    ]
    state = ProjectState(project_id="project-1", attributes=attributes)
    assert calculate_completeness(state) == 0.5
    assert len(state.attributes) == 4


def test_second_unsuccessful_conflict_attempt_escalates() -> None:
    conflict = Conflict(
        id="c-1",
        type="preference_vs_constraint",
        summary="Material exceeds budget",
        impact="A lower-cost alternative is required",
        status=ConflictStatus.OPEN,
        severity=ConstraintSeverity.IMPORTANT,
        resolution_attempts=1,
    )
    updated = record_conflict_attempt(conflict)
    assert updated.resolution_attempts == 2
    assert updated.status == ConflictStatus.ESCALATED
```

```python
# tests/unit/domain/test_approval_policy.py
from alignspace.domain.enums import ConflictStatus, ConstraintSeverity, Role
from alignspace.domain.models import Approval, BriefVersion, Conflict, ProjectState
from alignspace.domain.policies import can_approve


def test_same_version_and_hash_from_both_roles_is_required() -> None:
    brief = BriefVersion(version=2, content_hash="abc", payload={}, completeness=0.9)
    state = ProjectState(
        project_id="project-1",
        approvals=[
            Approval(role=Role.HOMEOWNER, actor_id="h-1", brief_version=2, content_hash="abc"),
            Approval(role=Role.DESIGNER, actor_id="d-1", brief_version=2, content_hash="abc"),
        ],
    )
    assert can_approve(state, brief) is True


def test_open_critical_conflict_blocks_approval() -> None:
    brief = BriefVersion(version=1, content_hash="abc", payload={}, completeness=0.9)
    state = ProjectState(
        project_id="project-1",
        conflicts=[
            Conflict(
                id="c-1",
                type="preference_vs_constraint",
                summary="Unsafe wall change",
                impact="Professional review required",
                status=ConflictStatus.OPEN,
                severity=ConstraintSeverity.CRITICAL,
            )
        ],
    )
    assert can_approve(state, brief) is False
```

- [ ] **Step 2: Run the tests and verify missing-model failures**

Run: `uv run pytest tests/unit/domain/test_alignment_policies.py tests/unit/domain/test_approval_policy.py -v`  
Expected: collection fails because the new domain models and policy functions are not defined.

- [ ] **Step 3: Implement workflow entities and deterministic invariants**

Add typed models using these required fields:

```python
class Question(BaseModel):
    id: str
    target_role: Role
    text: str
    rationale: str = ""
    options: list[str] = Field(default_factory=list)
    answer: str | None = None
    repetition_fingerprint: str = ""


class BriefVersion(BaseModel):
    version: int
    content_hash: str
    payload: dict[str, object]
    completeness: float = Field(ge=0, le=1)


class Approval(BaseModel):
    role: Role
    actor_id: str
    brief_version: int
    content_hash: str
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

Extend `ProjectState` with typed `constraints`, `questions`, `conflicts`, `brief_versions`, `approvals`, `completeness`, `current_node`, and `wait_reason` fields. Replace the Task 2 `PatchOperation` alias with an `Annotated` discriminated union containing the attribute, constraint, question, conflict, brief, and approval operation models.

Implement `add_question`, `record_conflict_attempt`, `can_draft_brief`, and `can_approve` exactly as follows:

```python
def add_question(state: ProjectState, question: Question) -> ProjectState:
    count = sum(item.target_role == Role.HOMEOWNER for item in state.questions)
    if question.target_role == Role.HOMEOWNER and count >= 10:
        raise DomainRuleError("homeowner question budget exhausted")
    return state.model_copy(update={"questions": [*state.questions, question]})


REQUIRED_DIMENSIONS = frozenset(
    {"style", "colour", "material", "lighting", "layout", "furniture", "mood", "function"}
)
DECIDED_STATUSES = frozenset(
    {AttributeStatus.CONFIRMED, AttributeStatus.UNRESOLVED, AttributeStatus.NOT_APPLICABLE}
)


def calculate_completeness(state: ProjectState) -> float:
    decided = {
        attribute.dimension
        for attribute in state.attributes
        if attribute.status in DECIDED_STATUSES
    }
    return len(decided & REQUIRED_DIMENSIONS) / len(REQUIRED_DIMENSIONS)


def can_draft_brief(state: ProjectState) -> bool:
    critical_open = any(
        item.status == ConflictStatus.OPEN and item.severity == ConstraintSeverity.CRITICAL
        for item in state.conflicts
    )
    return state.completeness >= 0.85 and not critical_open


def record_conflict_attempt(conflict: Conflict) -> Conflict:
    attempts = conflict.resolution_attempts + 1
    status = ConflictStatus.ESCALATED if attempts >= 2 else ConflictStatus.OPEN
    return conflict.model_copy(update={"resolution_attempts": attempts, "status": status})


def can_approve(state: ProjectState, brief: BriefVersion) -> bool:
    if not can_draft_brief(state):
        return False
    approved_roles = {
        item.role
        for item in state.approvals
        if item.brief_version == brief.version and item.content_hash == brief.content_hash
    }
    return approved_roles == {Role.HOMEOWNER, Role.DESIGNER}
```

- [ ] **Step 4: Run the complete domain suite**

Run: `uv run pytest tests/unit/domain -v && uv run ruff check src tests`  
Expected: all domain tests pass.

- [ ] **Step 5: Commit the workflow entities**

```bash
git add src/alignspace/domain tests/unit/domain
git commit -m "feat: enforce alignment and approval rules"
```

---

### Task 4: Implement SQLite Persistence, Optimistic Locking, and Idempotency

**Files:**
- Create: `src/alignspace/persistence/__init__.py`
- Create: `src/alignspace/persistence/database.py`
- Create: `src/alignspace/persistence/tables.py`
- Create: `src/alignspace/persistence/repository.py`
- Create: `src/alignspace/persistence/uow.py`
- Create: `tests/integration/persistence/test_repository.py`
- Create: `tests/integration/persistence/test_concurrency.py`

**Interfaces:**
- Consumes: `ProjectState` and domain entities from Tasks 2–3.
- Produces: `create_engine_and_session(url: str)`, `ProjectRepository(session)`, `SqlAlchemyUnitOfWork(session_factory)`, `uow.projects.load(project_id: str) -> ProjectState`, `uow.projects.save(state: ProjectState, expected_version: int) -> None`, and idempotency lookups.

- [ ] **Step 1: Write failing persistence tests**

```python
# tests/integration/persistence/test_repository.py
from alignspace.domain.models import ProjectState
from alignspace.persistence.database import create_engine_and_session
from alignspace.persistence.uow import SqlAlchemyUnitOfWork


def test_project_state_round_trips_through_sqlite(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")
    original = ProjectState(project_id="project-1", state_version=0)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(original)
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        loaded = uow.projects.load("project-1")
    assert loaded == original
    engine.dispose()
```

```python
# tests/integration/persistence/test_concurrency.py
import pytest

from alignspace.domain.models import ProjectState
from alignspace.domain.policies import StaleStateError
from alignspace.persistence.database import create_engine_and_session
from alignspace.persistence.uow import SqlAlchemyUnitOfWork


def test_repository_rejects_stale_version(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(ProjectState(project_id="project-1"))
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        current = uow.projects.load("project-1")
        uow.projects.save(current.model_copy(update={"state_version": 1}), expected_version=0)
        uow.commit()
    with pytest.raises(StaleStateError):
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            uow.projects.save(current.model_copy(update={"state_version": 1}), expected_version=0)
            uow.commit()
    engine.dispose()
```

- [ ] **Step 2: Run tests and verify missing-persistence failures**

Run: `uv run pytest tests/integration/persistence -v`  
Expected: collection fails with `ModuleNotFoundError: No module named 'alignspace.persistence'`.

- [ ] **Step 3: Implement tables and repository boundaries**

Create SQLAlchemy tables for `projects`, `project_members`, `image_assets`, `attributes`, `constraints`, `questions`, `conflicts`, `brief_versions`, `approvals`, `audit_events`, and `idempotency_records`. Store typed entity payloads in SQLite JSON columns while retaining stable IDs and `project_id` columns for isolation and deletion.

Use this engine factory:

```python
# src/alignspace/persistence/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from alignspace.persistence.tables import Base


def create_engine_and_session(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
```

`ProjectRepository.save` must perform a conditional update equivalent to:

```python
result = session.execute(
    update(ProjectRow)
    .where(ProjectRow.id == state.project_id, ProjectRow.state_version == expected_version)
    .values(state_version=state.state_version, status=state.status.value)
)
if result.rowcount != 1:
    raise StaleStateError(f"project {state.project_id} changed concurrently")
```

Within the same unit of work, replace or upsert each typed entity table from the supplied `ProjectState`; do not store a duplicate whole-state JSON snapshot in `projects`. `ProjectRepository.load` must assemble the projection from the project row and typed entity rows. `ProjectRepository` never commits or rolls back; `SqlAlchemyUnitOfWork.commit()` owns the transaction boundary and rolls back on context-manager exit when commit did not succeed. Persist an audit row with each accepted state write. Persist idempotency key, canonical request hash, response payload, and resulting version; return the stored response for an identical replay and raise `IdempotencyConflictError` for different content.

- [ ] **Step 4: Run persistence tests and inspect table creation**

Run: `uv run pytest tests/integration/persistence -v && uv run ruff check src tests`  
Expected: repository round-trip and stale-write tests pass.

- [ ] **Step 5: Commit persistence**

```bash
git add src/alignspace/persistence tests/integration/persistence
git commit -m "feat: persist canonical project state"
```

---

### Task 5: Implement Deterministic Providers and the Five Agent Contracts

**Files:**
- Create: `src/alignspace/agents/__init__.py`
- Create: `src/alignspace/agents/contracts.py`
- Create: `src/alignspace/agents/vision.py`
- Create: `src/alignspace/agents/homeowner.py`
- Create: `src/alignspace/agents/designer.py`
- Create: `src/alignspace/agents/alignment.py`
- Create: `src/alignspace/agents/review.py`
- Create: `src/alignspace/agents/question_selector.py`
- Create: `src/alignspace/providers/__init__.py`
- Create: `src/alignspace/providers/mock.py`
- Create: `src/alignspace/providers/validated.py`
- Create: `tests/unit/agents/test_agents.py`
- Create: `tests/unit/agents/test_question_selector.py`

**Interfaces:**
- Consumes: Domain state and patch models from Tasks 2–3.
- Produces: `AgentResult`, `AgentBundle`, provider protocols, five `run(state: ProjectState) -> AgentResult` methods, `QuestionCandidate`, and `select_question(candidates: list[QuestionCandidate], history: set[str]) -> QuestionCandidate | None`.

- [ ] **Step 1: Write failing agent and ranking tests**

```python
# tests/unit/agents/test_question_selector.py
from alignspace.agents.question_selector import QuestionCandidate, select_question


def test_selector_prefers_high_information_non_repeated_question() -> None:
    candidates = [
        QuestionCandidate(id="wall-material", uncertainty=0.9, impact=0.8, conflict_relevance=0.8, coverage_gap=0.7, effort=0.2, fingerprint="wall-material"),
        QuestionCandidate(id="chair-colour", uncertainty=0.4, impact=0.2, conflict_relevance=0.0, coverage_gap=0.3, effort=0.2, fingerprint="chair-colour"),
    ]
    selected = select_question(candidates, history={"chair-colour"})
    assert selected.id == "wall-material"


def test_selector_returns_none_when_every_candidate_repeats() -> None:
    candidate = QuestionCandidate(id="wall", uncertainty=1, impact=1, conflict_relevance=1, coverage_gap=1, effort=0, fingerprint="wall")
    assert select_question([candidate], history={"wall"}) is None
```

```python
# tests/unit/agents/test_agents.py
from alignspace.agents.contracts import AgentBundle
from alignspace.domain.enums import AttributeStatus, NextAction
from alignspace.domain.models import ProjectState
from alignspace.providers.mock import build_mock_agents


def test_mock_vision_returns_proposals_only() -> None:
    agents: AgentBundle = build_mock_agents()
    result = agents.vision.run(ProjectState(project_id="project-1"))
    assert result.patches
    assert all(operation.attribute.status == AttributeStatus.PROPOSED for operation in result.patches)


def test_alignment_requests_homeowner_when_visual_proposals_are_unconfirmed() -> None:
    agents = build_mock_agents()
    state = agents.vision.run(ProjectState(project_id="project-1")).state
    result = agents.alignment.run(state)
    assert result.next_action == NextAction.ASK_HOMEOWNER


def test_invalid_provider_output_is_repaired_once() -> None:
    from pydantic import BaseModel

    from alignspace.providers.mock import SequenceLanguageProvider
    from alignspace.providers.validated import generate_validated

    class Output(BaseModel):
        value: str

    provider = SequenceLanguageProvider(outputs=[{"wrong": "shape"}, {"value": "valid"}])
    result = generate_validated(provider, "test", {}, Output)
    assert result.value == "valid"
    assert provider.calls == 2
```

- [ ] **Step 2: Run tests and verify missing-agent failures**

Run: `uv run pytest tests/unit/agents -v`  
Expected: collection fails because the agent and provider modules do not exist.

- [ ] **Step 3: Implement protocols, deterministic fixtures, and agents**

Define these stable interfaces:

```python
class VisionProvider(Protocol):
    def analyze(self, state: ProjectState) -> list[Attribute]:
        raise NotImplementedError


class LanguageModelProvider(Protocol):
    def generate(self, task: str, payload: dict[str, object]) -> dict[str, object]:
        raise NotImplementedError


class AgentResult(BaseModel):
    state: ProjectState
    patches: list[PatchOperation] = Field(default_factory=list)
    next_action: NextAction | None = None
    review_decision: ReviewDecision | None = None


class AgentBundle(NamedTuple):
    vision: VisionAnalyst
    homeowner: HomeownerInterviewAgent
    designer: DesignerAgent
    alignment: AlignmentAgent
    review: ReviewAgent
```

The mock vision provider returns wall color, chair material, floor color, and warm lighting as `proposed` observations with image evidence. The mock interview agent first asks which additional image elements matter, then asks one selected detail question. The designer agent accepts explicit fixture feedback only. The alignment agent emits one of the approved `NextAction` values. The review agent always runs deterministic policy and schema gates before returning `PASS`.

`generate_validated(provider, task, payload, result_model)` calls the provider once, validates with the requested Pydantic model, and makes exactly one repair attempt after a validation error. It raises `ProviderOutputError` after the second invalid result. `SequenceLanguageProvider` records its call count and returns configured outputs in order so the retry rule remains network-free and deterministic.

Implement the score exactly as:

```python
def score(candidate: QuestionCandidate) -> float:
    return (
        0.35 * candidate.uncertainty
        + 0.30 * candidate.impact
        + 0.20 * candidate.conflict_relevance
        + 0.10 * candidate.coverage_gap
        - 0.05 * candidate.effort
    )
```

Exclude candidates whose fingerprint appears in history before taking the maximum score.

- [ ] **Step 4: Run agent tests**

Run: `uv run pytest tests/unit/agents -v && uv run ruff check src tests`  
Expected: all agent tests pass.

- [ ] **Step 5: Commit the five logical agents**

```bash
git add src/alignspace/agents src/alignspace/providers tests/unit/agents
git commit -m "feat: add deterministic agent roles"
```

---

### Task 6: Build the LangGraph Workflow with Human Interrupts

**Files:**
- Create: `src/alignspace/workflow/__init__.py`
- Create: `src/alignspace/workflow/state.py`
- Create: `src/alignspace/workflow/graph.py`
- Create: `src/alignspace/workflow/runtime.py`
- Create: `tests/integration/workflow/test_graph.py`
- Create: `tests/integration/workflow/test_resume.py`

**Interfaces:**
- Consumes: `AgentBundle`, `ProjectState`, `AgentResult`, and patch policies.
- Produces: `WorkflowState`, `build_graph(agents, checkpointer)`, `memory_graph(agents)`, and `sqlite_graph(agents, path)`.

- [ ] **Step 1: Write failing graph and interrupt tests**

```python
# tests/integration/workflow/test_graph.py
from alignspace.providers.mock import build_mock_agents
from alignspace.workflow.runtime import memory_graph


def test_graph_starts_with_vision_and_pauses_for_homeowner() -> None:
    graph = memory_graph(build_mock_agents())
    config = {"configurable": {"thread_id": "project-1"}}
    result = graph.invoke({"project_id": "project-1"}, config=config)
    assert result["project_state"]["attributes"]
    assert result["__interrupt__"][0].value["waitReason"] == "homeowner"
```

```python
# tests/integration/workflow/test_resume.py
from langgraph.types import Command

from alignspace.providers.mock import build_mock_agents
from alignspace.workflow.runtime import memory_graph


def test_homeowner_answer_resumes_same_thread() -> None:
    graph = memory_graph(build_mock_agents())
    config = {"configurable": {"thread_id": "project-1"}}
    graph.invoke({"project_id": "project-1"}, config=config)
    resumed = graph.invoke(
        Command(resume={"answer": "I also like the warm lighting"}),
        config=config,
    )
    assert resumed["project_state"]["state_version"] >= 1
```

- [ ] **Step 2: Run tests and verify missing-workflow failures**

Run: `uv run pytest tests/integration/workflow -v`  
Expected: collection fails because `alignspace.workflow` is missing.

- [ ] **Step 3: Implement graph state, nodes, routes, and checkpointers**

Define graph state as JSON-serializable values:

```python
class WorkflowState(TypedDict, total=False):
    project_id: str
    project_state: dict[str, object]
    next_action: str
    pending_question: dict[str, object]
    review_decision: str
```

Build the graph with these node names:

```text
vision_analysis
homeowner_interview
wait_homeowner
designer_review
wait_designer
alignment
wait_professional
draft_brief
review
awaiting_approval
```

The wait nodes must call `interrupt()` with JSON-serializable payloads. Resume with `Command(resume=payload)` and the same `thread_id`. Keep all code before `interrupt()` free of non-idempotent side effects because LangGraph restarts the node on resume.

Use `InMemorySaver` in tests and this synchronous SQLite construction for local execution:

```python
def sqlite_graph(agents: AgentBundle, path: str):
    connection = sqlite3.connect(path, check_same_thread=False)
    checkpointer = SqliteSaver(connection)
    return build_graph(agents, checkpointer)
```

Conditional routing from `alignment` must map `ask_homeowner`, `ask_designer`, `request_professional_review`, `draft_brief`, and `stop_unresolved` to explicit nodes. Conditional routing from `review` maps repair/downgrade/redact back to alignment, escalation to professional wait, and pass to awaiting approval.

- [ ] **Step 4: Run workflow tests**

Run: `uv run pytest tests/integration/workflow -v && uv run ruff check src tests`  
Expected: graph pauses, resumes on the same thread, and passes all integration tests.

- [ ] **Step 5: Commit graph orchestration**

```bash
git add src/alignspace/workflow tests/integration/workflow
git commit -m "feat: orchestrate agents with LangGraph"
```

---

### Task 7: Implement the Application Service and Transactional Write Flow

**Files:**
- Create: `src/alignspace/application/__init__.py`
- Create: `src/alignspace/application/commands.py`
- Create: `src/alignspace/application/service.py`
- Create: `tests/unit/application/test_workflow_service.py`
- Create: `tests/integration/application/test_idempotent_write.py`

**Interfaces:**
- Consumes: Repository/UoW from Task 4 and compiled graph from Task 6.
- Produces: `ActorContext`, `WriteEnvelope[T]`, `WorkflowService.start_analysis(project_id: str, actor: ActorContext, envelope: WriteEnvelope[dict[str, object]]) -> WorkflowResponse`, `WorkflowService.resume(project_id: str, actor: ActorContext, wait_reason: str, envelope: WriteEnvelope[dict[str, object]]) -> WorkflowResponse`, and `WorkflowService.edit_attribute(project_id: str, attribute_id: str, actor: ActorContext, envelope: WriteEnvelope[dict[str, object]]) -> WorkflowResponse`.

- [ ] **Step 1: Write failing service tests**

```python
# tests/unit/application/test_workflow_service.py
import pytest

from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.service import AuthorizationError, WorkflowService
from alignspace.domain.enums import Role


def test_designer_cannot_answer_homeowner_question(service: WorkflowService) -> None:
    actor = ActorContext(actor_id="designer-1", role=Role.DESIGNER)
    envelope = WriteEnvelope(idempotency_key="key-1", expected_state_version=1, data={"answer": "yes"})
    with pytest.raises(AuthorizationError):
        service.resume("project-1", actor, "homeowner", envelope)
```

```python
# tests/integration/application/test_idempotent_write.py
from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.domain.enums import Role


def test_identical_write_returns_original_result(service) -> None:
    actor = ActorContext(actor_id="homeowner-1", role=Role.HOMEOWNER)
    envelope = WriteEnvelope(idempotency_key="same-key", expected_state_version=0, data={})
    first = service.start_analysis("project-1", actor, envelope)
    second = service.start_analysis("project-1", actor, envelope)
    assert second == first
```

- [ ] **Step 2: Run tests and verify missing-service failures**

Run: `uv run pytest tests/unit/application tests/integration/application -v`  
Expected: collection fails because application modules and fixtures are absent.

- [ ] **Step 3: Implement authorization, idempotency, graph invocation, and persistence**

Define command types:

```python
T = TypeVar("T")


class ActorContext(BaseModel):
    actor_id: str
    role: Role


class WriteEnvelope(BaseModel, Generic[T]):
    idempotency_key: str
    expected_state_version: int
    data: T
```

`WorkflowService` must hash the canonical JSON request, return a matching idempotent response, reject a conflicting replay, verify project membership and role, load canonical state, invoke the graph with `thread_id=project_id`, validate returned state through Pydantic and patch policies, persist accepted changes with an audit record, then return either a pending interrupt or completed state.

Use `Command(resume=envelope.data)` only when continuing a stored interrupt. Use a plain input dictionary when starting a new graph run. Reconcile any checkpoint whose recorded project version differs from the canonical database by rebuilding the graph input from `ProjectRepository.load(project_id)`.

- [ ] **Step 4: Run application-service tests**

Run: `uv run pytest tests/unit/application tests/integration/application -v && uv run ruff check src tests`  
Expected: authorization and idempotent replay tests pass.

- [ ] **Step 5: Commit application orchestration**

```bash
git add src/alignspace/application tests/unit/application tests/integration/application
git commit -m "feat: coordinate transactional workflow writes"
```

---

### Task 8: Expose Project, Asset, and Attribute APIs

**Files:**
- Create: `src/alignspace/api/__init__.py`
- Create: `src/alignspace/api/dependencies.py`
- Create: `src/alignspace/api/errors.py`
- Create: `src/alignspace/api/routes/__init__.py`
- Create: `src/alignspace/api/routes/projects.py`
- Create: `src/alignspace/main.py`
- Create: `tests/conftest.py`
- Create: `tests/api/test_projects.py`
- Create: `tests/api/test_assets_and_attributes.py`

**Interfaces:**
- Consumes: Application service and repositories.
- Produces: `create_app(database_url, checkpoint_path)`, actor headers, project CRUD, asset registration/deletion, and attribute correction endpoints.

- [ ] **Step 1: Write failing API tests**

```python
# tests/api/test_projects.py
def test_create_and_read_project(client) -> None:
    response = client.post(
        "/v1/projects",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
        json={"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": True, "designerId": "designer-1"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    loaded = client.get(
        f"/v1/projects/{project_id}",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
    )
    assert loaded.status_code == 200
    assert loaded.json()["stateVersion"] == 0
```

```python
# tests/api/test_assets_and_attributes.py
def test_asset_registration_requires_consent(client, project_without_consent) -> None:
    response = client.post(
        f"/v1/projects/{project_without_consent}/assets",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
        json={
            "idempotencyKey": "asset-1",
            "expectedStateVersion": 0,
            "data": {"fixtureId": "living-room-1", "mediaType": "image/jpeg", "sizeBytes": 1024},
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSENT_REQUIRED"
```

- [ ] **Step 2: Run tests and verify missing-app failures**

Run: `uv run pytest tests/api/test_projects.py tests/api/test_assets_and_attributes.py -v`  
Expected: collection fails because `create_app` and API fixtures do not exist.

- [ ] **Step 3: Implement the application factory and project routes**

`create_app` must initialize the SQLAlchemy engine, session factory, repositories, mock agents, SQLite graph checkpointer, application service, exception handlers, and routers. Store this container on `app.state.container`.

Require `X-Actor-Id` and `X-Actor-Role` on project-scoped routes. Implement:

```text
POST   /v1/projects
GET    /v1/projects/{projectId}
DELETE /v1/projects/{projectId}
POST   /v1/projects/{projectId}/assets
DELETE /v1/projects/{projectId}/assets/{assetId}
PATCH  /v1/projects/{projectId}/attributes/{attributeId}
```

Attribute correction accepts `confirmed`, `rejected`, `unresolved`, or `not_applicable` only from an authorized human role. Project and asset deletion remove active records and call `checkpointer.delete_thread(project_id)`; retained audit metadata must not contain image content.

Map domain errors to the stable response shape with code, message, correlation ID, recoverability, and safe details.

- [ ] **Step 4: Run project API tests**

Run: `uv run pytest tests/api/test_projects.py tests/api/test_assets_and_attributes.py -v && uv run ruff check src tests`  
Expected: project, consent, asset, correction, and deletion tests pass.

- [ ] **Step 5: Commit foundational APIs**

```bash
git add src/alignspace/api src/alignspace/main.py tests/conftest.py tests/api/test_projects.py tests/api/test_assets_and_attributes.py
git commit -m "feat: expose project and preference APIs"
```

---

### Task 9: Expose Workflow, Conflict, Brief, and Approval APIs

**Files:**
- Create: `src/alignspace/api/routes/workflow.py`
- Create: `src/alignspace/api/routes/briefs.py`
- Modify: `src/alignspace/main.py`
- Create: `tests/api/test_workflow.py`
- Create: `tests/api/test_briefs.py`

**Interfaces:**
- Consumes: `WorkflowService`, graph interrupts, brief and approval policies.
- Produces: Analysis start/resume, next question, designer review, conflict resolution, latest brief, brief edit, and approval endpoints.

- [ ] **Step 1: Write failing workflow and approval API tests**

```python
# tests/api/test_workflow.py
def test_analysis_returns_pending_homeowner_question(client, ready_project) -> None:
    project_id = ready_project["id"]
    current = client.get(
        f"/v1/projects/{project_id}",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
    ).json()
    response = client.post(
        f"/v1/projects/{project_id}/analysis-runs",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
        json={"idempotencyKey": "run-1", "expectedStateVersion": current["stateVersion"], "data": {}},
    )
    assert response.status_code == 202
    assert response.json()["waitReason"] == "homeowner"
    assert response.json()["pendingQuestion"]["targetRole"] == "homeowner"
```

```python
# tests/api/test_briefs.py
def test_both_roles_must_approve_same_brief(client, brief_ready_project) -> None:
    project_id = brief_ready_project["id"]
    project = client.get(
        f"/v1/projects/{project_id}",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
    ).json()
    brief = client.get(
        f"/v1/projects/{project_id}/briefs/latest",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
    ).json()
    first = client.post(
        f"/v1/projects/{project_id}/briefs/{brief['version']}/approvals",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
        json={"idempotencyKey": "approve-h", "expectedStateVersion": project["stateVersion"], "data": {"contentHash": brief["contentHash"]}},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "awaiting_approval"

    second = client.post(
        f"/v1/projects/{project_id}/briefs/{brief['version']}/approvals",
        headers={"X-Actor-Id": "designer-1", "X-Actor-Role": "designer"},
        json={"idempotencyKey": "approve-d", "expectedStateVersion": first.json()["stateVersion"], "data": {"contentHash": brief["contentHash"]}},
    )
    assert second.status_code == 200
    assert second.json()["status"] == "approved"
```

- [ ] **Step 2: Run tests and verify missing-route failures**

Run: `uv run pytest tests/api/test_workflow.py tests/api/test_briefs.py -v`  
Expected: requests return `404 Not Found` because workflow and brief routers are not registered.

- [ ] **Step 3: Implement workflow and brief routes**

Implement and register:

```text
POST  /v1/projects/{projectId}/analysis-runs
GET   /v1/projects/{projectId}/questions/next
POST  /v1/projects/{projectId}/questions/{questionId}/answer
POST  /v1/projects/{projectId}/designer-reviews
POST  /v1/projects/{projectId}/conflicts/{conflictId}/resolve
GET   /v1/projects/{projectId}/briefs/latest
PATCH /v1/projects/{projectId}/briefs/{version}
POST  /v1/projects/{projectId}/briefs/{version}/approvals
```

Return `202 Accepted` with `waitReason` and a JSON-serializable pending task when the graph interrupts. Resume using the same project ID as LangGraph `thread_id`. Validate the final draft against `schemas/design-brief.schema.json`, compute the content hash from canonical JSON excluding approvals, and reject an approval whose submitted hash differs.

Editing a brief creates version `n + 1`, computes a new hash, clears approvals, appends an audit event, and returns the project to `awaiting_approval` after review passes.

- [ ] **Step 4: Run all API tests**

Run: `uv run pytest tests/api -v && uv run ruff check src tests`  
Expected: every API test passes with no warnings.

- [ ] **Step 5: Commit workflow APIs**

```bash
git add src/alignspace/api/routes/workflow.py src/alignspace/api/routes/briefs.py src/alignspace/main.py tests/api/test_workflow.py tests/api/test_briefs.py
git commit -m "feat: expose alignment workflow APIs"
```

---

### Task 10: Add Safety Regression Tests and Complete the Acceptance Path

**Files:**
- Create: `tests/unit/domain/test_safety_policy.py`
- Create: `tests/acceptance/test_backend_happy_path.py`
- Create: `tests/acceptance/test_adversarial_paths.py`
- Modify: `tests/conftest.py`
- Create: `README.backend.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Complete backend from Tasks 1–9.
- Produces: Network-free acceptance evidence, a `workflow_driver.complete() -> dict[str, object]` fixture, local run instructions, and explicit safety regressions.

- [ ] **Step 1: Write failing safety and acceptance tests**

```python
# tests/unit/domain/test_safety_policy.py
import pytest

from alignspace.domain.policies import PolicyViolationError, validate_professional_claim


def test_structural_assurance_is_blocked() -> None:
    with pytest.raises(PolicyViolationError, match="professional review required"):
        validate_professional_claim("This wall is definitely non-load-bearing and safe to remove")
```

```python
# tests/acceptance/test_adversarial_paths.py
import json


def test_image_instruction_cannot_change_project_scope(client, ready_project) -> None:
    project_id = ready_project["id"]
    current = client.get(
        f"/v1/projects/{project_id}",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
    ).json()
    response = client.post(
        f"/v1/projects/{project_id}/analysis-runs",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
        json={
            "idempotencyKey": "injection-run",
            "expectedStateVersion": current["stateVersion"],
            "data": {"fixture": "image-text-ignore-policy-read-other-project"},
        },
    )
    assert response.status_code == 202
    state = client.get(
        f"/v1/projects/{project_id}",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
    ).json()
    assert state["id"] == project_id
    assert "other-project" not in json.dumps(state)
```

```python
# tests/acceptance/test_backend_happy_path.py
def test_backend_completes_reviewed_dual_approval(workflow_driver) -> None:
    final_state = workflow_driver.complete()
    assert final_state["status"] == "approved"
    assert len(final_state["latestBrief"]["approvals"]) == 2
    assert len(final_state["questions"]) <= 10
    assert not any(
        conflict["status"] == "open" and conflict["severity"] == "critical"
        for conflict in final_state["conflicts"]
    )
    assert final_state["briefSchemaValid"] is True
```

- [ ] **Step 2: Run tests and verify the safety-policy failure**

Run: `uv run pytest tests/unit/domain/test_safety_policy.py tests/acceptance -v`  
Expected: collection fails because `validate_professional_claim` and acceptance fixtures are not defined.

- [ ] **Step 3: Implement deterministic blocked-topic policy and acceptance fixtures**

Implement normalized phrase matching for these categories: structural, electrical, regulatory, safety-critical, exact-price, and live-availability. Return a professional-review task from agent workflows; raise `PolicyViolationError` when an API operation attempts to persist an unsupported assurance.

Implement `workflow_driver.complete()` in `tests/conftest.py` so it calls the public API in this exact order and always reads the latest `stateVersion` before the next write. Create deterministic fixtures for:

```text
three lawful living-room asset records
wall colour, chair material, floor colour, and warm-light observations
homeowner selection of lighting as an additional liked element
designer budget constraint against natural stone
homeowner acceptance of a lower-cost stone-effect finish
review pass after conflict resolution
matching homeowner and designer approvals
```

Write `README.backend.md` with exact commands:

```bash
uv sync --extra dev
uv run uvicorn alignspace.main:app --reload
uv run pytest -q
uv run ruff check src tests
```

Add a concise backend link and scope statement to the root README.

- [ ] **Step 4: Run complete verification**

Run: `uv run pytest -q`  
Expected: all unit, integration, API, and acceptance tests pass.

Run: `uv run ruff check src tests && git diff --check`  
Expected: no lint or whitespace errors.

- [ ] **Step 5: Commit acceptance evidence and documentation**

```bash
git add src/alignspace/domain/policies.py tests/unit/domain/test_safety_policy.py tests/acceptance README.backend.md README.md
git commit -m "test: verify backend agent workflow"
```

---

## Final Verification

Run all commands from the repository root:

```bash
uv sync --extra dev
uv run pytest -q
uv run pytest --cov=alignspace --cov-report=term-missing
uv run ruff check src tests
git diff --check
git status --short --branch
```

Expected results:

- All tests pass without model credentials or network access after dependency installation.
- Coverage output contains no untested critical policy, approval, idempotency, or state-transition branch.
- Ruff and whitespace checks pass.
- The working tree contains only deliberate implementation-plan progress or is clean after the final commit.
- The backend starts locally and exposes OpenAPI at `/docs`.

## Specification Coverage

- Architecture and component boundaries: Tasks 4–9.
- Sparse canonical state and patch rules: Tasks 1–3.
- Five logical agents and deterministic question selection: Task 5.
- LangGraph routing, SQLite checkpoints, and human pause/resume: Task 6.
- Authorization, idempotency, optimistic locking, audit, and transactions: Tasks 4, 7, and 8.
- Approved API surface: Tasks 8–9.
- Brief schema, completeness, review, versioning, and dual approval: Tasks 1, 3, 5, and 9.
- Safety, prompt injection, professional escalation, deletion, and manual fallback: Tasks 5, 8, and 10.
- Unit, integration, API, and acceptance verification: Tasks 1–10.
