import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, type ApiClient } from '../api';
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


describe('SpaceBoard 3D sync resilience', () => {
  it('keeps the 3D draft and offers a retry when a concurrent write wins', async () => {
    const base = snapshot();
    const withObject: SpaceSnapshot = {
      ...base,
      plan: {
        ...base.plan!,
        objects: [
          {
            id: 'obj-1',
            roomId: 'room-a',
            kind: 'furniture',
            label: '沙发',
            geometry: { x: 2000, y: 2500, width: 1000, depth: 600, height: 800 },
          },
        ],
      },
    };
    const execute = vi.fn(async () => {
      throw new ApiError(409, 'STATE_VERSION_STALE', 'stale', { recoverable: true });
    });
    const client = {
      get: vi.fn(async (path: string) => (path.endsWith('/materials') ? catalogue : withObject)),
      execute,
    } as unknown as ApiClient;
    render(
      <SpaceBoard client={client} projectId="p1" role="homeowner" stateVersion={withObject.stateVersion} />,
    );
    await userEvent.click(await screen.findByRole('button', { name: '打开 3D 预览' }));

    const walls = [
      { id: 'n', start: { x: 0, y: 0 }, end: { x: 400, y: 0 } },
      { id: 'e', start: { x: 400, y: 0 }, end: { x: 400, y: 500 } },
      { id: 's', start: { x: 400, y: 500 }, end: { x: 0, y: 500 } },
      { id: 'w', start: { x: 0, y: 500 }, end: { x: 0, y: 0 } },
    ];
    const project = {
      activeFloorId: 'f',
      floors: [
        {
          id: 'f',
          walls,
          rooms: [{ id: 'r', name: '客厅', walls: ['n', 'e', 's', 'w'], alignspaceRoomId: 'room-a' }],
          furniture: [{ id: 'obj-1', position: { x: 150, y: 350 } }],
        },
      ],
    };
    const dispatch = (data: unknown) =>
      act(() => {
        window.dispatchEvent(
          new MessageEvent('message', { origin: 'http://127.0.0.1:4173', data }),
        );
      });
    dispatch({ type: 'alignspace:applied', protocol: 1 });
    dispatch({ type: 'alignspace:project', protocol: 1, project });

    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('button', { name: '重试同步' })).toBeVisible();
    expect(screen.getByText(/本次 3D 编辑未覆盖新版本/)).toBeVisible();
  });
});
