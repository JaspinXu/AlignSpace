"""Candidate preference analysis and confirmation service.

Candidates are proposals. Confirming one writes into the single formal
preference system (``Attribute``) with a stable id derived from the candidate,
so repeating a confirmation cannot create a duplicate and re-running analysis
cannot overwrite a confirmed or human-edited candidate.
"""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.service import AuthorizationError
from alignspace.domain.base import DomainModel
from alignspace.domain.constraints import flag_brief_change, reconcile_constraints
from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    EvidenceSource,
    Role,
)
from alignspace.domain.models import Attribute, Evidence, ProjectState
from alignspace.domain.patches import (
    StatePatch,
    UpsertAnalysisRun,
    UpsertAttribute,
    UpsertCandidate,
    UpsertDesignEntry,
    apply_patch,
)
from alignspace.domain.policies import StaleStateError, calculate_completeness
from alignspace.domain.preferences import (
    AnalysisRun,
    AnalysisStatus,
    CandidateDimension,
    CandidatePreference,
    CandidateStatus,
    Certainty,
    DesignEntry,
    EntryStatus,
    InputAsset,
    ProviderMode,
    calculate_analysis_fingerprint,
)
from alignspace.persistence.repository import ProjectRepository, canonical_request_hash
from alignspace.persistence.tables import ImageAssetRow
from alignspace.persistence.uow import SqlAlchemyUnitOfWork
from alignspace.providers.preference import (
    AnalysisAsset,
    PreferenceAnalysisProvider,
    PreferenceAnalysisRequest,
)
from alignspace.storage.base import Storage

PROMPT_VERSION = "candidate-prompt-v1"
SCHEMA_VERSION = "1.0.0"
MAX_ANALYSIS_ASSETS = 10


class ThirdPartyConsentRequired(ValueError):
    """Raised when real analysis is requested without third-party consent."""


class CandidateStateError(ValueError):
    """Raised when a candidate action is invalid for its current state."""


class CandidateView(DomainModel):
    id: str
    entry_id: str
    dimension: CandidateDimension
    certainty: Certainty
    proposed_value: str | None
    confirmed_value: str | None
    status: CandidateStatus
    attribute_id: str | None
    human_edited: bool
    evidence: list[Evidence]


class EntryView(DomainModel):
    id: str
    analysis_run_id: str
    source_asset_id: str | None
    source_available: bool
    target_element: str
    attention_dimensions: list[CandidateDimension]
    note: str
    status: EntryStatus
    candidates: list[CandidateView]


class AnalysisRunView(DomainModel):
    id: str
    status: AnalysisStatus
    description: str
    provider_mode: ProviderMode
    model: str
    prompt_version: str
    schema_version: str
    third_party_consent: bool
    input_assets: list[InputAsset]
    input_fingerprint: str
    stale: bool
    error: str | None
    entries: list[EntryView]


class CandidateBoard(DomainModel):
    state_version: int
    runs: list[AnalysisRunView]


MembershipCheck = Callable[[str, ActorContext], bool]


class PreferenceService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        provider: PreferenceAnalysisProvider,
        storage: Storage,
        membership_check: MembershipCheck,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._storage = storage
        self._membership_check = membership_check

    # -- reads -----------------------------------------------------------------

    def board(self, project_id: str, actor: ActorContext) -> CandidateBoard:
        self._authorize(project_id, actor)
        with self._session_factory() as session:
            state = self._load(session, project_id)
            active = self._active_asset_ids(session, project_id)
            return self._board(state, active)

    # -- analysis --------------------------------------------------------------

    def run_analysis(
        self, project_id: str, actor: ActorContext, envelope: WriteEnvelope[dict[str, object]]
    ) -> CandidateBoard:
        self._authorize(project_id, actor)
        self._require_homeowner(actor, "run preference analysis")
        asset_ids, description, consent = self._read_analysis_request(project_id, envelope.data)
        request_hash = self._request_hash("run_preference_analysis", project_id, actor, envelope)
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return CandidateBoard.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            assets = self._analysis_assets(uow.session, project_id, asset_ids)
            fingerprint = calculate_analysis_fingerprint(
                [(asset.id, asset.sha256) for asset in assets], description, PROMPT_VERSION
            )
            provider_mode = self._provider_mode()
            if provider_mode is ProviderMode.DEEPSEEK and not consent:
                raise ThirdPartyConsentRequired(
                    "sending reference images to a third-party model service requires consent"
                )
            # The external call happens before the local write. Local idempotency
            # does not guarantee the provider is only billed once.
            result = self._provider.analyze(
                PreferenceAnalysisRequest(
                    assets=assets,
                    description=description,
                    prompt_version=PROMPT_VERSION,
                    schema_version=SCHEMA_VERSION,
                )
            )
            run = AnalysisRun(
                id=str(uuid4()),
                status=AnalysisStatus.COMPLETED,
                requested_by=actor.actor_id,
                description=description,
                input_assets=[InputAsset(asset_id=asset.id, sha256=asset.sha256) for asset in assets],
                input_fingerprint=fingerprint,
                provider_mode=provider_mode,
                model=result.model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                third_party_consent=consent,
            )
            operations: list[Any] = [UpsertAnalysisRun(analysis_run=run)]
            operations.extend(self._merge_proposals(state, run, result.entries))
            updated = apply_patch(
                state, StatePatch(expected_state_version=state.state_version, operations=operations)
            )
            response = self._board(updated, self._active_asset_ids(uow.session, project_id))
            uow.projects.save(updated, expected_version=state.state_version)
            self._record(
                uow, project_id, envelope, request_hash, response, updated.state_version
            )
            uow.commit()
            return response

    def _merge_proposals(self, state: ProjectState, run: AnalysisRun, entries) -> list[Any]:
        """Upsert proposals by a stable per-image id, never clobbering human work."""
        operations: list[Any] = []
        existing_entries = {item.id: item for item in state.design_entries}
        existing_candidates = {item.id: item for item in state.candidates}
        for proposed in entries:
            entry_id = f"entry-{proposed.source_asset_id}-{proposed.target_element}"
            entry = existing_entries.get(entry_id)
            operations.append(
                UpsertDesignEntry(
                    entry=DesignEntry(
                        id=entry_id,
                        analysis_run_id=run.id,
                        source_asset_id=proposed.source_asset_id,
                        target_element=proposed.target_element,
                        attention_dimensions=proposed.attention_dimensions,
                        note=entry.note if entry else "",
                        status=(
                            EntryStatus.SOURCE_DELETED
                            if entry and entry.status is EntryStatus.SOURCE_DELETED
                            else (entry.status if entry else EntryStatus.OPEN)
                        ),
                    )
                )
            )
            for candidate in proposed.candidates:
                candidate_id = (
                    f"cand-{proposed.source_asset_id}-{proposed.target_element}-"
                    f"{candidate.dimension.value}"
                )
                current = existing_candidates.get(candidate_id)
                if current is not None and (
                    current.status is not CandidateStatus.PROPOSED or current.human_edited
                ):
                    # A confirmed, rejected or human-edited candidate is preserved.
                    continue
                operations.append(
                    UpsertCandidate(
                        candidate=CandidatePreference(
                            id=candidate_id,
                            entry_id=entry_id,
                            dimension=candidate.dimension,
                            certainty=candidate.certainty,
                            proposed_value=candidate.proposed_value,
                            evidence=candidate.evidence,
                        )
                    )
                )
        return operations

    # -- candidate decisions ---------------------------------------------------

    def confirm_candidate(
        self,
        project_id: str,
        candidate_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> CandidateBoard:
        return self._decide(project_id, candidate_id, actor, envelope, confirm=True)

    def reject_candidate(
        self,
        project_id: str,
        candidate_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> CandidateBoard:
        return self._decide(project_id, candidate_id, actor, envelope, confirm=False)

    def _decide(
        self,
        project_id: str,
        candidate_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
        *,
        confirm: bool,
    ) -> CandidateBoard:
        self._authorize(project_id, actor)
        self._require_homeowner(actor, "decide a candidate")
        action = "confirm_candidate" if confirm else "reject_candidate"
        request_hash = self._request_hash(
            action, project_id, actor, envelope, extra={"candidateId": candidate_id}
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return CandidateBoard.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            candidate = next((item for item in state.candidates if item.id == candidate_id), None)
            if candidate is None:
                raise KeyError(f"candidate {candidate_id} not found")
            entry = next(
                (item for item in state.design_entries if item.id == candidate.entry_id), None
            )
            if entry is None:
                raise CandidateStateError("candidate entry no longer exists")
            active = self._active_asset_ids(uow.session, project_id)
            if entry.source_asset_id and entry.source_asset_id not in active:
                raise CandidateStateError(
                    "the source image was deleted; this candidate can no longer be applied"
                )
            if confirm:
                operations = self._confirmation_operations(state, entry, candidate, envelope.data)
            else:
                operations = [
                    UpsertCandidate(
                        candidate=candidate.model_copy(update={"status": CandidateStatus.REJECTED})
                    )
                ]
                updated = apply_patch(
                    state,
                    StatePatch(
                        expected_state_version=state.state_version, operations=operations
                    ),
                )
                response = self._board(updated, active)
                uow.projects.save(updated, expected_version=state.state_version)
                self._record(
                    uow, project_id, envelope, request_hash, response, updated.state_version
                )
                uow.commit()
                return response
            updated = apply_patch(
                state, StatePatch(expected_state_version=state.state_version, operations=operations)
            )
            updated = updated.model_copy(
                update={
                    "conflicts": reconcile_constraints(updated),
                    "completeness": calculate_completeness(updated),
                }
            )
            updated = flag_brief_change(updated)
            response = self._board(updated, active)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record(uow, project_id, envelope, request_hash, response, updated.state_version)
            uow.commit()
            return response

    def _confirmation_operations(
        self,
        state: ProjectState,
        entry: DesignEntry,
        candidate: CandidatePreference,
        data: dict[str, object],
    ) -> list[Any]:
        raw = data.get("value", candidate.confirmed_value or candidate.proposed_value)
        if not isinstance(raw, str) or not raw.strip():
            raise CandidateStateError("confirming requires a value to adopt")
        value = raw.strip()
        # Stable id derived from the candidate: repeating a confirmation is a no-op
        # rather than a second preference.
        attribute_id = f"pref-{candidate.id}"
        evidence = list(candidate.evidence)
        evidence.append(
            Evidence(
                source_type=EvidenceSource.HOMEOWNER_ANSWER,
                source_id=candidate.id,
                description="Homeowner confirmed this candidate.",
            )
        )
        attribute = Attribute(
            id=attribute_id,
            target_element=entry.target_element,
            dimension=candidate.dimension.value,
            value=value,
            status=AttributeStatus.CONFIRMED,
            confidence=1.0,
            evidence=evidence,
            actor=ActorKind.HOMEOWNER,
        )
        confirmed = candidate.model_copy(
            update={
                "status": CandidateStatus.CONFIRMED,
                "confirmed_value": value,
                "attribute_id": attribute_id,
            }
        )
        signed = self._sign_entry(state, entry, candidate.id)
        operations: list[Any] = [UpsertCandidate(candidate=confirmed)]
        if signed is not None:
            operations.append(UpsertDesignEntry(entry=signed))
        return [*operations, UpsertAttribute(attribute=attribute)]

    def _sign_entry(
        self, state: ProjectState, entry: DesignEntry, candidate_id: str
    ) -> DesignEntry | None:
        """Reflect remaining decisions in the entry status."""
        siblings = [
            item
            for item in state.candidates
            if item.entry_id == entry.id
            and item.id != candidate_id
            and item.status is not CandidateStatus.CONFIRMED
        ]
        status = EntryStatus.PARTIALLY_CONFIRMED if siblings else EntryStatus.CONFIRMED
        if entry.status is status:
            return None
        return entry.model_copy(update={"status": status})

    def edit_candidate(
        self,
        project_id: str,
        candidate_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> CandidateBoard:
        self._authorize(project_id, actor)
        self._require_homeowner(actor, "edit a candidate")
        request_hash = self._request_hash(
            "edit_candidate", project_id, actor, envelope, extra={"candidateId": candidate_id}
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return CandidateBoard.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            candidate = next((item for item in state.candidates if item.id == candidate_id), None)
            if candidate is None:
                raise KeyError(f"candidate {candidate_id} not found")
            raw_value = envelope.data.get("value")
            if raw_value is not None and not isinstance(raw_value, str):
                raise CandidateStateError("candidate value must be a string")
            changes: dict[str, object] = {"human_edited": True}
            if raw_value is not None:
                changes["proposed_value"] = raw_value.strip() or None
            if envelope.data.get("certainty") is not None:
                changes["certainty"] = Certainty(str(envelope.data["certainty"]))
            edited = candidate.model_copy(update=changes)
            active = self._active_asset_ids(uow.session, project_id)
            updated = apply_patch(
                state,
                StatePatch(
                    expected_state_version=state.state_version,
                    operations=[UpsertCandidate(candidate=edited)],
                ),
            )
            response = self._board(updated, active)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record(uow, project_id, envelope, request_hash, response, updated.state_version)
            uow.commit()
            return response

    def edit_entry(
        self,
        project_id: str,
        entry_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> CandidateBoard:
        self._authorize(project_id, actor)
        self._require_homeowner(actor, "edit a design entry")
        request_hash = self._request_hash(
            "edit_design_entry", project_id, actor, envelope, extra={"entryId": entry_id}
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return CandidateBoard.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            entry = next((item for item in state.design_entries if item.id == entry_id), None)
            if entry is None:
                raise KeyError(f"design entry {entry_id} not found")
            changes: dict[str, object] = {}
            if isinstance(envelope.data.get("note"), str):
                changes["note"] = envelope.data["note"]
            if envelope.data.get("attentionDimensions") is not None:
                changes["attention_dimensions"] = [
                    CandidateDimension(str(item))
                    for item in envelope.data["attentionDimensions"]
                ]
            if envelope.data.get("dismissed") is True:
                changes["status"] = EntryStatus.DISMISSED
            edited = entry.model_copy(update=changes)
            active = self._active_asset_ids(uow.session, project_id)
            updated = apply_patch(
                state,
                StatePatch(
                    expected_state_version=state.state_version,
                    operations=[UpsertDesignEntry(entry=edited)],
                ),
            )
            response = self._board(updated, active)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record(uow, project_id, envelope, request_hash, response, updated.state_version)
            uow.commit()
            return response

    def delete_entry(
        self,
        project_id: str,
        entry_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> CandidateBoard:
        self._authorize(project_id, actor)
        self._require_homeowner(actor, "delete a design entry")
        request_hash = self._request_hash(
            "delete_design_entry", project_id, actor, envelope, extra={"entryId": entry_id}
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return CandidateBoard.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            if not any(item.id == entry_id for item in state.design_entries):
                raise KeyError(f"design entry {entry_id} not found")
            # Drop the candidate organisation only. Confirmed preferences were already
            # written into the formal Attribute system and are never removed here.
            updated = state.model_copy(
                update={
                    "state_version": state.state_version + 1,
                    "design_entries": [
                        item for item in state.design_entries if item.id != entry_id
                    ],
                    "candidates": [item for item in state.candidates if item.entry_id != entry_id],
                }
            )
            active = self._active_asset_ids(uow.session, project_id)
            response = self._board(updated, active)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record(uow, project_id, envelope, request_hash, response, updated.state_version)
            uow.commit()
            return response

    # -- helpers ---------------------------------------------------------------

    def _read_analysis_request(
        self, project_id: str, data: dict[str, object]
    ) -> tuple[list[str], str, bool]:
        raw_ids = data.get("assetIds")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise CandidateStateError("analysis requires at least one selected image")
        asset_ids = [str(item) for item in raw_ids]
        if len(set(asset_ids)) != len(asset_ids):
            raise CandidateStateError("selected images must be unique")
        if len(asset_ids) > MAX_ANALYSIS_ASSETS:
            raise CandidateStateError("analysis accepts at most ten images")
        description = data.get("description")
        if not isinstance(description, str) or not description.strip():
            raise CandidateStateError("analysis requires a description of what is liked")
        return asset_ids, description.strip(), data.get("thirdPartyConsent") is True

    def _analysis_assets(
        self, session: Session, project_id: str, asset_ids: list[str]
    ) -> list[AnalysisAsset]:
        rows = session.scalars(
            select(ImageAssetRow).where(
                ImageAssetRow.project_id == project_id,
                ImageAssetRow.id.in_(asset_ids),
                ImageAssetRow.deleted_at.is_(None),
            )
        ).all()
        found = {row.id: row for row in rows}
        missing = [asset_id for asset_id in asset_ids if asset_id not in found]
        if missing:
            raise KeyError(f"unknown or deleted reference images: {missing}")
        return [
            AnalysisAsset(
                id=asset_id,
                media_type=found[asset_id].payload.get("media_type", "image/unknown"),
                sha256=found[asset_id].payload.get("sha256", ""),
                data=self._storage.open(found[asset_id].payload["storage_key"]),
            )
            for asset_id in asset_ids
            if found[asset_id].payload.get("storage_key")
        ]

    def _provider_mode(self) -> ProviderMode:
        return self._provider.provider_mode

    def _active_asset_ids(self, session: Session, project_id: str) -> set[str]:
        rows = session.scalars(
            select(ImageAssetRow.id).where(
                ImageAssetRow.project_id == project_id,
                ImageAssetRow.deleted_at.is_(None),
            )
        ).all()
        return set(rows)

    def _board(self, state: ProjectState, active: set[str]) -> CandidateBoard:
        by_entry: dict[str, list[CandidateView]] = {}
        for candidate in state.candidates:
            by_entry.setdefault(candidate.entry_id, []).append(
                CandidateView(
                    id=candidate.id,
                    entry_id=candidate.entry_id,
                    dimension=candidate.dimension,
                    certainty=candidate.certainty,
                    proposed_value=candidate.proposed_value,
                    confirmed_value=candidate.confirmed_value,
                    status=candidate.status,
                    attribute_id=candidate.attribute_id,
                    human_edited=candidate.human_edited,
                    evidence=candidate.evidence,
                )
            )
        entries = [
            EntryView(
                id=entry.id,
                analysis_run_id=entry.analysis_run_id,
                source_asset_id=entry.source_asset_id,
                source_available=entry.source_asset_id in active,
                target_element=entry.target_element,
                attention_dimensions=entry.attention_dimensions,
                note=entry.note,
                status=entry.status,
                candidates=sorted(
                    by_entry.get(entry.id, []), key=lambda item: item.dimension.value
                ),
            )
            for entry in state.design_entries
        ]
        runs = [
            AnalysisRunView(
                id=run.id,
                status=run.status,
                description=run.description,
                provider_mode=run.provider_mode,
                model=run.model,
                prompt_version=run.prompt_version,
                schema_version=run.schema_version,
                third_party_consent=run.third_party_consent,
                input_assets=run.input_assets,
                input_fingerprint=run.input_fingerprint,
                stale=self._is_stale(run, active),
                error=run.error,
                entries=[item for item in entries if item.analysis_run_id == run.id],
            )
            for run in state.analysis_runs
        ]
        return CandidateBoard(state_version=state.state_version, runs=runs)

    @staticmethod
    def _is_stale(run: AnalysisRun, active: set[str]) -> bool:
        return any(asset.asset_id not in active for asset in run.input_assets)

    def _load(self, session: Session, project_id: str) -> ProjectState:
        return ProjectRepository(session).load(project_id)

    def _authorize(self, project_id: str, actor: ActorContext) -> None:
        if not self._membership_check(project_id, actor):
            raise AuthorizationError("actor is not a project member with the requested role")

    @staticmethod
    def _require_homeowner(actor: ActorContext, action: str) -> None:
        if actor.role is not Role.HOMEOWNER:
            raise AuthorizationError(f"only a homeowner can {action}")

    @staticmethod
    def _check_version(state: ProjectState, expected_version: int) -> None:
        if state.state_version != expected_version:
            raise StaleStateError(
                f"expected version {expected_version}, current version {state.state_version}"
            )

    @staticmethod
    def _request_hash(
        action: str,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[Any],
        *,
        extra: dict[str, object] | None = None,
    ) -> str:
        return canonical_request_hash(
            {
                "action": action,
                "projectId": project_id,
                "actor": actor.model_dump(mode="json", by_alias=True),
                "envelope": envelope.model_dump(mode="json", by_alias=True),
                **(extra or {}),
            }
        )

    @staticmethod
    def _record(
        uow: SqlAlchemyUnitOfWork,
        project_id: str,
        envelope: WriteEnvelope[Any],
        request_hash: str,
        response: DomainModel,
        resulting_version: int,
    ) -> None:
        uow.idempotency.record(
            project_id=project_id,
            key=envelope.idempotency_key,
            request_hash=request_hash,
            response_payload=response.model_dump(mode="json", by_alias=True),
            resulting_version=resulting_version,
        )
