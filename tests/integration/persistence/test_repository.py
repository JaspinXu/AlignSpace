from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select

from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    ConflictStatus,
    ConflictType,
    ConstraintCategory,
    ConstraintOwner,
    ConstraintSeverity,
    ConstraintVerificationStatus,
    EvidenceSource,
    ProjectStatus,
    Role,
)
from alignspace.domain.models import (
    Approval,
    Attribute,
    BriefVersion,
    Conflict,
    Constraint,
    Evidence,
    ProjectState,
    Question,
    QuestionOption,
    calculate_brief_content_hash,
)
from alignspace.persistence.database import create_engine_and_session
from alignspace.persistence.repository import (
    IdempotencyConflictError,
    canonical_request_hash,
)
from alignspace.persistence.tables import AuditEventRow, IdempotencyRecordRow, ProjectRow
from alignspace.persistence.uow import SqlAlchemyUnitOfWork


def _complete_state() -> ProjectState:
    brief_payload: dict[str, object] = {
        "style": "warm modern",
        "constraints": ["retain the structural wall"],
    }
    content_hash = calculate_brief_content_hash(brief_payload)
    return ProjectState(
        project_id="project-1",
        state_version=0,
        status=ProjectStatus.HOMEOWNER_REVIEW,
        attributes=[
            Attribute(
                id="attribute-1",
                target_element="living room",
                dimension="style",
                value="warm modern",
                status=AttributeStatus.PROPOSED,
                confidence=0.82,
                evidence=[
                    Evidence(
                        source_type=EvidenceSource.IMAGE,
                        source_id="asset-1",
                        description="Warm timber and cream upholstery",
                    )
                ],
                actor=ActorKind.VISION_AGENT,
                updated_at=datetime(2026, 9, 9, 1, 2, 3, tzinfo=UTC),
            )
        ],
        constraints=[
            Constraint(
                id="constraint-1",
                category=ConstraintCategory.SPACE,
                statement="Retain the structural wall",
                rationale="Removal has not been assessed",
                severity=ConstraintSeverity.CRITICAL,
                verification_status=ConstraintVerificationStatus.UNVERIFIED,
                owner=ConstraintOwner.DESIGNER,
                evidence=[
                    Evidence(
                        source_type=EvidenceSource.DESIGNER_NOTE,
                        source_id="note-1",
                        description="Existing plan marks the wall as structural",
                    )
                ],
            )
        ],
        questions=[
            Question(
                id="question-1",
                target_role=Role.HOMEOWNER,
                text="Which timber tone do you prefer?",
                rationale="Resolve the material direction",
                options=[QuestionOption(label="oak"), QuestionOption(label="walnut")],
                answer="oak",
                repetition_fingerprint="timber-tone",
            )
        ],
        conflicts=[
            Conflict(
                id="conflict-1",
                type=ConflictType.PREFERENCE_VS_CONSTRAINT,
                summary="Open plan conflicts with structural wall",
                impact="The layout needs a non-structural alternative",
                status=ConflictStatus.OPEN,
                severity=ConstraintSeverity.CRITICAL,
                resolution_attempts=1,
            )
        ],
        brief_versions=[
            BriefVersion(
                version=1,
                content_hash=content_hash,
                payload=brief_payload,
                completeness=0.9,
            )
        ],
        approvals=[
            Approval(
                role=Role.HOMEOWNER,
                actor_id="homeowner-1",
                brief_version=1,
                content_hash=content_hash,
                approved_at=datetime(2026, 9, 9, 2, 3, 4, tzinfo=UTC),
            )
        ],
        completeness=0.875,
        current_node="ask_homeowner",
        wait_reason="homeowner",
    )


def test_project_state_round_trips_through_sqlite(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")
    original = _complete_state()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(original)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        loaded = uow.projects.load("project-1")

    assert loaded == original
    engine.dispose()


def test_schema_uses_canonical_entity_tables_without_a_state_snapshot(tmp_path) -> None:
    engine, _ = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")
    inspector = inspect(engine)

    assert {
        "projects",
        "project_members",
        "image_assets",
        "attributes",
        "constraints",
        "questions",
        "conflicts",
        "brief_versions",
        "approvals",
        "audit_events",
        "idempotency_records",
    } <= set(inspector.get_table_names())
    project_columns = {column["name"] for column in inspector.get_columns("projects")}
    assert project_columns == {
        "budget_band",
        "consent",
        "id",
        "state_version",
        "status",
        "completeness",
        "current_node",
        "room_type",
        "wait_reason",
        "brief_stale",
    }
    engine.dispose()


def test_create_and_save_append_audit_events_in_the_same_transaction(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")
    initial = ProjectState(project_id="project-1")

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(initial)
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        updated = initial.model_copy(
            update={
                "state_version": 1,
                "status": ProjectStatus.ANALYSING,
                "current_node": "analyse_images",
            }
        )
        uow.projects.save(updated, expected_version=0)
        uow.commit()

    with session_factory() as session:
        events = list(
            session.scalars(select(AuditEventRow).order_by(AuditEventRow.id)).all()
        )

    assert [(event.event_type, event.state_version) for event in events] == [
        ("project_created", 0),
        ("project_saved", 1),
    ]
    assert all(event.project_id == "project-1" for event in events)
    engine.dispose()


def test_idempotency_lookup_returns_identical_stored_response(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")
    request_hash = canonical_request_hash({"answer": "oak", "options": [1, 2]})

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(ProjectState(project_id="project-1"))
        uow.idempotency.record(
            project_id="project-1",
            key="request-1",
            request_hash=request_hash,
            response_payload={"status": "waiting", "stateVersion": 1},
            resulting_version=1,
        )
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        replay = uow.idempotency.lookup("project-1", "request-1", request_hash)

    assert replay is not None
    assert replay.response_payload == {"status": "waiting", "stateVersion": 1}
    assert replay.resulting_version == 1
    engine.dispose()


def test_idempotency_lookup_rejects_same_key_with_different_content(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")
    first_hash = canonical_request_hash({"answer": "oak"})

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(ProjectState(project_id="project-1"))
        uow.idempotency.record(
            project_id="project-1",
            key="request-1",
            request_hash=first_hash,
            response_payload={"stateVersion": 1},
            resulting_version=1,
        )
        uow.commit()

    with (
        pytest.raises(IdempotencyConflictError, match="request-1"),
        SqlAlchemyUnitOfWork(session_factory) as uow,
    ):
        uow.idempotency.lookup(
            "project-1",
            "request-1",
            canonical_request_hash({"answer": "walnut"}),
        )
    engine.dispose()


def test_canonical_request_hash_is_stable_for_equivalent_payloads() -> None:
    left = {"details": {"colour": "crème", "finish": "matte"}, "answer": "oak"}
    right = {"answer": "oak", "details": {"finish": "matte", "colour": "crème"}}

    assert canonical_request_hash(left) == canonical_request_hash(right)


def test_uncommitted_unit_of_work_rolls_back_project_audit_and_idempotency(tmp_path) -> None:
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'test.db'}")

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(ProjectState(project_id="project-1"))
        uow.idempotency.record(
            project_id="project-1",
            key="request-1",
            request_hash=canonical_request_hash({"answer": "oak"}),
            response_payload={"stateVersion": 0},
            resulting_version=0,
        )

    with session_factory() as session:
        assert session.scalar(select(ProjectRow.id)) is None
        assert session.scalar(select(AuditEventRow.id)) is None
        assert session.scalar(select(IdempotencyRecordRow.key)) is None
    engine.dispose()


def test_candidate_entities_round_trip_through_the_repository(tmp_path):
    from alignspace.domain.preferences import (
        AnalysisRun,
        AnalysisStatus,
        CandidateDimension,
        CandidatePreference,
        Certainty,
        DesignEntry,
        InputAsset,
        ProviderMode,
    )
    from alignspace.persistence.database import create_engine_and_session
    from alignspace.persistence.repository import ProjectRepository

    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'cand.db'}")
    try:
        with session_factory() as session:
            repository = ProjectRepository(session)
            state = ProjectState(project_id="project-cand")
            repository.create(state)
            session.commit()

        with session_factory() as session:
            repository = ProjectRepository(session)
            state = repository.load("project-cand")
            run = AnalysisRun(
                id="run-1",
                status=AnalysisStatus.COMPLETED,
                requested_by="homeowner-1",
                description="喜欢床的颜色",
                input_assets=[InputAsset(asset_id="asset-1", sha256="aaa")],
                input_fingerprint="fp",
                provider_mode=ProviderMode.MOCK,
                model="mock-deterministic",
                prompt_version="prompt-v1",
                schema_version="1.0.0",
            )
            entry = DesignEntry(
                id="entry-1",
                analysis_run_id="run-1",
                source_asset_id="asset-1",
                target_element="bed",
                attention_dimensions=[CandidateDimension.COLOUR],
            )
            candidate = CandidatePreference(
                id="cand-1",
                entry_id="entry-1",
                dimension=CandidateDimension.COLOUR,
                certainty=Certainty.INFERRED,
                proposed_value="warm grey",
            )
            updated = state.model_copy(
                update={
                    "state_version": state.state_version + 1,
                    "analysis_runs": [run],
                    "design_entries": [entry],
                    "candidates": [candidate],
                }
            )
            repository.save(updated, expected_version=state.state_version)
            session.commit()

        with session_factory() as session:
            reloaded = ProjectRepository(session).load("project-cand")
        assert [item.id for item in reloaded.analysis_runs] == ["run-1"]
        assert [item.id for item in reloaded.design_entries] == ["entry-1"]
        assert [item.id for item in reloaded.candidates] == ["cand-1"]
        assert reloaded.candidates[0].proposed_value == "warm grey"
    finally:
        engine.dispose()


def test_space_versions_round_trip_through_the_repository(tmp_path):
    from alignspace.domain.enums import Role
    from alignspace.domain.space import (
        SpacePlan,
        SpaceVersion,
        build_rectangular_room,
        calculate_space_content_hash,
    )
    from alignspace.persistence.database import create_engine_and_session
    from alignspace.persistence.repository import ProjectRepository

    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'space.db'}")
    try:
        with session_factory() as session:
            repository = ProjectRepository(session)
            state = ProjectState(project_id="project-space")
            repository.create(state)
            session.commit()

        with session_factory() as session:
            repository = ProjectRepository(session)
            state = repository.load("project-space")
            plan = SpacePlan(
                rooms=[
                    build_rectangular_room(
                        room_id="room-1", name="客厅", width=4000, depth=5000
                    )
                ]
            )
            payload = plan.model_dump(mode="json", by_alias=True)
            version = SpaceVersion(
                version=1,
                content_hash=calculate_space_content_hash(payload),
                payload=payload,
                created_by="homeowner-1",
                created_role=Role.HOMEOWNER,
                source="rectangular_dimensions",
            )
            updated = state.model_copy(
                update={
                    "state_version": state.state_version + 1,
                    "space_versions": [version],
                }
            )
            repository.save(updated, expected_version=state.state_version)
            session.commit()

        with session_factory() as session:
            reloaded = ProjectRepository(session).load("project-space")
        assert [item.version for item in reloaded.space_versions] == [1]
        restored = reloaded.space_versions[0]
        assert restored.created_role is Role.HOMEOWNER
        assert restored.payload["rooms"][0]["id"] == "room-1"
        assert restored.payload["rooms"][0]["floor"]["id"] == "floor-room-1"
    finally:
        engine.dispose()
