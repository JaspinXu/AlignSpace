from typing import Annotated, Literal

from pydantic import BaseModel, Field

from alignspace.domain.enums import ActorKind, AttributeStatus, Role
from alignspace.domain.models import (
    Approval,
    Attribute,
    BriefVersion,
    Conflict,
    Constraint,
    ProjectState,
    Question,
)
from alignspace.domain.policies import DomainRuleError, StaleStateError


class UpsertAttribute(BaseModel):
    op: Literal["upsert_attribute"] = "upsert_attribute"
    attribute: Attribute


class UpsertConstraint(BaseModel):
    op: Literal["upsert_constraint"] = "upsert_constraint"
    constraint: Constraint


class UpsertQuestion(BaseModel):
    op: Literal["upsert_question"] = "upsert_question"
    question: Question


class UpsertConflict(BaseModel):
    op: Literal["upsert_conflict"] = "upsert_conflict"
    conflict: Conflict


class UpsertBriefVersion(BaseModel):
    op: Literal["upsert_brief_version"] = "upsert_brief_version"
    brief_version: BriefVersion


class UpsertApproval(BaseModel):
    op: Literal["upsert_approval"] = "upsert_approval"
    approval: Approval


PatchOperation = Annotated[
    UpsertAttribute
    | UpsertConstraint
    | UpsertQuestion
    | UpsertConflict
    | UpsertBriefVersion
    | UpsertApproval,
    Field(discriminator="op"),
]


class StatePatch(BaseModel):
    expected_state_version: int
    operations: list[PatchOperation]


def apply_patch(state: ProjectState, patch: StatePatch) -> ProjectState:
    if patch.expected_state_version != state.state_version:
        raise StaleStateError(
            f"expected version {patch.expected_state_version}, current version {state.state_version}"
        )
    attributes = list(state.attributes)
    constraints = list(state.constraints)
    questions = list(state.questions)
    conflicts = list(state.conflicts)
    brief_versions = list(state.brief_versions)
    approvals = list(state.approvals)
    for operation in patch.operations:
        if isinstance(operation, UpsertAttribute):
            attribute = operation.attribute
            if (
                attribute.actor == ActorKind.VISION_AGENT
                and attribute.status != AttributeStatus.PROPOSED
            ):
                raise DomainRuleError("vision observations must remain proposed")
            attributes = [item for item in attributes if item.id != attribute.id]
            attributes.append(attribute)
        elif isinstance(operation, UpsertConstraint):
            constraint = operation.constraint
            constraints = [item for item in constraints if item.id != constraint.id]
            constraints.append(constraint)
        elif isinstance(operation, UpsertQuestion):
            question = operation.question
            questions = [item for item in questions if item.id != question.id]
            homeowner_question_count = sum(
                item.target_role == Role.HOMEOWNER for item in questions
            )
            if question.target_role == Role.HOMEOWNER and homeowner_question_count >= 10:
                raise DomainRuleError("homeowner question budget exhausted")
            questions.append(question)
        elif isinstance(operation, UpsertConflict):
            conflict = operation.conflict
            conflicts = [item for item in conflicts if item.id != conflict.id]
            conflicts.append(conflict)
        elif isinstance(operation, UpsertBriefVersion):
            brief_version = operation.brief_version
            brief_versions = [
                item for item in brief_versions if item.version != brief_version.version
            ]
            brief_versions.append(brief_version)
        elif isinstance(operation, UpsertApproval):
            approval = operation.approval
            approvals = [
                item
                for item in approvals
                if (item.role, item.brief_version, item.content_hash)
                != (approval.role, approval.brief_version, approval.content_hash)
            ]
            approvals.append(approval)
        else:
            raise TypeError(f"unsupported patch operation: {operation!r}")
    return state.model_copy(
        update={
            "attributes": attributes,
            "constraints": constraints,
            "questions": questions,
            "conflicts": conflicts,
            "brief_versions": brief_versions,
            "approvals": approvals,
            "state_version": state.state_version + 1,
        }
    )
