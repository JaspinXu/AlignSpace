import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ApiClient } from '../api';
import type { SpaceApprovalView } from '../types';
import { JointApproval } from './JointApproval';

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

function setup() {
  const execute = vi.fn(async (_write: { path: string; body: string }) => approvals);
  const client = {
    get: vi.fn(async () => approvals),
    execute,
  } as unknown as ApiClient;
  render(<JointApproval client={client} projectId="p1" stateVersion={4} />);
  return { execute };
}

describe('JointApproval', () => {
  it('shows the current brief and space versions with approval status', async () => {
    setup();
    expect(await screen.findByText(/说明书 v1 · 空间 v1/)).toBeVisible();
    expect(screen.getByText(/尚未双方批准/)).toBeVisible();
  });

  it('submits both brief and space hashes', async () => {
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
