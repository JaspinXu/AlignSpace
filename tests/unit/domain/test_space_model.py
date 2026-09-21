import pytest
from pydantic import ValidationError

from alignspace.domain.space import (
    MAX_DIMENSION,
    MIN_DIMENSION,
    SpaceObject,
    SpacePlan,
    build_rectangular_room,
    calculate_space_content_hash,
)
from alignspace.domain.space_catalog import (
    Approximation,
    MaterialTarget,
    UnsupportedMaterialError,
    match_material,
    supported_options,
)


def plan(**overrides) -> SpacePlan:
    room = build_rectangular_room(
        room_id="room-1", name="客厅", width=4000, depth=5000
    )
    return SpacePlan(rooms=[room], objects=overrides.pop("objects", []), **overrides)


def test_rectangular_room_has_stable_ids_and_four_walls():
    room = build_rectangular_room(room_id="room-1", name="客厅", width=4000, depth=5000)
    assert room.floor.id == "floor-room-1"
    assert [wall.id for wall in room.walls] == [
        "wall-room-1-north",
        "wall-room-1-east",
        "wall-room-1-south",
        "wall-room-1-west",
    ]
    assert room.size.width == 4000


@pytest.mark.parametrize("width,depth", [(MIN_DIMENSION - 1, 4000), (4000, MAX_DIMENSION + 1)])
def test_room_dimensions_are_bounded(width, depth):
    with pytest.raises(ValueError):
        build_rectangular_room(room_id="room-1", name="客厅", width=width, depth=depth)


def test_plan_rejects_duplicate_ids():
    room = build_rectangular_room(room_id="room-1", name="客厅", width=4000, depth=5000)
    with pytest.raises(ValidationError):
        SpacePlan(rooms=[room, room])


def test_plan_rejects_an_object_in_an_unknown_room():
    with pytest.raises(ValidationError):
        plan(objects=[SpaceObject(id="obj-1", room_id="ghost", label="沙发")])


def test_plan_rejects_unsupported_room_type():
    room = build_rectangular_room(room_id="room-1", name="客厅", width=4000, depth=5000)
    with pytest.raises(ValidationError):
        SpacePlan(rooms=[room.model_copy(update={"room_type": "garage"})])


def test_space_content_hash_is_stable_and_content_sensitive():
    first = plan()
    same = plan()
    assert calculate_space_content_hash(first.model_dump(mode="json")) == (
        calculate_space_content_hash(same.model_dump(mode="json"))
    )
    changed = plan(objects=[SpaceObject(id="obj-1", room_id="room-1", label="沙发")])
    assert calculate_space_content_hash(first.model_dump(mode="json")) != (
        calculate_space_content_hash(changed.model_dump(mode="json"))
    )


def test_exact_material_matches_cover_labels_colours_and_patterns():
    for value in ("pale oak", "herringbone", "实木复合地板（橡木）", "floor.engineered-oak"):
        match = match_material(value, target=MaterialTarget.FLOOR)
        assert match.option_id == "floor.engineered-oak"
        assert match.approximation == Approximation.EXACT


def test_approximation_is_labelled_and_never_silent():
    match = match_material("natural stone", target=MaterialTarget.FLOOR)
    assert match.approximation == Approximation.APPROXIMATE
    assert match.note


def test_unsupported_values_are_rejected():
    with pytest.raises(UnsupportedMaterialError):
        match_material("solid gold", target=MaterialTarget.FLOOR)
    with pytest.raises(UnsupportedMaterialError):
        match_material("", target=MaterialTarget.FLOOR)


def test_floor_and_wall_catalogues_stay_separate():
    assert {option.id for option in supported_options(MaterialTarget.WALL)} == {
        "wall.microcement"
    }
    # A wall-only option cannot be applied to a floor.
    with pytest.raises(UnsupportedMaterialError):
        match_material("墙面微水泥", target=MaterialTarget.FLOOR)
