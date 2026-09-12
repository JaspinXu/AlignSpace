import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiClient } from '../api';
import { BRIEF_HASH, briefSnapshot, conflictSnapshot, snapshot } from '../test/fixtures';
import type { ProjectSnapshot } from '../types';
import { Workspace } from './Workspace';

const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

function setup(
  role: 'homeowner' | 'designer' = 'homeowner',
  initial: ProjectSnapshot = snapshot(role),
) {
  let state = initial;
  const writes: RequestInit[] = [];
  let conflict = false;
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url, init) => {
    if (url === '/v1/auth/refresh') return response({ accessToken: 'token', user: { id: 'u1', email: 'user@example.com', emailVerified: false } });
    if (init?.method === 'GET') return response(state);
    writes.push(init || {});
    if (conflict) {
      conflict = false;
      state = { ...state, projectState: { ...state.projectState, stateVersion: 5 }, project: { ...state.project, stateVersion: 5 } };
      return response({ error: { code: 'STATE_VERSION_STALE', message: 'stale', correlationId: 'c1', recoverable: true, details: {} } }, 409);
    }
    return response({ projectState: state.projectState });
  });
  const client = new ApiClient({ fetcher, locks: null, channel: null });
  return { client, fetcher, writes, conflict: () => { conflict = true; }, setState: (next: typeof state) => { state = next; } };
}

describe('role-aware work area', () => {
  it('lets the homeowner select broad preferences and sends supported English keywords', async () => {
    const env = setup();
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    await userEvent.click(await screen.findByRole('checkbox', { name: /暖色灯光/ }));
    await userEvent.click(screen.getByRole('button', { name: '提交回答' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    expect(JSON.parse(String(env.writes[0].body)).data.answer).toContain('lighting');
  });

  it('shows a designer the shared state without homeowner answer or sample controls', async () => {
    const env = setup('designer');
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    await screen.findByText('等待屋主回答');
    expect(screen.queryByRole('button', { name: '提交回答' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '登记演示样本' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新增偏好' })).not.toBeInTheDocument();
  });

  it('preserves an edited attribute on 409, refetches and uses a new key/version on deliberate resubmit', async () => {
    const env = setup();
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    const field = await screen.findByRole('textbox', { name: /偏好内容/ });
    await userEvent.clear(field);
    await userEvent.type(field, '柔和的阅读灯');
    env.conflict();
    await userEvent.click(screen.getByRole('button', { name: '保存偏好' }));
    await screen.findByText(/输入已保留/);
    expect(field).toHaveValue('柔和的阅读灯');
    expect(env.writes).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: '保存偏好' }));
    await waitFor(() => expect(env.writes).toHaveLength(2));
    const first = JSON.parse(String(env.writes[0].body));
    const second = JSON.parse(String(env.writes[1].body));
    expect(second.expectedStateVersion).toBe(5);
    expect(second.idempotencyKey).not.toBe(first.idempotencyKey);
    expect(second.data.value).toBe('柔和的阅读灯');
  });

  it('refreshes on focus and stops listening on navigation', async () => {
    const env = setup('designer');
    await env.client.restore();
    const view = render(<Workspace client={env.client} projectId="p1" />);
    await screen.findByText('等待屋主回答');
    const before = env.fetcher.mock.calls.length;
    fireEvent.focus(window);
    await waitFor(() => expect(env.fetcher.mock.calls.length).toBeGreaterThan(before));
    view.unmount();
    const after = env.fetcher.mock.calls.length;
    fireEvent.focus(window);
    expect(env.fetcher).toHaveBeenCalledTimes(after);
  });
});

describe('preference and conflict decisions', () => {
  it('lets the homeowner confirm a proposed visual observation', async () => {
    const env = setup('homeowner', conflictSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    await userEvent.click(await screen.findByRole('button', { name: '确认 warm ambient' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data).toEqual({ status: 'confirmed', value: 'warm ambient' });
    expect(env.writes[0].method).toBe('PATCH');
  });

  it('lets the homeowner reject a proposed visual observation', async () => {
    const env = setup('homeowner', conflictSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    await userEvent.click(await screen.findByRole('button', { name: '拒绝 warm ambient' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data.status).toBe('rejected');
  });

  it('hides homeowner preference controls from the designer', async () => {
    const env = setup('designer', conflictSnapshot('designer'));
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    await screen.findByText(/天然石材与预算冲突/);
    expect(screen.queryByRole('button', { name: '确认 warm ambient' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '拒绝 warm ambient' })).not.toBeInTheDocument();
  });

  it('resolves an open conflict with a written decision', async () => {
    const env = setup('homeowner', conflictSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    const field = await screen.findByRole('textbox', { name: /冲突解决说明/ });
    await userEvent.type(field, '改用低成本的石材效果饰面');
    await userEvent.click(screen.getByRole('button', { name: '提交冲突决定' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data).toEqual({ status: 'resolved', resolution: '改用低成本的石材效果饰面' });
  });
});

describe('designer review and brief approval', () => {
  it('lets a designer submit a review note', async () => {
    const base = snapshot('designer');
    const initial: ProjectSnapshot = {
      ...base,
      pendingQuestion: { ...base.pendingQuestion!, targetRole: 'designer', text: 'Designer review' },
      projectState: { ...base.projectState, waitReason: 'designer', currentNode: 'wait_designer' },
    };
    const env = setup('designer', initial);
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    const field = await screen.findByRole('textbox', { name: /设计师反馈/ });
    await userEvent.type(field, '预算内可用石材效果替代');
    await userEvent.click(screen.getByRole('button', { name: '提交设计师反馈' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data).toEqual({ note: '预算内可用石材效果替代' });
  });

  it('approves the exact brief version and content hash shown', async () => {
    const env = setup('homeowner', briefSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    await screen.findByText(/方案版本 v1/);
    await userEvent.click(await screen.findByRole('button', { name: '批准此版本' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data).toEqual({ contentHash: BRIEF_HASH });
  });

  it('shows an existing approval from the other party', async () => {
    const env = setup('designer', briefSnapshot('designer'));
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    expect(await screen.findByText(/屋主已批准 v1/)).toBeInTheDocument();
  });

  it('edits the brief into a new version using the full payload', async () => {
    const env = setup('designer', briefSnapshot('designer'));
    await env.client.restore();
    render(<Workspace client={env.client} projectId="p1" />);
    const field = await screen.findByRole('textbox', { name: /方案目标/ });
    await userEvent.clear(field);
    await userEvent.type(field, 'warm modern{enter}calm lighting');
    await userEvent.click(screen.getByRole('button', { name: '保存方案修改' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data.payload.project.id).toBe('p1');
    expect(body.data.payload.goals).toEqual(['warm modern', 'calm lighting']);
  });
});
