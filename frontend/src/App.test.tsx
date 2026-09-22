import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { ApiClient } from './api';
import { briefSnapshot, snapshot } from './test/fixtures';

const json = (data: unknown) => new Response(JSON.stringify(data));
function setup(state = snapshot()) {
  const fetcher = vi.fn<typeof fetch>(async (url) => {
    if (url === '/v1/auth/refresh') return json({ accessToken: 'token', user: { id: 'u1' } });
    if (url === '/v1/projects') return json([state.project]);
    return json(state);
  });
  const channel = { postMessage: vi.fn(), close: vi.fn(), onmessage: null as ((event: { data: unknown }) => void) | null };
  const client = new ApiClient({ fetcher, channel, locks: null });
  return { fetcher, channel, client };
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});

describe('application session and navigation', () => {
  it('guards browser history into the reader and preserves the draft on cancellation', async () => {
    window.history.replaceState(null, '', '/?project=p1&view=brief&version=1');
    const env = setup(briefSnapshot());
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<App client={env.client} />);
    await userEvent.click(await screen.findByRole('button', { name: '返回工作区' }));
    fireEvent.change(await screen.findByLabelText('方案目标'), { target: { value: '历史导航未保存目标' } });
    act(() => window.history.back());
    await waitFor(() => expect(confirm).toHaveBeenCalled());
    expect(screen.getByLabelText('方案目标')).toHaveValue('历史导航未保存目标');
    expect(window.location.search).toBe('?project=p1&page=approval');
    confirm.mockReturnValue(true);
    act(() => window.history.back());
    await screen.findByRole('heading', { name: '设计说明书' });
    expect(window.location.search).toBe('?project=p1&view=brief&version=1');
    confirm.mockRestore();
  });

  it('restores a versioned reader link and removes reader parameters when returning', async () => {
    window.history.replaceState(null, '', '/?project=p1&view=brief&version=1');
    const env = setup(briefSnapshot());
    render(<App client={env.client} />);
    await screen.findByRole('heading', { name: '设计说明书' });
    expect(await screen.findByText('warm modern')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '返回工作区' }));
    await screen.findByRole('heading', { name: '方案审批' });
    expect(window.location.search).toBe('?project=p1&page=approval');
    await userEvent.click(screen.getByRole('button', { name: '查看设计说明书' }));
    await screen.findByRole('heading', { name: '设计说明书' });
    expect(window.location.search).toBe('?project=p1&view=brief&version=1');
    act(() => {
      window.history.replaceState(null, '', '/?project=p1');
      fireEvent.popState(window);
    });
    await screen.findByRole('heading', { name: '当前任务' });
  });

  it('preserves dirty goals when reader navigation is cancelled', async () => {
    window.history.replaceState(null, '', '/?project=p1');
    const env = setup(briefSnapshot());
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<App client={env.client} />);
    fireEvent.change(await screen.findByLabelText('方案目标'), { target: { value: '未保存目标' } });
    await userEvent.click(screen.getByRole('button', { name: '查看设计说明书' }));
    expect(confirm).toHaveBeenCalled();
    expect(screen.getByLabelText('方案目标')).toHaveValue('未保存目标');
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole('button', { name: '查看设计说明书' }));
    await screen.findByRole('heading', { name: '设计说明书' });
    expect(await screen.findByText('warm modern')).toBeVisible();
    confirm.mockRestore();
  });

  it('restores once across default-client rerenders', async () => {
    const env = setup();
    let refreshes = 0;
    vi.stubGlobal('BroadcastChannel', undefined);
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (url, init) => {
      // Bound the broken loop so the regression test cannot flood requests.
      if (url === '/v1/auth/refresh' && ++refreshes > 1) return new Promise<Response>(() => {});
      return env.fetcher(url, init);
    }));
    const view = render(<App />);
    await screen.findByRole('heading', { name: '我的项目' });
    view.rerender(<App />);
    await act(async () => {});
    expect(refreshes).toBe(1);
  });

  it('opens the project from the URL on reload and follows history navigation', async () => {
    window.history.replaceState(null, '', '/?project=p1');
    const env = setup();
    render(<App client={env.client} />);
    await screen.findByRole('heading', { name: '当前任务' });
    await userEvent.click(screen.getByRole('button', { name: '返回我的项目' }));
    expect(new URL(window.location.href).searchParams.has('project')).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: /客厅.*屋主/ }));
    expect(new URL(window.location.href).searchParams.get('project')).toBe('p1');
    act(() => {
      window.history.replaceState(null, '', '/');
      fireEvent.popState(window);
    });
    await screen.findByRole('heading', { name: '我的项目' });
  });

  it('removes authenticated content when another tab logs out', async () => {
    const env = setup();
    render(<App client={env.client} />);
    await screen.findByRole('heading', { name: '我的项目' });
    act(() => env.channel.onmessage?.({ data: { type: 'logout' } }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: '我的项目' })).not.toBeInTheDocument());
    expect(screen.getByRole('textbox', { name: '邮箱' })).toBeInTheDocument();
  });

  it('navigates workspace pages through the URL and clears the page when switching projects', async () => {
    window.history.replaceState(null, '', '/?project=p1');
    const env = setup();
    render(<App client={env.client} />);
    await screen.findByRole('heading', { name: '当前任务' });
    await userEvent.click(screen.getByRole('button', { name: '空间方案' }));
    expect(new URL(window.location.href).searchParams.get('page')).toBe('space');
    expect(screen.getByRole('button', { name: '空间方案' })).toHaveAttribute('aria-current', 'page');
    await userEvent.click(screen.getByRole('button', { name: '返回我的项目' }));
    const after = new URL(window.location.href).searchParams;
    expect(after.has('page')).toBe(false);
    expect(after.has('project')).toBe(false);
  });

  it('keeps the workspace mounted behind the reader so drafts are not lost', async () => {
    window.history.replaceState(null, '', '/?project=p1');
    const env = setup(briefSnapshot());
    render(<App client={env.client} />);
    await screen.findByRole('heading', { name: '当前任务' });
    await userEvent.click(screen.getByRole('button', { name: '查看设计说明书' }));
    await screen.findByRole('heading', { name: '设计说明书' });
    const workspace = document.querySelector('.workspace-shell');
    expect(workspace).not.toBeNull();
    expect(workspace!.closest('[hidden]')).not.toBeNull();
    // The hidden workspace is removed from the accessibility tree.
    expect(screen.queryByRole('navigation', { name: '工作区导航' })).toBeNull();
  });
});
