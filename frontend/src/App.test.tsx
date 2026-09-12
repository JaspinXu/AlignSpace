import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { ApiClient } from './api';
import { snapshot } from './test/fixtures';

const json = (data: unknown) => new Response(JSON.stringify(data));
function setup() {
  const state = snapshot();
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
});
