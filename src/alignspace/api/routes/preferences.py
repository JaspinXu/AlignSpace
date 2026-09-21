from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from alignspace.api.dependencies import get_actor, get_container
from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.preferences import CandidateBoard

router = APIRouter(prefix="/v1/projects", tags=["preferences"])
Actor = Annotated[ActorContext, Depends(get_actor)]
Container = Annotated[object, Depends(get_container)]


@router.post(
    "/{project_id}/preference-analyses",
    response_model=CandidateBoard,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_preference_analysis(
    project_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> CandidateBoard:
    return container.preferences.run_analysis(project_id, actor, envelope)


@router.get("/{project_id}/preference-analyses", response_model=CandidateBoard)
def candidate_board(project_id: str, actor: Actor, container: Container) -> CandidateBoard:
    return container.preferences.board(project_id, actor)


@router.patch("/{project_id}/candidates/{candidate_id}", response_model=CandidateBoard)
def edit_candidate(
    project_id: str,
    candidate_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> CandidateBoard:
    return container.preferences.edit_candidate(project_id, candidate_id, actor, envelope)


@router.post("/{project_id}/candidates/{candidate_id}/confirm", response_model=CandidateBoard)
def confirm_candidate(
    project_id: str,
    candidate_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> CandidateBoard:
    return container.preferences.confirm_candidate(project_id, candidate_id, actor, envelope)


@router.post("/{project_id}/candidates/{candidate_id}/reject", response_model=CandidateBoard)
def reject_candidate(
    project_id: str,
    candidate_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> CandidateBoard:
    return container.preferences.reject_candidate(project_id, candidate_id, actor, envelope)


@router.patch("/{project_id}/design-entries/{entry_id}", response_model=CandidateBoard)
def edit_design_entry(
    project_id: str,
    entry_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> CandidateBoard:
    return container.preferences.edit_entry(project_id, entry_id, actor, envelope)


@router.delete("/{project_id}/design-entries/{entry_id}", response_model=CandidateBoard)
def delete_design_entry(
    project_id: str,
    entry_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    response: Response,
    actor: Actor,
    container: Container,
) -> CandidateBoard:
    response.status_code = status.HTTP_200_OK
    return container.preferences.delete_entry(project_id, entry_id, actor, envelope)
