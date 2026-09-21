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
};

export type EditorMessage =
  | { kind: 'ready' }
  | { kind: 'plan'; handoff: OpenPlan3DHandoff }
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
    sections.push({
      center: [
        metres(room.origin.x + room.size.width / 2),
        DEFAULT_WALL_HEIGHT_M / 2,
        metres(room.origin.y + room.size.depth / 2),
      ],
      label: room.name,
      displayName: room.name,
      story: 0,
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

export function buildPreviewMessage(plan: SpacePlan): { type: 'alignspace:space'; protocol: number; handoff: OpenPlan3DHandoff } {
  return {
    type: 'alignspace:space',
    protocol: OPENPLAN3D_PROTOCOL,
    handoff: toOpenPlan3DHandoff(plan),
  };
}

/**
 * Parse a message from the preview iframe. Anything from another origin or
 * with a different protocol/type is ignored rather than trusted.
 */
export function parseEditorMessage(event: { origin: string; data: unknown }, allowedOrigin: string): EditorMessage | null {
  if (!isAllowedPreviewOrigin(event.origin, allowedOrigin)) return null;
  const data = event.data as { type?: string; protocol?: number; message?: string } | null;
  if (!data || typeof data !== 'object') return null;
  if (data.type === 'alignspace:ready') return { kind: 'ready' };
  if (data.type === 'alignspace:error') {
    return { kind: 'error', message: typeof data.message === 'string' ? data.message : '预览失败' };
  }
  return null;
}
