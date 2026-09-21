"""Shared domain primitives.

These live in their own module so that feature modules (for example
``alignspace.domain.preferences``) can define models without importing
``alignspace.domain.models``, which in turn composes them into ``ProjectState``.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from alignspace.domain.enums import EvidenceSource


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class DomainModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Evidence(DomainModel):
    source_type: EvidenceSource
    source_id: NonBlankString
    description: NonBlankString
