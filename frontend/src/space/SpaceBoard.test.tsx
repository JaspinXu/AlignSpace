import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ApiClient } from '../api';
import type { SpaceSnapshot } from '../types';
import { SpaceBoard } from './SpaceBoard';

function snapshot(): SpaceSnapshot {
  return {
    projectId: 'p1',
    stateVersion: 4,
    version: 2,
    contentHash: 'a'.repeat(64),
    source: 'rectangular_dimensions',
    previousVersion: 1,
    createdBy: 'homeowner-1',
    createdRole: 'homeowner',
    createdAt: '2026-09-21T00:00:00Z',
    plan: {
      schemaVersion: '1.0.0',
      units: 'mm',
      rooms: [
        {
          id: 'room-a',
          name: '客厅',
          roomType: 'living_room',
          origin: { x: 0, y: 0 },
          size: { width: 4000, depth: 5000 },
          walls: [
            { id: 'wall-room-a-north', start: { x: 0, y: 0 }, end: { x: 4000, y: 0 }, thickness: 100 },
          ],
          floor: { id: 'floor-room-a', materialOptionId: null, bindingId: null },
        },
      ],
      objects: [],
    },
  };
}

const catalogue = {
  options: [
    { id: 'floor.engineered-oak', label: '实木复合地板（橡木）', targets: ['floor'], colours: [], patterns: [] },
  ],
};

function setup(role: 'homeowner' | 'designer' = 'homeowner', initial: SpaceSnapshot = snapshot()) {
  const execute = vi.fn(async (_write: { path: string; method: string; body: string }) => initial);
  const client = {
    get: vi.fn(async (path: string) => (path.endsWith('/materials') ? catalogue : initial)),
    execute,
  } as unknown as ApiClient;
  render(<SpaceBoard client={client} projectId="p1" role={role} stateVersion={initial.stateVersion} />);
  return { execute };
}

describe('SpaceBoard', () => {
  it('shows the persisted plan and its version', async () => {
    setup();
    expect(await screen.findByTestId('room-room-a')).toBeInTheDocument();
    expect(screen.getByText(/空间版本 v2/)).toBeVisible();
    expect(screen.getByRole('button', { name: '删除房间' })).toBeVisible();
  });

  it('lets the homeowner add a rectangular room through the versioned envelope', async () => {
    const { execute } = setup();
    await screen.findByTestId('room-room-a');
    await userEvent.click(screen.getByRole('button', { name: '添加房间' }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    const write = execute.mock.calls[0][0];
    expect(write.path).toBe('/v1/projects/p1/space/rooms');
    expect(write.method).toBe('POST');
    const body = JSON.parse(write.body);
    expect(body.expectedStateVersion).toBe(4);
    expect(body.data).toMatchObject({ name: '客厅', roomType: 'living_room', width: 4000, depth: 5000 });
  });

  it('does not let a designer delete a room', async () => {
    setup('designer');
    await screen.findByTestId('room-room-a');
    expect(screen.queryByRole('button', { name: '删除房间' })).toBeNull();
    // The designer still sees the shared draft.
    expect(screen.getByRole('button', { name: '添加房间' })).toBeVisible();
  });

  it('adds furniture to the selected room', async () => {
    const { execute } = setup();
    await screen.findByTestId('room-room-a');
    await userEvent.click(screen.getByRole('button', { name: '客厅' }));
    await userEvent.click(screen.getByRole('button', { name: '添加家具' }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    const write = execute.mock.calls[0][0];
    expect(write.path).toBe('/v1/projects/p1/space/objects');
    expect(JSON.parse(write.body).data).toMatchObject({ roomId: 'room-a', kind: 'furniture' });
  });
});
