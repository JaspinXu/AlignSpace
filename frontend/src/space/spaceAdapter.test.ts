import { describe, expect, it } from 'vitest';

import type { SpacePlan } from '../types';
import {
  buildPreviewMessage,
  isAllowedPreviewOrigin,
  parseEditorMessage,
  planFingerprint,
  previewPatternNote,
  roomCorners,
  spaceExtent,
  toOpenPlan3DHandoff,
  upstreamDiff,
  upstreamPatches,
  type SpaceSyncOp,
} from './spaceAdapter';

const ORIGIN = 'http://127.0.0.1:4173';

function plan(): SpacePlan {
  return {
    schemaVersion: '1.0.0',
    units: 'mm',
    rooms: [
      {
        id: 'room-a',
        name: '客厅',
        roomType: 'living_room',
        origin: { x: 1000, y: 2000 },
        size: { width: 4000, depth: 5000 },
        walls: [
          { id: 'wall-room-a-north', start: { x: 1000, y: 2000 }, end: { x: 5000, y: 2000 }, thickness: 100 },
          { id: 'wall-room-a-east', start: { x: 5000, y: 2000 }, end: { x: 5000, y: 7000 }, thickness: 100 },
        ],
        floor: { id: 'floor-room-a', materialOptionId: null, bindingId: null },
      },
    ],
    objects: [
      {
        id: 'obj-1',
        roomId: 'room-a',
        kind: 'furniture',
        label: '沙发',
        geometry: { width: 2000, depth: 900, height: 800 },
      },
    ],
  };
}

describe('spaceAdapter', () => {
  it('derives absolute room corners and extent', () => {
    expect(roomCorners(plan().rooms[0])).toEqual([
      { x: 1000, y: 2000 },
      { x: 5000, y: 2000 },
      { x: 5000, y: 7000 },
      { x: 1000, y: 7000 },
    ]);
    expect(spaceExtent(plan())).toEqual({ minX: 1000, minY: 2000, width: 4000, height: 5000 });
  });

  it('produces a valid OpenPlan3D handoff from persisted geometry only', () => {
    const handoff = toOpenPlan3DHandoff(plan());
    expect(handoff.openplanHandoffVersion).toBe(1);
    expect(handoff.walls).toHaveLength(2);
    const [north] = handoff.walls;
    expect(north.identifier).toBe('wall-room-a-north');
    // dimensions are metres: length 4m, default height 2.7m, thickness 0.1m
    expect(north.dimensions[0]).toBeCloseTo(4);
    expect(north.dimensions[1]).toBeCloseTo(2.7);
    expect(north.dimensions[2]).toBeCloseTo(0.1);
    expect(north.transform).toHaveLength(16);
    expect(Math.hypot(north.transform[0], north.transform[2])).toBeGreaterThan(0);
    expect(handoff.sections[0].displayName).toBe('客厅');
    const [object] = handoff.objects;
    expect(object.dimensions[2]).toBeGreaterThan(0);
    expect(object.category.label).toBe('沙发');
  });

  it('passes a saved floor material into the 3D handoff', () => {
    const withMaterial = plan();
    withMaterial.rooms[0].floor.materialOptionId = 'floor.engineered-oak';
    const handoff = toOpenPlan3DHandoff(withMaterial);
    expect(handoff.alignspaceFloorMaterials).toEqual({ 'room-a': 'floor.engineered-oak' });
    expect(handoff.sections[0].color).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it('only trusts the exact local preview origin', () => {
    expect(isAllowedPreviewOrigin(ORIGIN, ORIGIN)).toBe(true);
    expect(isAllowedPreviewOrigin('http://localhost:4173', 'http://localhost:4173')).toBe(true);
    expect(isAllowedPreviewOrigin('http://127.0.0.1:4173', 'http://localhost:4173')).toBe(false);
    expect(isAllowedPreviewOrigin('https://evil.example', ORIGIN)).toBe(false);
    expect(isAllowedPreviewOrigin('https://openplan3d.example', 'https://openplan3d.example')).toBe(false);
    expect(isAllowedPreviewOrigin('*', '*')).toBe(false);
  });

  it('ignores messages from another origin and accepts the ready handshake', () => {
    expect(parseEditorMessage({ origin: 'https://evil.example', data: { type: 'alignspace:ready' } }, ORIGIN)).toBeNull();
    expect(parseEditorMessage({ origin: ORIGIN, data: { type: 'alignspace:ready' } }, ORIGIN)).toEqual({ kind: 'ready' });
    expect(parseEditorMessage({ origin: ORIGIN, data: { type: 'other' } }, ORIGIN)).toBeNull();
  });

  it('sends a protocol-tagged handoff message', () => {
    const message = buildPreviewMessage(plan());
    expect(message.type).toBe('alignspace:space');
    expect(message.protocol).toBe(1);
    expect(message.handoff.walls).toHaveLength(2);
  });
});

const upstreamProject = {
  activeFloorId: 'floor-x',
  floors: [
    {
      id: 'floor-x',
      walls: [
        { id: 'wall-room-a-north', start: { x: 100, y: 200 }, end: { x: 500, y: 200 } },
        { id: 'wall-room-a-east', start: { x: 500, y: 200 }, end: { x: 500, y: 700 } },
        { id: 'wall-room-a-south', start: { x: 500, y: 700 }, end: { x: 100, y: 700 } },
        { id: 'wall-room-a-west', start: { x: 100, y: 700 }, end: { x: 100, y: 200 } },
      ],
      rooms: [
        {
          id: 'detected-1',
          name: '会客厅',
          walls: ['wall-room-a-north', 'wall-room-a-east', 'wall-room-a-south', 'wall-room-a-west'],
          alignspaceRoomId: 'room-a',
        },
      ],
      furniture: [{ id: 'obj-1', position: { x: 25, y: 30 }, width: 200, depth: 90, height: 80 }],
    },
  ],
};

describe('spaceAdapter edit-back', () => {
  it('carries authoritative room and object ids into the handoff', () => {
    const handoff = toOpenPlan3DHandoff(plan());
    expect(handoff.alignspaceRoomIds).toEqual(['room-a']);
    expect(handoff.alignspaceObjectIds).toEqual(['obj-1']);
  });

  it('diffs a renamed room and a moved object into controlled writes', () => {
    const base = plan();
    const diff = upstreamDiff(upstreamProject, base, 'homeowner', { basePlan: base });
    expect(diff.ops).toContainEqual({ op: 'update_room', roomId: 'room-a', name: '会客厅' });
    expect(diff.ops).toContainEqual({
      op: 'update_object',
      objectId: 'obj-1',
      geometry: { width: 2000, depth: 900, height: 800, x: 250, y: 300 },
    });
    expect(diff.conflicts).toEqual([]);
  });

  it('does not let a designer delete rooms or objects', () => {
    const ops = upstreamPatches(upstreamProject, plan(), 'designer');
    expect(ops.some((op) => op.op === 'delete_room' || op.op === 'delete_object')).toBe(false);
  });

  it('produces a stable fingerprint for the same plan', () => {
    expect(planFingerprint(plan())).toBe(planFingerprint(plan()));
  });
});


const rectWalls = [
  { id: 'wall-room-a-north', start: { x: 100, y: 200 }, end: { x: 500, y: 200 } },
  { id: 'wall-room-a-east', start: { x: 500, y: 200 }, end: { x: 500, y: 700 } },
  { id: 'wall-room-a-south', start: { x: 500, y: 700 }, end: { x: 100, y: 700 } },
  { id: 'wall-room-a-west', start: { x: 100, y: 700 }, end: { x: 100, y: 200 } },
];

describe('spaceAdapter edit-back round two', () => {
  it('keeps a saved object position when rebuilding the handoff', () => {
    const positioned = plan();
    positioned.objects[0].geometry = { ...positioned.objects[0].geometry, x: 1500, y: 3500 };
    const transform = toOpenPlan3DHandoff(positioned).objects[0].transform;
    expect(transform[12]).toBeCloseTo(1.5);
    expect(transform[14]).toBeCloseTo(3.5);
  });

  it('creates a room drawn in the editor', () => {
    const upstream = {
      activeFloorId: 'f',
      floors: [
        {
          id: 'f',
          walls: [
            { id: 'n1', start: { x: 0, y: 0 }, end: { x: 400, y: 0 } },
            { id: 'e1', start: { x: 400, y: 0 }, end: { x: 400, y: 500 } },
            { id: 's1', start: { x: 400, y: 500 }, end: { x: 0, y: 500 } },
            { id: 'w1', start: { x: 0, y: 500 }, end: { x: 0, y: 0 } },
          ],
          rooms: [{ id: 'r', name: '书房', walls: ['n1', 'e1', 's1', 'w1'] }],
          furniture: [],
        },
      ],
    };
    const diff = upstreamDiff(upstream, plan(), 'homeowner');
    expect(diff.ops).toContainEqual({
      op: 'create_room',
      upstreamId: 'r',
      name: '书房',
      origin: { x: 0, y: 0 },
      size: { width: 4000, depth: 5000 },
    });
  });

  it('deletes the last room and object instead of silently keeping them', () => {
    const empty = { activeFloorId: 'f', floors: [{ id: 'f', walls: [], rooms: [], furniture: [] }] };
    const diff = upstreamDiff(empty, plan(), 'homeowner', { basePlan: plan() });
    expect(diff.ops).toContainEqual({ op: 'delete_room', roomId: 'room-a' });
    expect(diff.ops).toContainEqual({ op: 'delete_object', objectId: 'obj-1' });
  });

  it('sends a polygon outline for a non-rectangular room', () => {
    const walls = [
      { id: 'a', start: { x: 0, y: 0 }, end: { x: 400, y: 0 } },
      { id: 'b', start: { x: 400, y: 0 }, end: { x: 400, y: 200 } },
      { id: 'c', start: { x: 400, y: 200 }, end: { x: 200, y: 200 } },
      { id: 'd', start: { x: 200, y: 200 }, end: { x: 200, y: 500 } },
      { id: 'e', start: { x: 200, y: 500 }, end: { x: 0, y: 500 } },
      { id: 'f', start: { x: 0, y: 500 }, end: { x: 0, y: 0 } },
    ];
    const upstream = {
      activeFloorId: 'f',
      floors: [
        {
          id: 'f',
          walls,
          rooms: [
            {
              id: 'r',
              name: '客厅',
              walls: ['a', 'b', 'c', 'd', 'e', 'f'],
              alignspaceRoomId: 'room-a',
            },
          ],
          furniture: [],
        },
      ],
    };
    const diff = upstreamDiff(upstream, plan(), 'designer', { basePlan: plan() });
    const update = diff.ops.find((op) => op.op === 'update_room') as
      | Extract<ReturnType<typeof upstreamDiff>['ops'][number], { op: 'update_room' }>
      | undefined;
    expect(update?.outline).toHaveLength(6);
    expect(diff.unsupported).toEqual([]);
  });

  it('creates furniture added in the editor', () => {
    const upstream = {
      activeFloorId: 'f',
      floors: [
        {
          id: 'f',
          walls: rectWalls,
          rooms: [{ id: 'r', name: '客厅', walls: rectWalls.map((wall) => wall.id), alignspaceRoomId: 'room-a' }],
          furniture: [
            { id: 'new-f', position: { x: 200, y: 200 }, width: 80, depth: 60, height: 80, catalogId: 'sofa' },
          ],
        },
      ],
    };
    const diff = upstreamDiff(upstream, plan(), 'designer');
    expect(diff.ops).toContainEqual({
      op: 'create_object',
      upstreamId: 'new-f',
      roomId: 'room-a',
      kind: 'furniture',
      label: 'sofa',
      geometry: { x: 2000, y: 2000, width: 800, depth: 600, height: 800 },
    });
  });

  it('flags a confirmed pattern that the preview cannot render', () => {
    expect(previewPatternNote('herringbone')).toMatch(/不支持/);
    expect(previewPatternNote('pale oak')).toBeNull();
  });
});


const roomWithId = {
  id: 'r',
  name: '客厅',
  walls: rectWalls.map((wall) => wall.id),
  alignspaceRoomId: 'room-a',
};

describe('spaceAdapter round three safety', () => {
  it('rejects an invalid-coordinate snapshot instead of deleting the object', () => {
    const upstream = {
      activeFloorId: 'f',
      floors: [
        {
          id: 'f',
          walls: rectWalls,
          rooms: [roomWithId],
          furniture: [{ id: 'obj-1', position: { x: Number.NaN, y: 0 } }],
        },
      ],
    };
    const diff = upstreamDiff(upstream, plan(), 'homeowner', { basePlan: plan() });
    expect(diff.ops).toEqual([]);
    expect(diff.unsupported[0]).toMatch(/非法坐标/);
  });

  it('never deletes a collaborator object added after the base import', () => {
    const base = plan();
    const serverPlan: SpacePlan = {
      ...plan(),
      objects: [
        ...plan().objects,
        {
          id: 'obj-collab',
          roomId: 'room-a',
          kind: 'furniture',
          label: '协作者家具',
          geometry: { x: 2500, y: 2500, width: 800, depth: 800, height: 800 },
        },
      ],
    };
    const upstream = {
      activeFloorId: 'f',
      floors: [
        {
          id: 'f',
          walls: rectWalls,
          rooms: [roomWithId],
          furniture: [{ id: 'obj-1', position: { x: 250, y: 300 } }],
        },
      ],
    };
    const diff = upstreamDiff(upstream, serverPlan, 'homeowner', { basePlan: base });
    expect(
      diff.ops.some((op) => op.op === 'delete_object' && op.objectId === 'obj-collab'),
    ).toBe(false);
  });

  it('updates an editor-created object once its backend id is known', () => {
    const serverPlan: SpacePlan = {
      ...plan(),
      objects: [
        ...plan().objects,
        {
          id: 'obj-backend',
          roomId: 'room-a',
          kind: 'furniture',
          label: '沙发',
          geometry: { x: 1000, y: 1000, width: 800, depth: 600, height: 800 },
        },
      ],
    };
    const upstream = {
      activeFloorId: 'f',
      floors: [
        {
          id: 'f',
          walls: rectWalls,
          rooms: [roomWithId],
          furniture: [
            { id: 'obj-1', position: { x: 250, y: 300 } },
            { id: 'temp-1', position: { x: 120, y: 130 } },
          ],
        },
      ],
    };
    const idMap = new Map([['temp-1', 'obj-backend']]);
    const backendObject = serverPlan.objects.find((item) => item.id === 'obj-backend')!;
    const createdBase: SpacePlan = { ...plan(), objects: [backendObject] };
    const diff = upstreamDiff(upstream, serverPlan, 'designer', {
      basePlan: plan(),
      createdBase,
      idMap,
    });
    expect(diff.ops).toContainEqual({
      op: 'update_object',
      objectId: 'obj-backend',
      geometry: expect.objectContaining({ x: 1200, y: 1300 }),
    });
    expect(diff.ops.some((op) => op.op === 'create_object')).toBe(false);
    expect(diff.ops.some((op) => op.op === 'delete_object')).toBe(false);
  });
});


function planWithTwoObjects(): SpacePlan {
  const base = plan();
  return {
    ...base,
    objects: [
      {
        id: 'obj-a',
        roomId: 'room-a',
        kind: 'furniture',
        label: 'A',
        geometry: { x: 1000, y: 1000, width: 800, depth: 600, height: 800 },
      },
      {
        id: 'obj-b',
        roomId: 'room-a',
        kind: 'furniture',
        label: 'B',
        geometry: { x: 1000, y: 1000, width: 800, depth: 600, height: 800 },
      },
    ],
  };
}

function upstreamWithFurniture(positions: Record<string, { x: number; y: number }>) {
  return {
    activeFloorId: 'f',
    floors: [
      {
        id: 'f',
        walls: rectWalls,
        rooms: [roomWithId],
        furniture: Object.entries(positions).map(([id, position]) => ({
          id,
          position,
          width: 80,
          depth: 60,
          height: 80,
        })),
      },
    ],
  };
}

describe('spaceAdapter three-way merge', () => {
  it('does not revert a collaborator object the editor never touched', () => {
    const base = planWithTwoObjects();
    const theirs: SpacePlan = {
      ...base,
      objects: base.objects.map((item) =>
        item.id === 'obj-b' ? { ...item, geometry: { ...item.geometry, x: 3000 } } : item,
      ),
    };
    // The editor only moved A; B is still at the base position.
    const upstream = upstreamWithFurniture({ 'obj-a': { x: 200, y: 100 }, 'obj-b': { x: 100, y: 100 } });
    const diff = upstreamDiff(upstream, theirs, 'homeowner', { basePlan: base });
    expect(diff.ops).toContainEqual({
      op: 'update_object',
      objectId: 'obj-a',
      geometry: expect.objectContaining({ x: 2000 }),
    });
    expect(diff.ops.some((op) => op.op === 'update_object' && op.objectId === 'obj-b')).toBe(false);
    expect(diff.conflicts).toEqual([]);
  });

  it('reports a conflict when both sides change the same object field', () => {
    const base = planWithTwoObjects();
    const theirs: SpacePlan = {
      ...base,
      objects: base.objects.map((item) =>
        item.id === 'obj-a' ? { ...item, geometry: { ...item.geometry, x: 3000 } } : item,
      ),
    };
    const upstream = upstreamWithFurniture({ 'obj-a': { x: 200, y: 100 }, 'obj-b': { x: 100, y: 100 } });
    const diff = upstreamDiff(upstream, theirs, 'homeowner', { basePlan: base });
    expect(diff.ops.some((op) => op.op === 'update_object' && op.objectId === 'obj-a')).toBe(false);
    expect(diff.conflicts.join(' ')).toMatch(/双方修改/);
  });

  it('does not revert a collaborator room rename the editor never touched', () => {
    const base = plan();
    const theirs: SpacePlan = {
      ...base,
      rooms: base.rooms.map((room) => ({ ...room, name: '会客厅' })),
    };
    const upstream = {
      activeFloorId: 'f',
      floors: [
        { id: 'f', walls: rectWalls, rooms: [{ ...roomWithId, name: '客厅' }], furniture: [] },
      ],
    };
    const diff = upstreamDiff(upstream, theirs, 'homeowner', { basePlan: base });
    expect(diff.ops.some((op) => op.op === 'update_room')).toBe(false);
  });
});


describe('spaceAdapter independent field merge', () => {
  it('merges a user move with a collaborator size change on the same object', () => {
    const base = planWithTwoObjects();
    const theirs: SpacePlan = {
      ...base,
      objects: base.objects.map((item) =>
        item.id === 'obj-a' ? { ...item, geometry: { ...item.geometry, width: 1200 } } : item,
      ),
    };
    // The editor only moved obj-a; its width is still the base width.
    const upstream = upstreamWithFurniture({ 'obj-a': { x: 150, y: 100 }, 'obj-b': { x: 100, y: 100 } });
    const diff = upstreamDiff(upstream, theirs, 'homeowner', { basePlan: base });
    const update = diff.ops.find((op) => op.op === 'update_object' && op.objectId === 'obj-a') as
      | Extract<SpaceSyncOp, { op: 'update_object' }>
      | undefined;
    expect(update?.geometry).toMatchObject({ x: 1500, y: 1000, width: 1200 });
    expect(diff.conflicts).toEqual([]);
  });

  it('merges a user size change with a collaborator move on the same object', () => {
    const base = planWithTwoObjects();
    const theirs: SpacePlan = {
      ...base,
      objects: base.objects.map((item) =>
        item.id === 'obj-a' ? { ...item, geometry: { ...item.geometry, x: 3000 } } : item,
      ),
    };
    const upstream = {
      activeFloorId: 'f',
      floors: [
        {
          id: 'f',
          walls: rectWalls,
          rooms: [roomWithId],
          furniture: [
            { id: 'obj-a', position: { x: 100, y: 100 }, width: 100, depth: 60, height: 80 },
            { id: 'obj-b', position: { x: 100, y: 100 }, width: 80, depth: 60, height: 80 },
          ],
        },
      ],
    };
    const diff = upstreamDiff(upstream, theirs, 'homeowner', { basePlan: base });
    const update = diff.ops.find((op) => op.op === 'update_object' && op.objectId === 'obj-a') as
      | Extract<SpaceSyncOp, { op: 'update_object' }>
      | undefined;
    expect(update?.geometry).toMatchObject({ x: 3000, width: 1000 });
    expect(diff.conflicts).toEqual([]);
  });

  it('still applies a size change when only the position conflicts', () => {
    const base = planWithTwoObjects();
    const theirs: SpacePlan = {
      ...base,
      objects: base.objects.map((item) =>
        item.id === 'obj-a' ? { ...item, geometry: { ...item.geometry, x: 3000 } } : item,
      ),
    };
    const upstream = {
      activeFloorId: 'f',
      floors: [
        {
          id: 'f',
          walls: rectWalls,
          rooms: [roomWithId],
          furniture: [
            { id: 'obj-a', position: { x: 200, y: 100 }, width: 100, depth: 60, height: 80 },
            { id: 'obj-b', position: { x: 100, y: 100 }, width: 80, depth: 60, height: 80 },
          ],
        },
      ],
    };
    const diff = upstreamDiff(upstream, theirs, 'homeowner', { basePlan: base });
    const update = diff.ops.find((op) => op.op === 'update_object' && op.objectId === 'obj-a') as
      | Extract<SpaceSyncOp, { op: 'update_object' }>
      | undefined;
    expect(update?.geometry).toMatchObject({ x: 3000, width: 1000 });
    expect(diff.conflicts.join(' ')).toMatch(/位置被双方修改/);
  });
});
