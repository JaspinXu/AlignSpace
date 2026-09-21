import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ApiClient } from '../api';
import type { MaterialCatalogue, SpaceApprovalView, SpaceBindingList, SpacePlan, SpaceSnapshot } from '../types';
import { BindingPanel } from './BindingPanel';

const plan: SpacePlan = {
  schemaVersion: '1.0.0',
  units: 'mm',
  rooms: [
    {
      id: 'room-a',
      name: '客厅',
      roomType: 'living_room',
      origin: { x: 0, y: 0 },
      size: { width: 4000, depth: 5000 },
      walls: [],
      floor: { id: 'floor-room-a', materialOptionId: null, bindingId: null },
    },
  ],
  objects: [],
};

const materials: MaterialCatalogue = {
  options: [
    { id: 'floor.engineered-oak', label: '实木复合地板（橡木）', targets: ['floor'], colours: [], patterns: [] },
    { id: 'wall.microcement', label: '墙面微水泥', targets: ['wall'], colours: [], patterns: [] },
  ],
};

const bindingList: SpaceBindingList = {
  projectId: 'p1',
  stateVersion: 4,
  floorPreferences: [{ attributeId: 'pref-floor', value: 'natural stone', dimension: 'material' }],
  bindings: [
    {
      id: 'binding-1',
      roomId: 'room-a',
      floorObjectId: null,
      target: 'floor',
      attributeId: 'pref-floor',
      candidateId: null,
      materialOptionId: 'floor.porcelain-tile',
      approximation: 'approximate',
      note: '天然石材以瓷砖近似呈现。',
      status: 'active',
      boundBy: 'homeowner-1',
      boundAt: '2026-09-21T00:00:00Z',
      spaceVersion: 1,
      appliedSpaceVersion: null,
    },
  ],
};

const approvals: SpaceApprovalView = {
  projectId: 'p1',
  stateVersion: 4,
  briefVersion: 1,
  briefHash: 'b'.repeat(64),
  spaceVersion: 1,
  spaceHash: 'a'.repeat(64),
  approvals: [],
  approved: false,
};

const appliedSnapshot: SpaceSnapshot = {
  projectId: 'p1',
  stateVersion: 5,
  version: 2,
  contentHash: 'c'.repeat(64),
  source: 'material_application',
  previousVersion: 1,
  createdBy: 'homeowner-1',
  createdRole: 'homeowner',
  createdAt: '2026-09-21T00:00:00Z',
  plan,
};

function setup(role: 'homeowner' | 'designer' = 'homeowner') {
  const execute = vi.fn(async (_write: { path: string; method: string; body: string }) => appliedSnapshot);
  const client = {
    get: vi.fn(async (path: string) =>
      path.includes('/bindings') ? bindingList : approvals,
    ),
    execute,
  } as unknown as ApiClient;
  const onApplied = vi.fn();
  render(
    <BindingPanel
      client={client}
      projectId="p1"
      role={role}
      stateVersion={4}
      plan={plan}
      materials={materials}
      onApplied={onApplied}
    />,
  );
  return { execute, onApplied };
}

describe('BindingPanel', () => {
  it('shows the binding status and an explicit approximation note', async () => {
    setup();
    expect(await screen.findByText(/已绑定/)).toBeVisible();
    expect(screen.getAllByText(/近似替代/).length).toBeGreaterThan(0);
    expect(screen.getByText(/天然石材以瓷砖近似呈现/)).toBeVisible();
  });

  it('lets the homeowner bind a confirmed floor preference', async () => {
    const { execute } = setup();
    await screen.findByText(/已绑定/);
    await userEvent.selectOptions(screen.getByLabelText('已确认地板偏好'), 'pref-floor');
    await userEvent.selectOptions(screen.getByLabelText('房间'), 'room-a');
    await userEvent.click(screen.getByRole('button', { name: '绑定到房间' }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    const write = execute.mock.calls[0][0];
    // Auto-match keeps the preference value authoritative; no material override.
    expect(JSON.parse(write.body).data).toEqual({ attributeId: 'pref-floor', roomId: 'room-a' });
  });

  it('does not let a designer create a binding', async () => {
    setup('designer');
    await screen.findByText(/已绑定/);
    expect(screen.queryByRole('button', { name: '绑定到房间' })).toBeNull();
    // Applying an existing binding is still allowed for the shared draft.
    expect(screen.getByRole('button', { name: '应用材质到空间' })).toBeVisible();
  });

  it('applies an active binding and reports the new space snapshot', async () => {
    const { execute, onApplied } = setup();
    await userEvent.click(await screen.findByRole('button', { name: '应用材质到空间' }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    expect(execute.mock.calls[0][0].path).toBe('/v1/projects/p1/space/bindings/binding-1/apply');
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(appliedSnapshot));
  });

  it('sends both brief and space hashes for joint approval', async () => {
    const { execute } = setup();
    await userEvent.click(await screen.findByRole('button', { name: '联合批准当前方案' }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    const write = execute.mock.calls[0][0];
    expect(write.path).toBe('/v1/projects/p1/space/approvals');
    expect(JSON.parse(write.body).data).toEqual({
      briefVersion: 1,
      briefHash: 'b'.repeat(64),
      spaceVersion: 1,
      spaceHash: 'a'.repeat(64),
    });
  });
});
