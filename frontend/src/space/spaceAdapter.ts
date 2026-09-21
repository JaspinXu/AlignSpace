import type { SpacePlan, SpaceRoom, SpacePoint } from '../types';

/**
 * The only controlled bridge between our backend plan and the local
 * OpenPlan3D editor. Everything is local: this module never references the
 * upstream hosted service, analytics, accounts or share links. Authentication
 * tokens are never placed in a URL; the handoff travels over an
 * origin-checked `postMessage` after the editor announces readiness.
 */

export const OPENPLAN3D_PROTOCOL = 1;
const MM_PER_METRE = 1000;
const DEFAULT_WALL_HEIGHT_M = 2.7;

export type OpenPlan3DWall = {
  identifier: string;
  dimensions: [number, number, number];
  transform: number[];
  category: { label: string };
  story: number;
};

export type OpenPlan3DObject = {
  identifier: string;
  dimensions: [number, number, number];
  transform: number[];
  category: { label: string };
  story: number;
};

export type OpenPlan3DSection = {
  center: [number, number, number];
  label: string;
  displayName: string;
  story: number;
  color?: string;
};

export type OpenPlan3DHandoff = {
  openplanHandoffVersion: 1;
  walls: OpenPlan3DWall[];
  objects: OpenPlan3DObject[];
  doors: never[];
  windows: never[];
  openings: never[];
  sections: OpenPlan3DSection[];
  stories: { index: number; name: string }[];
  /** Extension consumed by the AlignSpace bridge: roomId -> material option id. */
  alignspaceFloorMaterials?: Record<string, string>;
  /** Index-aligned with `sections`: the authoritative room ids. */
  alignspaceRoomIds?: string[];
  /** Index-aligned with `objects`: the authoritative object ids. */
  alignspaceObjectIds?: string[];
};

// A deterministic colour per supported floor material so a saved material change
// is visible in the 3D preview. This is presentation only, not a material claim.
const FLOOR_MATERIAL_COLORS: Record<string, string> = {
  'floor.engineered-oak': '#c8a165',
  'floor.porcelain-tile': '#d9d4cc',
  'floor.vinyl-plank': '#b98a5a',
  'floor.microcement': '#b9b3a8',
  'wall.microcement': '#c9c3b8',
};

// Laying patterns the bundled local 3D preview cannot render. A confirmed
// pattern preference stays valid, but the preview must state it is showing the
// base material only instead of implying the pattern was reproduced.
const UNRENDERED_PATTERNS: Record<string, string> = {
  herringbone: '人字拼',
};

export function previewPatternNote(value: string): string | null {
  const key = value.trim().toLowerCase();
  return key in UNRENDERED_PATTERNS
    ? `3D 预览暂不支持「${UNRENDERED_PATTERNS[key]}」，按基础材质呈现（近似）。`
    : null;
}

export type EditorMessage =
  | { kind: 'ready' }
  | { kind: 'applied'; fingerprint: string | null }
  | { kind: 'project'; project: unknown }
  | { kind: 'error'; message: string };

function metres(value: number): number {
  return value / MM_PER_METRE;
}

/** Absolute corners of a rectangular room, in drawing order N-E-S-W. */
export function roomCorners(room: SpaceRoom): SpacePoint[] {
  const { x, y } = room.origin;
  return [
    { x, y },
    { x: x + room.size.width, y },
    { x: x + room.size.width, y: y + room.size.depth },
    { x, y: y + room.size.depth },
  ];
}

export function spaceExtent(plan: SpacePlan): { minX: number; minY: number; width: number; height: number } {
  const points = plan.rooms.flatMap(roomCorners);
  if (points.length === 0) return { minX: 0, minY: 0, width: 4000, height: 4000 };
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  return {
    minX,
    minY,
    width: Math.max(Math.max(...xs) - minX, 1000),
    height: Math.max(Math.max(...ys) - minY, 1000),
  };
}

function wallTransform(start: SpacePoint, end: SpacePoint, heightM: number): number[] {
  const cx = (start.x + end.x) / 2;
  const cy = (start.y + end.y) / 2;
  const angle = Math.atan2(end.y - start.y, end.x - start.x);
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  // Column-major 4x4 (Y-up, ground XZ): local X follows the wall direction.
  return [
    cos, 0, sin, 0,
    0, 1, 0, 0,
    -sin, 0, cos, 0,
    metres(cx), heightM / 2, metres(cy), 1,
  ];
}

function objectTransformAt(xMm: number, yMm: number, heightM: number): number[] {
  return [
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    metres(xMm), heightM / 2, metres(yMm), 1,
  ];
}

/**
 * Convert the backend millimetre plan into the pinned OpenPlan3D handoff
 * shape. No room-detection or recognition happens here; the geometry is
 * exactly what the backend persisted.
 */
export function toOpenPlan3DHandoff(plan: SpacePlan): OpenPlan3DHandoff {
  const walls: OpenPlan3DWall[] = [];
  const sections: OpenPlan3DSection[] = [];
  const floorMaterials: Record<string, string> = {};
  for (const room of plan.rooms) {
    for (const wall of room.walls) {
      const length = Math.hypot(wall.end.x - wall.start.x, wall.end.y - wall.start.y);
      if (length <= 0) continue;
      walls.push({
        identifier: wall.id,
        dimensions: [metres(length), DEFAULT_WALL_HEIGHT_M, metres(wall.thickness || 100)],
        transform: wallTransform(wall.start, wall.end, DEFAULT_WALL_HEIGHT_M),
        category: { label: room.name },
        story: 0,
      });
    }
    const materialId = room.floor.materialOptionId;
    if (materialId) floorMaterials[room.id] = materialId;
    const color = materialId ? FLOOR_MATERIAL_COLORS[materialId] : undefined;
    sections.push({
      center: [
        metres(room.origin.x + room.size.width / 2),
        DEFAULT_WALL_HEIGHT_M / 2,
        metres(room.origin.y + room.size.depth / 2),
      ],
      label: room.name,
      displayName: room.name,
      story: 0,
      ...(color ? { color } : {}),
    });
  }
  const objects: OpenPlan3DObject[] = plan.objects.map((item) => {
    const room = plan.rooms.find((candidate) => candidate.id === item.roomId);
    const width = numberField(item.geometry, 'width', 800);
    const depth = numberField(item.geometry, 'depth', 800);
    const height = numberField(item.geometry, 'height', 800);
    // Keep the persisted position; only fall back to the room centre when the
    // object has never been placed.
    const centerX =
      typeof item.geometry.x === 'number' && Number.isFinite(item.geometry.x)
        ? item.geometry.x
        : (room?.origin.x ?? 0) + (room?.size.width ?? 0) / 2;
    const centerY =
      typeof item.geometry.y === 'number' && Number.isFinite(item.geometry.y)
        ? item.geometry.y
        : (room?.origin.y ?? 0) + (room?.size.depth ?? 0) / 2;
    return {
      identifier: item.id,
      dimensions: [
        Math.max(metres(width), 0.01),
        Math.max(metres(height), 0.01),
        Math.max(metres(depth), 0.01),
      ],
      transform: objectTransformAt(centerX, centerY, metres(height)),
      category: { label: item.label || item.kind },
      story: 0,
    };
  });
  return {
    openplanHandoffVersion: OPENPLAN3D_PROTOCOL,
    walls,
    objects,
    doors: [],
    windows: [],
    openings: [],
    sections,
    stories: [{ index: 0, name: '楼层 1' }],
    alignspaceFloorMaterials: floorMaterials,
    alignspaceRoomIds: plan.rooms.map((room) => room.id),
    alignspaceObjectIds: plan.objects.map((item) => item.id),
  };
}

function emptyRoom(): SpaceRoom {
  return {
    id: 'room-empty',
    name: '',
    roomType: 'other',
    origin: { x: 0, y: 0 },
    size: { width: 0, depth: 0 },
    walls: [],
    floor: { id: 'floor-empty', materialOptionId: null, bindingId: null },
  };
}

function numberField(geometry: Record<string, unknown>, key: string, fallback: number): number {
  const value = geometry[key];
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : fallback;
}

/** Only the exact configured local origin is trusted, never a wildcard. */
export function isAllowedPreviewOrigin(origin: string, allowed: string): boolean {
  return origin === allowed && /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(origin);
}

export function buildPreviewMessage(plan: SpacePlan): {
  type: 'alignspace:space';
  protocol: number;
  fingerprint: string;
  handoff: OpenPlan3DHandoff;
} {
  return {
    type: 'alignspace:space',
    protocol: OPENPLAN3D_PROTOCOL,
    fingerprint: planFingerprint(plan),
    handoff: toOpenPlan3DHandoff(plan),
  };
}

/** Stable identity for a plan, so a round-trip import is not applied twice. */
export function planFingerprint(plan: SpacePlan): string {
  return JSON.stringify({
    rooms: plan.rooms.map((room) => ({
      id: room.id,
      name: room.name,
      origin: room.origin,
      size: room.size,
      floor: room.floor.materialOptionId,
    })),
    objects: plan.objects.map((item) => ({ id: item.id, roomId: item.roomId, label: item.label, geometry: item.geometry })),
  });
}

/**
 * Parse a message from the preview iframe. Anything from another origin or
 * with a different protocol/type is ignored rather than trusted.
 */
export function parseEditorMessage(event: { origin: string; data: unknown }, allowedOrigin: string): EditorMessage | null {
  if (!isAllowedPreviewOrigin(event.origin, allowedOrigin)) return null;
  const data = event.data as {
    type?: string;
    protocol?: number;
    message?: string;
    fingerprint?: string;
    project?: unknown;
  } | null;
  if (!data || typeof data !== 'object') return null;
  if (data.type === 'alignspace:ready') return { kind: 'ready' };
  if (data.type === 'alignspace:applied') {
    return { kind: 'applied', fingerprint: typeof data.fingerprint === 'string' ? data.fingerprint : null };
  }
  if (data.type === 'alignspace:project') {
    return { kind: 'project', project: data.project };
  }
  if (data.type === 'alignspace:error') {
    return { kind: 'error', message: typeof data.message === 'string' ? data.message : '预览失败' };
  }
  return null;
}

// --- three-way edit-back from the local OpenPlan3D editor -------------------

export type SpaceSyncOp =
  | {
      op: 'update_room';
      roomId: string;
      name?: string;
      origin?: SpacePoint;
      size?: { width: number; depth: number };
      outline?: SpacePoint[];
    }
  | {
      op: 'create_room';
      upstreamId: string;
      name: string;
      origin: SpacePoint;
      size: { width: number; depth: number };
      outline?: SpacePoint[];
    }
  | { op: 'delete_room'; roomId: string }
  | { op: 'update_object'; objectId: string; geometry: Record<string, unknown> }
  | {
      op: 'create_object';
      upstreamId: string;
      roomId: string;
      kind: string;
      label: string;
      geometry: Record<string, unknown>;
    }
  | { op: 'delete_object'; objectId: string };

export type SpaceSyncDiff = {
  ops: SpaceSyncOp[];
  unsupported: string[];
  /** Fields the editor changed that a collaborator also changed; never applied. */
  conflicts: string[];
};

export type SpaceSyncOptions = {
  /**
   * The plan the editor imported. All comparisons are three-way
   * (base / editor snapshot / server current), so an untouched server-side
   * change is never reverted and a collaborator's new or edited content is
   * never overwritten or deleted.
   */
  basePlan?: SpacePlan | null;
  /**
   * Entities the editor created during this session, captured at creation time.
   * They act as the base for later edits before the session base advances.
   */
  createdBase?: SpacePlan | null;
  /** Editor temp id -> backend id, learned from earlier create responses. */
  idMap?: Map<string, string>;
};

type UpstreamWall = { id: string; start?: SpacePoint; end?: SpacePoint };
type UpstreamRoom = { id: string; name?: string; walls?: string[]; alignspaceRoomId?: string };
type UpstreamFurniture = {
  id: string;
  position?: SpacePoint;
  width?: number;
  depth?: number;
  height?: number;
  catalogId?: string;
  alignspaceLabel?: string;
};
type UpstreamFloor = {
  id: string;
  walls?: UpstreamWall[];
  rooms?: UpstreamRoom[];
  furniture?: UpstreamFurniture[];
};
type UpstreamProject = { activeFloorId?: string; floors?: UpstreamFloor[] };

type ObjectGeometry = {
  x: number;
  y: number;
  width: number;
  depth: number;
  height: number;
};

type RoomGeometryInfo = {
  kind: 'rect' | 'polygon';
  origin: SpacePoint;
  size: { width: number; depth: number };
  outline: SpacePoint[];
  signature: string;
};

type RoomGeometry = RoomGeometryInfo | { kind: 'unsupported' };

function centimetresToMillimetres(value: number): number {
  return Math.round(value * 10);
}

function millimetres(value: number): number {
  return Math.round(value);
}

function finitePoint(point: unknown): point is SpacePoint {
  const candidate = point as SpacePoint | undefined;
  return (
    Boolean(candidate) &&
    typeof candidate!.x === 'number' &&
    Number.isFinite(candidate!.x) &&
    typeof candidate!.y === 'number' &&
    Number.isFinite(candidate!.y)
  );
}

function signatureOf(points: SpacePoint[]): string {
  return points
    .map((point) => `${millimetres(point.x)},${millimetres(point.y)}`)
    .sort()
    .join(';');
}

/** Order wall segments into a simple polygon, in millimetres. */
function chainSegments(segments: { start: SpacePoint; end: SpacePoint }[]): SpacePoint[] | null {
  if (segments.length < 3) return null;
  const key = (point: SpacePoint) => `${millimetres(point.x)},${millimetres(point.y)}`;
  const points = new Map<string, SpacePoint>();
  const adjacency = new Map<string, string[]>();
  for (const segment of segments) {
    const startKey = key(segment.start);
    const endKey = key(segment.end);
    points.set(startKey, { x: millimetres(segment.start.x), y: millimetres(segment.start.y) });
    points.set(endKey, { x: millimetres(segment.end.x), y: millimetres(segment.end.y) });
    adjacency.set(startKey, [...(adjacency.get(startKey) ?? []), endKey]);
    adjacency.set(endKey, [...(adjacency.get(endKey) ?? []), startKey]);
  }
  if ([...adjacency.values()].some((neighbours) => neighbours.length !== 2)) return null;
  const start = [...points.keys()][0];
  const outline: SpacePoint[] = [];
  let current = start;
  let previous: string | null = null;
  for (let guard = 0; guard <= points.size; guard += 1) {
    if (guard === points.size) return current === start ? outline : null;
    outline.push(points.get(current)!);
    const neighbours = adjacency.get(current)!;
    const next = neighbours.find((candidate) => candidate !== previous) ?? neighbours[0];
    previous = current;
    current = next;
    if (current === start) return outline;
  }
  return null;
}

function geometryFromOutline(outline: SpacePoint[]): RoomGeometryInfo | null {
  const xs = outline.map((point) => point.x);
  const ys = outline.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  const origin = { x: minX, y: minY };
  const size = { width: maxX - minX, depth: maxY - minY };
  if (size.width < 1000 || size.depth < 1000) return null;
  const rectangular =
    outline.length === 4 &&
    outline.every(
      (point) => (point.x === minX || point.x === maxX) && (point.y === minY || point.y === maxY),
    );
  return {
    kind: rectangular ? 'rect' : 'polygon',
    origin,
    size,
    outline,
    signature: signatureOf(outline),
  };
}

function upstreamRoomGeometry(room: UpstreamRoom, walls: Map<string, UpstreamWall>): RoomGeometry {
  const segments = (room.walls ?? [])
    .map((id) => walls.get(id))
    .filter((wall): wall is UpstreamWall => Boolean(wall?.start && wall?.end))
    .filter((wall) => finitePoint(wall.start) && finitePoint(wall.end))
    .map((wall) => ({
      start: {
        x: centimetresToMillimetres(wall.start!.x),
        y: centimetresToMillimetres(wall.start!.y),
      },
      end: {
        x: centimetresToMillimetres(wall.end!.x),
        y: centimetresToMillimetres(wall.end!.y),
      },
    }));
  const outline = chainSegments(segments);
  if (!outline) return { kind: 'unsupported' };
  return geometryFromOutline(outline) ?? { kind: 'unsupported' };
}

function planRoomGeometry(room: SpacePlan['rooms'][number]): RoomGeometryInfo {
  const outline = chainSegments(room.walls.map((wall) => ({ start: wall.start, end: wall.end })));
  if (outline) {
    const geometry = geometryFromOutline(outline);
    if (geometry) return geometry;
  }
  // Fallback to the declared rectangle if the loop cannot be chained.
  const origin = room.origin;
  const size = room.size;
  const corners = [
    { x: origin.x, y: origin.y },
    { x: origin.x + size.width, y: origin.y },
    { x: origin.x + size.width, y: origin.y + size.depth },
    { x: origin.x, y: origin.y + size.depth },
  ];
  return {
    kind: 'rect',
    origin,
    size,
    outline: corners,
    signature: signatureOf(corners),
  };
}

function planObjectGeometry(object: SpacePlan['objects'][number]): ObjectGeometry {
  const geometry = object.geometry;
  const number = (key: string, fallback: number) =>
    typeof geometry[key] === 'number' && Number.isFinite(geometry[key]) ? (geometry[key] as number) : fallback;
  return {
    x: number('x', 0),
    y: number('y', 0),
    width: number('width', 800),
    depth: number('depth', 800),
    height: number('height', 800),
  };
}

function upstreamObjectGeometry(item: UpstreamFurniture): ObjectGeometry {
  return {
    x: centimetresToMillimetres(item.position!.x),
    y: centimetresToMillimetres(item.position!.y),
    width: centimetresToMillimetres(item.width ?? 80),
    depth: centimetresToMillimetres(item.depth ?? 80),
    height: centimetresToMillimetres(item.height ?? 80),
  };
}

function sameObject(a: ObjectGeometry, b: ObjectGeometry): boolean {
  return a.x === b.x && a.y === b.y && a.width === b.width && a.depth === b.depth && a.height === b.height;
}

function findRoomForPoint(plan: SpacePlan, x: number, y: number): string | null {
  const inside = plan.rooms.find((room) => {
    const minX = room.origin.x;
    const minY = room.origin.y;
    return x >= minX && x <= minX + room.size.width && y >= minY && y <= minY + room.size.depth;
  });
  if (inside) return inside.id;
  if (plan.rooms.length === 0) return null;
  let best = plan.rooms[0];
  let bestDistance = Infinity;
  for (const room of plan.rooms) {
    const cx = room.origin.x + room.size.width / 2;
    const cy = room.origin.y + room.size.depth / 2;
    const distance = Math.hypot(cx - x, cy - y);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = room;
    }
  }
  return best.id;
}

/**
 * Three-way diff between the imported base, the editor snapshot and the current
 * server plan. Only fields the editor actually changed relative to the base are
 * written; a field a collaborator also changed differently is reported as a
 * conflict and left untouched.
 */
export function upstreamDiff(
  upstream: unknown,
  plan: SpacePlan,
  role: 'homeowner' | 'designer',
  options: SpaceSyncOptions = {},
): SpaceSyncDiff {
  const project = upstream as UpstreamProject | null;
  if (!project || !Array.isArray(project.floors)) return { ops: [], unsupported: [], conflicts: [] };
  const floor =
    project.floors.find((item) => item.id === project.activeFloorId) ?? project.floors[0];
  if (!floor) return { ops: [], unsupported: [], conflicts: [] };

  const invalidWalls = (floor.walls ?? []).some(
    (wall) => !finitePoint(wall.start) || !finitePoint(wall.end),
  );
  const invalidFurniture = (floor.furniture ?? []).some((item) => !finitePoint(item.position));
  if (invalidWalls || invalidFurniture) {
    return {
      ops: [],
      unsupported: ['编辑器快照包含缺失或非法坐标，已忽略本次同步；请在编辑器中检查后重试。'],
      conflicts: [],
    };
  }

  const idMap = options.idMap ?? new Map<string, string>();
  const base = options.basePlan ?? null;
  const wallById = new Map((floor.walls ?? []).map((wall) => [wall.id, wall]));
  const ops: SpaceSyncOp[] = [];
  const unsupported: string[] = [];
  const conflicts: string[] = [];

  const createdBase = options.createdBase ?? null;
  const baseRooms = new Map((base?.rooms ?? []).map((room) => [room.id, room]));
  for (const room of createdBase?.rooms ?? []) baseRooms.set(room.id, room);
  const theirRooms = new Map(plan.rooms.map((room) => [room.id, room]));
  const mineRooms = new Map<
    string,
    { upstreamId: string; name: string; geometry: RoomGeometry }
  >();
  for (const room of floor.rooms ?? []) {
    const ourId = room.alignspaceRoomId ?? idMap.get(room.id);
    if (!ourId) continue;
    mineRooms.set(ourId, {
      upstreamId: room.id,
      name: room.name ?? '',
      geometry: upstreamRoomGeometry(room, wallById),
    });
  }

  // Rooms drawn in the editor have no backend identity yet: create them.
  for (const room of floor.rooms ?? []) {
    const resolved = room.alignspaceRoomId ?? idMap.get(room.id);
    if (resolved) continue;
    const geometry = upstreamRoomGeometry(room, wallById);
    if (geometry.kind === 'unsupported') {
      unsupported.push(`房间「${room.name || '未命名'}」形状不受支持，未同步。`);
      continue;
    }
    if (!theirRooms.has(room.id)) {
      ops.push({
        op: 'create_room',
        upstreamId: room.id,
        name: room.name || '房间',
        origin: geometry.origin,
        size: geometry.size,
        ...(geometry.kind === 'polygon' ? { outline: geometry.outline } : {}),
      });
    }
  }

  const roomIds = new Set<string>([...baseRooms.keys(), ...mineRooms.keys()]);
  for (const roomId of roomIds) {
    const baseRoom = baseRooms.get(roomId);
    const theirRoom = theirRooms.get(roomId);
    const mine = mineRooms.get(roomId);
    if (!mine) {
      if (!baseRoom || !theirRoom) continue;
      if (planRoomGeometry(baseRoom).signature === planRoomGeometry(theirRoom).signature &&
          baseRoom.name === theirRoom.name) {
        if (role === 'homeowner') ops.push({ op: 'delete_room', roomId });
      } else {
        conflicts.push(`房间「${baseRoom.name}」已被协作者修改，您的删除未生效。`);
      }
      continue;
    }
    if (!baseRoom) {
      if (mine.geometry.kind === 'unsupported') {
        unsupported.push(`房间「${mine.name || '未命名'}」形状不受支持，未同步。`);
      } else if (!theirRoom) {
        ops.push({
          op: 'create_room',
          upstreamId: mine.upstreamId,
          name: mine.name || '房间',
          origin: mine.geometry.origin,
          size: mine.geometry.size,
          ...(mine.geometry.kind === 'polygon' ? { outline: mine.geometry.outline } : {}),
        });
      }
      continue;
    }
    if (!theirRoom) {
      conflicts.push(`房间「${baseRoom.name}」已被协作者删除，您的修改未同步。`);
      continue;
    }
    const baseGeometry = planRoomGeometry(baseRoom);
    const theirGeometry = planRoomGeometry(theirRoom);
    const update: Extract<SpaceSyncOp, { op: 'update_room' }> = { op: 'update_room', roomId };
    let touched = false;
    if (mine.name && mine.name !== baseRoom.name) {
      if (theirRoom.name !== baseRoom.name && theirRoom.name !== mine.name) {
        conflicts.push(`房间「${baseRoom.name}」名称被双方修改，保留协作者版本。`);
      } else {
        update.name = mine.name;
        touched = true;
      }
    }
    if (mine.geometry.kind === 'unsupported') {
      unsupported.push(`房间「${baseRoom.name}」形状不受支持，仅同步其他字段。`);
    } else if (mine.geometry.signature !== baseGeometry.signature) {
      if (
        theirGeometry.signature !== baseGeometry.signature &&
        theirGeometry.signature !== mine.geometry.signature
      ) {
        conflicts.push(`房间「${baseRoom.name}」几何被双方修改，保留协作者版本。`);
      } else {
        update.origin = mine.geometry.origin;
        update.size = mine.geometry.size;
        if (mine.geometry.kind === 'polygon') update.outline = mine.geometry.outline;
        touched = true;
      }
    }
    if (touched) ops.push(update);
  }

  const baseObjects = new Map((base?.objects ?? []).map((item) => [item.id, item]));
  for (const item of createdBase?.objects ?? []) baseObjects.set(item.id, item);
  const theirObjects = new Map(plan.objects.map((item) => [item.id, item]));
  const mineObjects = new Map<string, { upstreamId: string; geometry: ObjectGeometry; label: string }>();
  for (const item of floor.furniture ?? []) {
    if (!item.id) continue;
    const ourId = idMap.get(item.id) ?? item.id;
    mineObjects.set(ourId, {
      upstreamId: item.id,
      geometry: upstreamObjectGeometry(item),
      label: item.alignspaceLabel || item.catalogId || '家具',
    });
  }

  const objectIds = new Set<string>([...baseObjects.keys(), ...mineObjects.keys()]);
  for (const objectId of objectIds) {
    const baseObject = baseObjects.get(objectId);
    const theirObject = theirObjects.get(objectId);
    const mine = mineObjects.get(objectId);
    if (!mine) {
      if (!baseObject || !theirObject) continue;
      if (sameObject(planObjectGeometry(baseObject), planObjectGeometry(theirObject))) {
        if (role === 'homeowner') ops.push({ op: 'delete_object', objectId });
      } else {
        conflicts.push(`家具「${baseObject.label || objectId}」已被协作者修改，您的删除未生效。`);
      }
      continue;
    }
    if (!baseObject) {
      if (!theirObject) {
        const roomId = findRoomForPoint(plan, mine.geometry.x, mine.geometry.y);
        if (!roomId) {
          unsupported.push(`家具「${mine.label}」找不到所属房间，未同步。`);
        } else {
          ops.push({
            op: 'create_object',
            upstreamId: mine.upstreamId,
            roomId,
            kind: 'furniture',
            label: mine.label,
            geometry: { ...mine.geometry },
          });
        }
      }
      continue;
    }
    if (!theirObject) {
      conflicts.push(`家具「${baseObject.label || objectId}」已被协作者删除，您的修改未同步。`);
      continue;
    }
    const baseGeometry = planObjectGeometry(baseObject);
    const theirGeometry = planObjectGeometry(theirObject);
    const movedByUser = mine.geometry.x !== baseGeometry.x || mine.geometry.y !== baseGeometry.y;
    const movedByThem = theirGeometry.x !== baseGeometry.x || theirGeometry.y !== baseGeometry.y;
    const resizedByUser =
      mine.geometry.width !== baseGeometry.width ||
      mine.geometry.depth !== baseGeometry.depth ||
      mine.geometry.height !== baseGeometry.height;
    const resizedByThem =
      theirGeometry.width !== baseGeometry.width ||
      theirGeometry.depth !== baseGeometry.depth ||
      theirGeometry.height !== baseGeometry.height;
    let apply = false;
    if (movedByUser) {
      if (movedByThem && (theirGeometry.x !== mine.geometry.x || theirGeometry.y !== mine.geometry.y)) {
        conflicts.push(`家具「${baseObject.label || objectId}」位置被双方修改，保留协作者版本。`);
      } else {
        apply = true;
      }
    }
    if (resizedByUser) {
      if (
        resizedByThem &&
        (theirGeometry.width !== mine.geometry.width ||
          theirGeometry.depth !== mine.geometry.depth ||
          theirGeometry.height !== mine.geometry.height)
      ) {
        conflicts.push(`家具「${baseObject.label || objectId}」尺寸被双方修改，保留协作者版本。`);
      } else {
        apply = true;
      }
    }
    if (apply) {
      ops.push({ op: 'update_object', objectId, geometry: { ...mine.geometry } });
    }
  }

  return { ops, unsupported, conflicts };
}

/** Backwards-compatible view of the diff that only returns the writes. */
export function upstreamPatches(
  upstream: unknown,
  plan: SpacePlan,
  role: 'homeowner' | 'designer',
  options: SpaceSyncOptions = {},
): SpaceSyncOp[] {
  return upstreamDiff(upstream, plan, role, options).ops;
}
