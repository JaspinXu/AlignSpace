import { describe, expect, it } from 'vitest';

import type { SpacePlan } from '../types';
import {
  buildPreviewMessage,
  isAllowedPreviewOrigin,
  parseEditorMessage,
  roomCorners,
  spaceExtent,
  toOpenPlan3DHandoff,
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
