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

// --- edit-back from the local OpenPlan3D editor ------------------------------

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
      name: string;
      origin: SpacePoint;
      size: { width: number; depth: number };
      outline?: SpacePoint[];
    }
  | { op: 'delete_room'; roomId: string }
  | { op: 'update_object'; objectId: string; geometry: Record<string, unknown> }
  | {
      op: 'create_object';
      roomId: string;
      kind: string;
      label: string;
      geometry: Record<string, unknown>;
    }
  | { op: 'delete_object'; objectId: string };

export type SpaceSyncDiff = { ops: SpaceSyncOp[]; unsupported: string[] };

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

function centimetresToMillimetres(value: number): number {
  return Math.round(value * 10);
}

function millimetres(value: number): number {
  return Math.round(value);
}

type RoomGeometry =
  | { kind: 'rect'; origin: SpacePoint; size: { width: number; depth: number } }
  | { kind: 'polygon'; origin: SpacePoint; size: { width: number; depth: number }; outline: SpacePoint[] }
  | { kind: 'unsupported' };

/** Order a room's wall endpoints into a simple polygon, in millimetres. */
function orderedOutline(room: UpstreamRoom, walls: Map<string, UpstreamWall>): SpacePoint[] | null {
  const segments = (room.walls ?? [])
    .map((id) => walls.get(id))
    .filter((wall): wall is UpstreamWall => Boolean(wall?.start && wall?.end))
    .filter((wall) => Number.isFinite(wall.start!.x) && Number.isFinite(wall.start!.y))
    .filter((wall) => Number.isFinite(wall.end!.x) && Number.isFinite(wall.end!.y));
  if (segments.length < 3) return null;
  const key = (point: SpacePoint) => `${millimetres(point.x)},${millimetres(point.y)}`;
  const points = new Map<string, SpacePoint>();
  const adjacency = new Map<string, string[]>();
  for (const segment of segments) {
    const start = {
      x: centimetresToMillimetres(segment.start!.x),
      y: centimetresToMillimetres(segment.start!.y),
    };
    const end = {
      x: centimetresToMillimetres(segment.end!.x),
      y: centimetresToMillimetres(segment.end!.y),
    };
    const startKey = key({ x: segment.start!.x, y: segment.start!.y });
    const endKey = key({ x: segment.end!.x, y: segment.end!.y });
    points.set(startKey, start);
    points.set(endKey, end);
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

function roomGeometry(room: UpstreamRoom, walls: Map<string, UpstreamWall>): RoomGeometry {
  const outline = orderedOutline(room, walls);
  if (!outline) return { kind: 'unsupported' };
  const xs = outline.map((point) => point.x);
  const ys = outline.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  const origin = { x: minX, y: minY };
  const size = { width: maxX - minX, depth: maxY - minY };
  if (size.width < 1000 || size.depth < 1000) return { kind: 'unsupported' };
  const rectangular = outline.every(
    (point) =>
      (point.x === minX || point.x === maxX) && (point.y === minY || point.y === maxY),
  );
  if (rectangular && outline.length === 4) return { kind: 'rect', origin, size };
  return { kind: 'polygon', origin, size, outline };
}

function findRoomForPoint(plan: SpacePlan, x: number, y: number): string | null {
  const inside = plan.rooms.find((room) => {
    const minX = room.origin.x;
    const minY = room.origin.y;
    return (
      x >= minX &&
      x <= minX + room.size.width &&
      y >= minY &&
      y <= minY + room.size.depth
    );
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
 * Diff an upstream OpenPlan3D project against our authoritative plan and return
 * the controlled writes needed to persist manual edits. New rooms/objects are
 * created, changed geometry is written (rectangular or polygonal) and removed
 * items are deleted; everything goes through the same permissioned, versioned
 * API as the 2D panel. Unsupported shapes are reported instead of silently
 * rewritten.
 */
export function upstreamDiff(
  upstream: unknown,
  plan: SpacePlan,
  role: 'homeowner' | 'designer',
): SpaceSyncDiff {
  const project = upstream as UpstreamProject | null;
  if (!project || !Array.isArray(project.floors)) return { ops: [], unsupported: [] };
  const floor =
    project.floors.find((item) => item.id === project.activeFloorId) ?? project.floors[0];
  if (!floor) return { ops: [], unsupported: [] };
  const wallById = new Map((floor.walls ?? []).map((wall) => [wall.id, wall]));
  const ops: SpaceSyncOp[] = [];
  const unsupported: string[] = [];

  const planRooms = new Map(plan.rooms.map((room) => [room.id, room]));
  const seenRooms = new Set<string>();
  for (const room of floor.rooms ?? []) {
    const ourId = room.alignspaceRoomId;
    const geometry = roomGeometry(room, wallById);
    if (!ourId) {
      // A room drawn in the editor has no backend identity yet: create it.
      if (geometry.kind === 'unsupported') {
        unsupported.push(`房间「${room.name || '未命名'}」形状不受支持，未同步。`);
        continue;
      }
      ops.push({
        op: 'create_room',
        name: room.name || '房间',
        origin: geometry.origin,
        size: geometry.size,
        ...(geometry.kind === 'polygon' ? { outline: geometry.outline } : {}),
      });
      continue;
    }
    seenRooms.add(ourId);
    const existing = planRooms.get(ourId);
    if (!existing) continue;
    const changed: Extract<SpaceSyncOp, { op: 'update_room' }> = {
      op: 'update_room',
      roomId: ourId,
    };
    let touched = false;
    if (room.name && room.name !== existing.name) {
      changed.name = room.name;
      touched = true;
    }
    if (geometry.kind === 'unsupported') {
      unsupported.push(`房间「${existing.name}」形状不受支持，仅同步名称。`);
    } else {
      const geometryChanged =
        geometry.kind === 'rect'
          ? geometry.size.width !== existing.size.width ||
            geometry.size.depth !== existing.size.depth ||
            geometry.origin.x !== existing.origin.x ||
            geometry.origin.y !== existing.origin.y
          : true;
      if (geometryChanged) {
        changed.origin = geometry.origin;
        changed.size = geometry.size;
        if (geometry.kind === 'polygon') changed.outline = geometry.outline;
        touched = true;
      }
    }
    if (touched) ops.push(changed);
  }
  if (role === 'homeowner') {
    for (const room of plan.rooms) {
      if (!seenRooms.has(room.id)) ops.push({ op: 'delete_room', roomId: room.id });
    }
  }

  const planObjects = new Map(plan.objects.map((item) => [item.id, item]));
  const seenObjects = new Set<string>();
  for (const item of floor.furniture ?? []) {
    const ourId = item.id;
    if (!ourId) continue;
    const px = item.position?.x;
    const py = item.position?.y;
    if (typeof px !== 'number' || !Number.isFinite(px) || typeof py !== 'number' || !Number.isFinite(py)) {
      continue;
    }
    const x = centimetresToMillimetres(px);
    const y = centimetresToMillimetres(py);
    const existing = planObjects.get(ourId);
    if (!existing) {
      // A furniture item added in the editor: create it in the containing room.
      const roomId = findRoomForPoint(plan, x, y);
      if (!roomId) {
        unsupported.push(`家具「${item.catalogId || ourId}」找不到所属房间，未同步。`);
        continue;
      }
      ops.push({
        op: 'create_object',
        roomId,
        kind: 'furniture',
        label: item.alignspaceLabel || item.catalogId || '家具',
        geometry: {
          x,
          y,
          width: centimetresToMillimetres(item.width ?? 80),
          depth: centimetresToMillimetres(item.depth ?? 80),
          height: centimetresToMillimetres(item.height ?? 80),
        },
      });
      continue;
    }
    seenObjects.add(ourId);
    if (existing.geometry.x !== x || existing.geometry.y !== y) {
      ops.push({ op: 'update_object', objectId: ourId, geometry: { ...existing.geometry, x, y } });
    }
  }
  if (role === 'homeowner') {
    for (const item of plan.objects) {
      if (!seenObjects.has(item.id)) ops.push({ op: 'delete_object', objectId: item.id });
    }
  }
  return { ops, unsupported };
}

/** Backwards-compatible view of the diff that only returns the writes. */
export function upstreamPatches(
  upstream: unknown,
  plan: SpacePlan,
  role: 'homeowner' | 'designer',
): SpaceSyncOp[] {
  return upstreamDiff(upstream, plan, role).ops;
}
