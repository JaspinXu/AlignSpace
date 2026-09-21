"""Explicit, testable catalogue of supported space materials.

Mapping a confirmed preference onto a space material must never be a guess.
This module is the single support list: a value either matches an option, is an
explicitly labelled approximation, or raises. Nothing here estimates cost or
claims the reference image used that material.
"""

import unicodedata
from enum import Enum

from pydantic import Field

from alignspace.domain.base import DomainModel


class Approximation(str, Enum):
    EXACT = "exact"
    APPROXIMATE = "approximate"


class MaterialTarget(str, Enum):
    FLOOR = "floor"
    WALL = "wall"


class UnsupportedMaterialError(ValueError):
    """Raised when a preference value has no supported material mapping."""


class MaterialOption(DomainModel):
    id: str
    label: str
    targets: list[MaterialTarget]
    colours: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class MaterialMatch(DomainModel):
    option_id: str
    approximation: Approximation
    note: str


MATERIAL_OPTIONS: dict[str, MaterialOption] = {
    option.id: option
    for option in (
        MaterialOption(
            id="floor.engineered-oak",
            label="实木复合地板（橡木）",
            targets=[MaterialTarget.FLOOR],
            colours=["pale oak", "warm oak", "honey oak"],
            patterns=["straight plank", "herringbone"],
        ),
        MaterialOption(
            id="floor.porcelain-tile",
            label="大规格瓷砖",
            targets=[MaterialTarget.FLOOR],
            colours=["light grey", "warm white"],
            patterns=["large format"],
        ),
        MaterialOption(
            id="floor.vinyl-plank",
            label="石塑锁扣地板",
            targets=[MaterialTarget.FLOOR],
            colours=["oak effect", "grey effect"],
            patterns=["straight plank"],
        ),
        MaterialOption(
            id="floor.microcement",
            label="微水泥",
            targets=[MaterialTarget.FLOOR],
            colours=["warm grey"],
            patterns=["seamless"],
        ),
        MaterialOption(
            id="wall.microcement",
            label="墙面微水泥",
            targets=[MaterialTarget.WALL],
            colours=["warm grey"],
            patterns=["seamless"],
        ),
    )
}

# Values that are close enough to a supported option to be offered, but only as a
# clearly labelled approximation the user has to confirm.
_APPROXIMATIONS: dict[str, tuple[str, str]] = {
    "marble": ("floor.porcelain-tile", "大理石效果以瓷砖近似呈现，非真实石材。"),
    "natural stone": ("floor.porcelain-tile", "天然石材以瓷砖近似呈现，观感相近但非同一材料。"),
    "concrete": ("floor.microcement", "清水混凝土以微水泥近似呈现。"),
    "laminate": ("floor.vinyl-plank", "强化复合以石塑锁扣地板近似呈现。"),
}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def material_option(option_id: str) -> MaterialOption | None:
    return MATERIAL_OPTIONS.get(option_id)


def supported_options(target: MaterialTarget) -> list[MaterialOption]:
    return [option for option in MATERIAL_OPTIONS.values() if target in option.targets]


def match_material(value: str, *, target: MaterialTarget) -> MaterialMatch:
    """Map a confirmed preference value onto a supported option.

    Exact matches cover the option id, its label, its colours and its patterns.
    Anything else must be an explicitly labelled approximation or is rejected.
    """
    wanted = _normalize(value)
    if not wanted:
        raise UnsupportedMaterialError("a material mapping requires a value")
    for option in MATERIAL_OPTIONS.values():
        if target not in option.targets:
            continue
        candidates = {
            _normalize(option.id),
            _normalize(option.label),
            *(_normalize(item) for item in option.colours),
            *(_normalize(item) for item in option.patterns),
        }
        if wanted in candidates:
            return MaterialMatch(
                option_id=option.id,
                approximation=Approximation.EXACT,
                note="",
            )
    approximation = _APPROXIMATIONS.get(wanted)
    if approximation is not None:
        option = MATERIAL_OPTIONS[approximation[0]]
        if target in option.targets:
            return MaterialMatch(
                option_id=option.id,
                approximation=Approximation.APPROXIMATE,
                note=approximation[1],
            )
    raise UnsupportedMaterialError(
        f"「{value}」不在受支持的{target.value}材料目录中，请改选受支持的取值。"
    )
