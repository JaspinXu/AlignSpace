import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiClient } from '../api';
import { snapshot } from '../test/fixtures';
import { Workspace } from './Workspace';

const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

function setup(role: 'homeowner' | 'designer' = 'homeowner') {
  let state = snapshot(role);
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
