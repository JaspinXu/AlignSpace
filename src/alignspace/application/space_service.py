"""Space persistence service for the shared 2D/3D draft.

Authoritative data lives on the backend. Every substantive edit appends an
immutable :class:`SpaceVersion`; view-only changes (pan/zoom) never reach the
service, and a no-op patch appends no version. The homeowner and the designer
share write access to the draft, while deletion is restricted to the homeowner
so one party cannot silently remove an object another party bound a preference
to.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.service import AuthorizationError
from alignspace.domain.base import DomainModel
from alignspace.domain.enums import Role
from alignspace.domain.patches import StatePatch, UpsertSpaceVersion, apply_patch
from alignspace.domain.policies import StaleStateError
from alignspace.domain.space import (
    SCHEMA_VERSION,
    UNITS,
    Floor,
    Point,
    Room,
    RoomSize,
    SpaceObject,
    SpacePlan,
    SpaceVersion,
    Wall,
    build_rectangular_room,
    calculate_space_content_hash,
)
from alignspace.domain.space_catalog import (
    MaterialOption,
    MaterialTarget,
    supported_options,
)
from alignspace.persistence.repository import canonical_request_hash
from alignspace.persistence.uow import SqlAlchemyUnitOfWork


class SpaceStateError(ValueError):
    """Raised when a space edit is invalid for the current draft."""


class SpaceSnapshot(DomainModel):
    project_id: str
    state_version: int
    version: int | None
    content_hash: str | None
    source: str | None
    previous_version: int | None
    created_by: str | None
    created_role: Role | None
    created_at: datetime | None
    plan: SpacePlan | None


class SpaceVersionSummary(DomainModel):
    version: int
    content_hash: str
    source: str
    previous_version: int | None
    created_by: str
    created_role: Role
    created_at: datetime


class SpaceVersionList(DomainModel):
    project_id: str
    state_version: int
    versions: list[SpaceVersionSummary]


class MaterialCatalogue(DomainModel):
    options: list[MaterialOption]


MembershipCheck = Callable[[str, ActorContext], bool]

_ROOM_FIELDS = {"name", "roomType", "origin", "size", "width", "depth", "outline"}
_OBJECT_FIELDS = {"roomId", "kind", "label", "geometry"}


def _empty_plan() -> SpacePlan:
    return SpacePlan(schema_version=SCHEMA_VERSION, units=UNITS, rooms=[], objects=[])


def _latest(state: Any) -> SpaceVersion | None:
    if not state.space_versions:
        return None
    return max(state.space_versions, key=lambda item: item.version)


class SpaceService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        membership_check: MembershipCheck,
    ) -> None:
        self._session_factory = session_factory
        self._membership_check = membership_check

    # -- reads -----------------------------------------------------------------

    def snapshot(self, project_id: str, actor: ActorContext) -> SpaceSnapshot:
        self._authorize(project_id, actor)
        with self._session_factory() as session:
            state = self._load(session, project_id)
            return self._snapshot(state)

    def versions(self, project_id: str, actor: ActorContext) -> SpaceVersionList:
        self._authorize(project_id, actor)
        with self._session_factory() as session:
            state = self._load(session, project_id)
            ordered = sorted(state.space_versions, key=lambda item: item.version, reverse=True)
            return SpaceVersionList(
                project_id=state.project_id,
                state_version=state.state_version,
                versions=[
                    SpaceVersionSummary(
                        version=item.version,
                        content_hash=item.content_hash,
                        source=item.source,
                        previous_version=item.previous_version,
                        created_by=item.created_by,
                        created_role=item.created_role,
                        created_at=item.created_at,
                    )
                    for item in ordered
                ],
            )

    def materials(
        self, project_id: str, actor: ActorContext, target: str | None = None
    ) -> MaterialCatalogue:
        self._authorize(project_id, actor)
        if target is None:
            return MaterialCatalogue(options=list(_all_options()))
        return MaterialCatalogue(options=supported_options(MaterialTarget(target)))

    # -- edits -----------------------------------------------------------------

    def create_room(
        self, project_id: str, actor: ActorContext, envelope: WriteEnvelope[dict[str, object]]
    ) -> SpaceSnapshot:
        self._authorize(project_id, actor)
        data = self._data(envelope)
        self._reject_unknown(data, _ROOM_FIELDS)

        def mutate(plan: SpacePlan) -> tuple[SpacePlan, str]:
            room_id = f"room-{uuid4().hex}"
            name = self._required_name(data)
            room_type = self._room_type(data)
            if data.get("outline") is not None:
                room = self._room_from_outline(room_id, name, room_type, data["outline"])
                source = "manual_edit"
            else:
                room = self._rectangular_room(
                    room_id,
                    name,
                    room_type,
                    self._number(data.get("width"), "width"),
                    self._number(data.get("depth"), "depth"),
                    self._origin(data.get("origin")),
                )
                source = "rectangular_dimensions"
            return self._validate(plan.model_copy(update={"rooms": [*plan.rooms, room]})), source

        return self._mutate(
            project_id, actor, envelope, action="create_space_room", mutate=mutate
        )

    def update_room(
        self,
        project_id: str,
        room_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> SpaceSnapshot:
        self._authorize(project_id, actor)
        data = self._data(envelope)
        self._reject_unknown(data, _ROOM_FIELDS)

        def mutate(plan: SpacePlan) -> tuple[SpacePlan, str]:
            room = next((item for item in plan.rooms if item.id == room_id), None)
            if room is None:
                raise KeyError(f"room {room_id} not found")
            changes: dict[str, object] = {}
            if isinstance(data.get("name"), str):
                name = str(data["name"]).strip()
                if not name:
                    raise SpaceStateError("a room name cannot be blank")
                changes["name"] = name
            if data.get("roomType") is not None:
                changes["roomType"] = self._room_type(data)
            if data.get("origin") is not None:
                changes["origin"] = self._origin(data["origin"])
            size = data.get("size")
            width = data.get("width")
            depth = data.get("depth")
            if isinstance(size, dict):
                width = size.get("width")
                depth = size.get("depth")
            if width is not None or depth is not None:
                new_width = self._number(width, "width") if width is not None else room.size.width
                new_depth = self._number(depth, "depth") if depth is not None else room.size.depth
                rebuilt = build_rectangular_room(
                    room_id=room.id,
                    name=str(changes.get("name", room.name)),
                    width=new_width,
                    depth=new_depth,
                    room_type=str(changes.get("roomType", room.room_type)),
                )
                merged = rebuilt.model_copy(
                    update={
                        "origin": changes.get("origin", room.origin),
                        "floor": room.floor,
                    }
                )
                room = self._offset_walls(merged)
            else:
                room = room.model_copy(update=changes)
            rooms = [room if item.id == room_id else item for item in plan.rooms]
            return self._validate(plan.model_copy(update={"rooms": rooms})), "manual_edit"

        return self._mutate(
            project_id,
            actor,
            envelope,
            action="update_space_room",
            extra={"roomId": room_id},
            mutate=mutate,
        )

    def delete_room(
        self,
        project_id: str,
        room_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> SpaceSnapshot:
        self._authorize(project_id, actor)
        self._require_homeowner(actor, "delete a room")

        def mutate(plan: SpacePlan) -> tuple[SpacePlan, str]:
            if not any(item.id == room_id for item in plan.rooms):
                raise KeyError(f"room {room_id} not found")
            rooms = [item for item in plan.rooms if item.id != room_id]
            objects = [item for item in plan.objects if item.room_id != room_id]
            return (
                self._validate(plan.model_copy(update={"rooms": rooms, "objects": objects})),
                "manual_edit",
            )

        return self._mutate(
            project_id,
            actor,
            envelope,
            action="delete_space_room",
            extra={"roomId": room_id},
            mutate=mutate,
        )

    def create_object(
        self, project_id: str, actor: ActorContext, envelope: WriteEnvelope[dict[str, object]]
    ) -> SpaceSnapshot:
        self._authorize(project_id, actor)
        data = self._data(envelope)
        self._reject_unknown(data, _OBJECT_FIELDS)

        def mutate(plan: SpacePlan) -> tuple[SpacePlan, str]:
            room_id = data.get("roomId")
            if not isinstance(room_id, str) or not room_id.strip():
                raise SpaceStateError("an object requires a roomId")
            if not any(item.id == room_id for item in plan.rooms):
                raise KeyError(f"room {room_id} not found")
            obj = SpaceObject(
                id=f"obj-{uuid4().hex}",
                room_id=room_id,
                kind=str(data.get("kind", "furniture")),
                label=str(data.get("label", "")),
                geometry=self._geometry(data.get("geometry")),
            )
            return (
                self._validate(plan.model_copy(update={"objects": [*plan.objects, obj]})),
                "manual_edit",
            )

        return self._mutate(
            project_id, actor, envelope, action="create_space_object", mutate=mutate
        )

    def update_object(
        self,
        project_id: str,
        object_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> SpaceSnapshot:
        self._authorize(project_id, actor)
        data = self._data(envelope)
        self._reject_unknown(data, _OBJECT_FIELDS)

        def mutate(plan: SpacePlan) -> tuple[SpacePlan, str]:
            obj = next((item for item in plan.objects if item.id == object_id), None)
            if obj is None:
                raise KeyError(f"object {object_id} not found")
            changes: dict[str, object] = {}
            if data.get("roomId") is not None:
                room_id = data["roomId"]
                if not isinstance(room_id, str) or not any(
                    item.id == room_id for item in plan.rooms
                ):
                    raise KeyError(f"room {room_id} not found")
                changes["room_id"] = room_id
            if data.get("kind") is not None:
                changes["kind"] = str(data["kind"])
            if data.get("label") is not None:
                changes["label"] = str(data["label"])
            if data.get("geometry") is not None:
                changes["geometry"] = self._geometry(data["geometry"])
            updated = obj.model_copy(update=changes)
            objects = [updated if item.id == object_id else item for item in plan.objects]
            return self._validate(plan.model_copy(update={"objects": objects})), "manual_edit"

        return self._mutate(
            project_id,
            actor,
            envelope,
            action="update_space_object",
            extra={"objectId": object_id},
            mutate=mutate,
        )

    def delete_object(
        self,
        project_id: str,
        object_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> SpaceSnapshot:
        self._authorize(project_id, actor)
        self._require_homeowner(actor, "delete an object")

        def mutate(plan: SpacePlan) -> tuple[SpacePlan, str]:
            if not any(item.id == object_id for item in plan.objects):
                raise KeyError(f"object {object_id} not found")
            objects = [item for item in plan.objects if item.id != object_id]
            return self._validate(plan.model_copy(update={"objects": objects})), "manual_edit"

        return self._mutate(
            project_id,
            actor,
            envelope,
            action="delete_space_object",
            extra={"objectId": object_id},
            mutate=mutate,
        )

    # -- helpers ---------------------------------------------------------------

    def _mutate(
        self,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
        *,
        action: str,
        mutate: Callable[[SpacePlan], tuple[SpacePlan, str]],
        extra: dict[str, object] | None = None,
    ) -> SpaceSnapshot:
        request_hash = self._request_hash(action, project_id, actor, envelope, extra=extra)
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return SpaceSnapshot.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            current = self._plan(state) or _empty_plan()
            plan, source = mutate(current)
            payload = plan.model_dump(mode="json")
            latest = _latest(state)
            if latest is not None and latest.payload == payload:
                # A non-substantive edit (for example re-sending the same value)
                # must not manufacture a historical version.
                response = self._snapshot(state)
                self._record(
                    uow, project_id, envelope, request_hash, response, state.state_version
                )
                uow.commit()
                return response
            version = self._new_version(state, payload, actor, source)
            updated = apply_patch(
                state,
                StatePatch(
                    expected_state_version=state.state_version,
                    operations=[UpsertSpaceVersion(space_version=version)],
                ),
            )
            response = self._snapshot(updated)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record(uow, project_id, envelope, request_hash, response, updated.state_version)
            uow.commit()
            return response

    def _new_version(
        self,
        state: Any,
        payload: dict[str, object],
        actor: ActorContext,
        source: str,
    ) -> SpaceVersion:
        latest = _latest(state)
        return SpaceVersion(
            version=(latest.version + 1) if latest else 1,
            content_hash=calculate_space_content_hash(payload),
            payload=payload,
            created_by=actor.actor_id,
            created_role=actor.role,
            source=source,
            previous_version=latest.version if latest else None,
        )

    def _snapshot(self, state: Any) -> SpaceSnapshot:
        latest = _latest(state)
        return SpaceSnapshot(
            project_id=state.project_id,
            state_version=state.state_version,
            version=latest.version if latest else None,
            content_hash=latest.content_hash if latest else None,
            source=latest.source if latest else None,
            previous_version=latest.previous_version if latest else None,
            created_by=latest.created_by if latest else None,
            created_role=latest.created_role if latest else None,
            created_at=latest.created_at if latest else None,
            plan=self._plan(state),
        )

    @staticmethod
    def _plan(state: Any) -> SpacePlan | None:
        latest = _latest(state)
        if latest is None:
            return None
        return SpacePlan.model_validate(latest.payload)

    @staticmethod
    def _validate(plan: SpacePlan) -> SpacePlan:
        # Re-run all structural validators after a mutation, so a whitelisted edit
        # cannot bypass id uniqueness, room references or size bounds.
        return SpacePlan.model_validate(plan.model_dump(mode="python"))

    def _rectangular_room(
        self,
        room_id: str,
        name: str,
        room_type: str,
        width: float,
        depth: float,
        origin: Point,
    ) -> Room:
        room = build_rectangular_room(
            room_id=room_id, name=name, width=width, depth=depth, room_type=room_type
        )
        return self._offset_walls(room.model_copy(update={"origin": origin}))

    @staticmethod
    def _offset_walls(room: Room) -> Room:
        if room.origin.x == 0 and room.origin.y == 0:
            return room
        walls = [
            Wall(
                id=wall.id,
                start=Point(x=wall.start.x + room.origin.x, y=wall.start.y + room.origin.y),
                end=Point(x=wall.end.x + room.origin.x, y=wall.end.y + room.origin.y),
                thickness=wall.thickness,
            )
            for wall in room.walls
        ]
        return room.model_copy(update={"walls": walls})

    def _room_from_outline(
        self, room_id: str, name: str, room_type: str, outline: object
    ) -> Room:
        if not isinstance(outline, list) or len(outline) < 3:
            raise SpaceStateError("a hand-drawn room needs at least three outline points")
        points = [Point.model_validate(item) for item in outline]
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        width = max(xs) - min(xs)
        depth = max(ys) - min(ys)
        walls = [
            Wall(
                id=f"wall-{room_id}-{index}",
                start=points[index],
                end=points[(index + 1) % len(points)],
            )
            for index in range(len(points))
        ]
        return Room(
            id=room_id,
            name=name,
            room_type=room_type,
            origin=Point(x=min(xs), y=min(ys)),
            size=RoomSize(width=width, depth=depth),
            walls=walls,
            floor=Floor(id=f"floor-{room_id}"),
        )

    @staticmethod
    def _required_name(data: dict[str, object]) -> str:
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SpaceStateError("a room requires a name")
        return name.strip()

    @staticmethod
    def _room_type(data: dict[str, object]) -> str:
        value = data.get("roomType", "living_room")
        if not isinstance(value, str):
            raise SpaceStateError("roomType must be a string")
        return value

    @staticmethod
    def _origin(raw: object) -> Point:
        if raw is None:
            return Point()
        if not isinstance(raw, dict):
            raise SpaceStateError("origin must be an object with x and y")
        return Point.model_validate(raw)

    @staticmethod
    def _number(raw: object, field: str) -> float:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise SpaceStateError(f"{field} must be a number")
        return float(raw)

    @staticmethod
    def _geometry(raw: object) -> dict[str, object]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise SpaceStateError("geometry must be an object")
        return dict(raw)

    @staticmethod
    def _data(envelope: WriteEnvelope[dict[str, object]]) -> dict[str, object]:
        return envelope.data if isinstance(envelope.data, dict) else {}

    @staticmethod
    def _reject_unknown(data: dict[str, object], allowed: set[str]) -> None:
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise SpaceStateError(
                "unsupported field(s): " + ", ".join(unknown) + "; submit only whitelisted fields"
            )

    def _load(self, session: Session, project_id: str) -> Any:
        from alignspace.persistence.repository import ProjectRepository

        return ProjectRepository(session).load(project_id)

    def _authorize(self, project_id: str, actor: ActorContext) -> None:
        if not self._membership_check(project_id, actor):
            raise AuthorizationError("actor is not a project member with the requested role")

    @staticmethod
    def _require_homeowner(actor: ActorContext, action: str) -> None:
        if actor.role is not Role.HOMEOWNER:
            raise AuthorizationError(f"only a homeowner can {action}")

    @staticmethod
    def _check_version(state: Any, expected_version: int) -> None:
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


def _all_options() -> list[MaterialOption]:
    from alignspace.domain.space_catalog import MATERIAL_OPTIONS

    return list(MATERIAL_OPTIONS.values())
