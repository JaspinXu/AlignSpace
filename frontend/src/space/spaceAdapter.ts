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

function objectTransform(room: SpaceRoom, heightM: number): number[] {
  const cx = room.origin.x + room.size.width / 2;
  const cy = room.origin.y + room.size.depth / 2;
  return [
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    metres(cx), heightM / 2, metres(cy), 1,
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
    return {
      identifier: item.id,
      dimensions: [
        Math.max(metres(width), 0.01),
        Math.max(metres(height), 0.01),
        Math.max(metres(depth), 0.01),
      ],
      transform: room ? objectTransform(room, metres(height)) : objectTransform(
        { ...emptyRoom(), id: 'room-missing', name: '未分配' },
        metres(height),
      ),
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
  | { op: 'update_room'; roomId: string; name?: string; origin?: SpacePoint; size?: { width: number; depth: number } }
  | { op: 'create_room'; name: string; origin: SpacePoint; size: { width: number; depth: number } }
  | { op: 'delete_room'; roomId: string }
  | { op: 'update_object'; objectId: string; geometry: Record<string, unknown> }
  | { op: 'delete_object'; objectId: string };

type UpstreamWall = { id: string; start?: SpacePoint; end?: SpacePoint };
type UpstreamRoom = { id: string; name?: string; walls?: string[]; alignspaceRoomId?: string };
type UpstreamFurniture = { id: string; position?: SpacePoint };
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

function roomBox(
  room: UpstreamRoom,
  walls: Map<string, UpstreamWall>,
): { origin: SpacePoint; size: { width: number; depth: number } } | null {
  const points = (room.walls ?? [])
    .map((id) => walls.get(id))
    .filter((wall): wall is UpstreamWall => Boolean(wall?.start && wall?.end))
    .flatMap((wall) => [wall.start as SpacePoint, wall.end as SpacePoint])
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (points.length === 0) return null;
  const xs = points.map((point) => centimetresToMillimetres(point.x));
  const ys = points.map((point) => centimetresToMillimetres(point.y));
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const width = Math.max(...xs) - minX;
  const depth = Math.max(...ys) - minY;
  if (width < 1000 || depth < 1000) return null;
  return { origin: { x: minX, y: minY }, size: { width, depth } };
}

/**
 * Diff an upstream OpenPlan3D project against our authoritative plan and return
 * the controlled writes needed to persist manual edits. New rooms/objects are
 * created and (for the homeowner only) removed ones are deleted; everything
 * goes through the same permissioned, versioned API as the 2D panel.
 */
export function upstreamPatches(
  upstream: unknown,
  plan: SpacePlan,
  role: 'homeowner' | 'designer',
): SpaceSyncOp[] {
  const project = upstream as UpstreamProject | null;
  if (!project || !Array.isArray(project.floors)) return [];
  const floor =
    project.floors.find((item) => item.id === project.activeFloorId) ?? project.floors[0];
  if (!floor) return [];
  const wallById = new Map((floor.walls ?? []).map((wall) => [wall.id, wall]));
  const ops: SpaceSyncOp[] = [];

  const planRooms = new Map(plan.rooms.map((room) => [room.id, room]));
  const seenRooms = new Set<string>();
  for (const room of floor.rooms ?? []) {
    const ourId = room.alignspaceRoomId;
    if (!ourId) continue;
    seenRooms.add(ourId);
    const existing = planRooms.get(ourId);
    const box = roomBox(room, wallById);
    if (existing) {
      const changed: Extract<SpaceSyncOp, { op: 'update_room' }> = {
        op: 'update_room',
        roomId: ourId,
      };
      let touched = false;
      if (room.name && room.name !== existing.name) {
        changed.name = room.name;
        touched = true;
      }
      if (
        box &&
        (box.size.width !== existing.size.width ||
          box.size.depth !== existing.size.depth ||
          box.origin.x !== existing.origin.x ||
          box.origin.y !== existing.origin.y)
      ) {
        changed.origin = box.origin;
        changed.size = box.size;
        touched = true;
      }
      if (touched) ops.push(changed);
    } else if (box) {
      ops.push({ op: 'create_room', name: room.name || '房间', origin: box.origin, size: box.size });
    }
  }
  // Deletions are only meaningful once at least one room round-tripped, and only
  // the homeowner may delete.
  if (role === 'homeowner' && seenRooms.size > 0) {
    for (const room of plan.rooms) {
      if (!seenRooms.has(room.id)) ops.push({ op: 'delete_room', roomId: room.id });
    }
  }

  const planObjects = new Map(plan.objects.map((item) => [item.id, item]));
  const seenObjects = new Set<string>();
  for (const item of floor.furniture ?? []) {
    const ourId = item.id;
    if (!ourId) continue;
    seenObjects.add(ourId);
    const existing = planObjects.get(ourId);
    if (!existing) continue;
    const px = item.position?.x;
    const py = item.position?.y;
    // Ignore non-finite positions so a malformed editor state cannot corrupt
    // the authoritative geometry.
    if (typeof px !== 'number' || !Number.isFinite(px) || typeof py !== 'number' || !Number.isFinite(py)) {
      continue;
    }
    const x = centimetresToMillimetres(px);
    const y = centimetresToMillimetres(py);
    if (existing.geometry.x !== x || existing.geometry.y !== y) {
      ops.push({ op: 'update_object', objectId: ourId, geometry: { ...existing.geometry, x, y } });
    }
  }
  if (role === 'homeowner' && seenObjects.size > 0) {
    for (const item of plan.objects) {
      if (!seenObjects.has(item.id)) ops.push({ op: 'delete_object', objectId: item.id });
    }
  }
  return ops;
}
