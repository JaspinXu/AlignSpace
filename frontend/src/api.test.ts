import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError, prepareWrite } from './api';

const user = { id: 'u1', email: 'owner@example.com', emailVerified: false as const };
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
const auth = (token = 'access-1') => json({ accessToken: token, user });
beforeEach(() => localStorage.clear());

describe('session and request boundaries', () => {
  it('finishes pending logout after reload instead of restoring the cookie session', async () => {
    let finish!: (response: Response) => void;
    const firstFetch = vi.fn<typeof fetch>().mockResolvedValueOnce(auth())
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    const first = new ApiClient({ fetcher: firstFetch, channel: null, locks: null });
    await first.restore();
    const logout = first.logout();
    const reloadFetch = vi.fn<typeof fetch>(async (url) => url === '/v1/auth/logout'
      ? new Response(null, { status: 204 }) : auth());
    const reloaded = new ApiClient({ fetcher: reloadFetch, channel: null, locks: null });
    await reloaded.restore();
    finish(new Response(null, { status: 204 }));
    await logout;
    expect(reloaded.user).toBeNull();
    expect(reloadFetch.mock.calls.map(([url]) => url)).toEqual(['/v1/auth/logout']);
  });
  it('serializes a new login behind logout cookie revocation', async () => {
    let finish!: (response: Response) => void;
    let queue: Promise<unknown> = Promise.resolve();
    const locks = { request: (_name: string, callback: () => Promise<unknown>) => {
      const result = queue.then(callback);
      queue = result.catch(() => undefined);
      return result;
    } };
    const fetcher = vi.fn<typeof fetch>(async (url) => {
      if (url === '/v1/auth/logout') return new Promise<Response>((resolve) => { finish = resolve; });
      return auth();
    });
    const client = new ApiClient({ fetcher, channel: null, locks });
    await client.restore();
    const logout = client.logout();
    await vi.waitFor(() => expect(finish).toBeDefined());
    const login = client.login('owner@example.com', 'a sufficiently long password');
    await Promise.resolve();
    const loginsWhileRevoking = fetcher.mock.calls.filter(([url]) => url === '/v1/auth/login').length;
    finish(new Response(null, { status: 204 }));
    await Promise.all([logout, login]);
    expect(loginsWhileRevoking).toBe(0);
    expect(client.user).toEqual(user);
  });
  it('clears and broadcasts logout before a slow revoke response arrives', async () => {
    let finish!: (response: Response) => void;
    const channel = { postMessage: vi.fn(), onmessage: null, close: vi.fn() };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(auth())
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    const client = new ApiClient({ fetcher, channel, locks: null });
    await client.restore();
    const logout = client.logout();
    const userWhilePending = client.user;
    const broadcastWhilePending = channel.postMessage.mock.calls.length;
    finish(new Response(null, { status: 204 }));
    await logout;
    expect(userWhilePending).toBeNull();
    expect(broadcastWhilePending).toBe(1);
  });

  it('ignores a login response that arrives after another tab logged out', async () => {
    let finish!: (response: Response) => void;
    const channel = { postMessage: vi.fn(), close: vi.fn(), onmessage: null as ((event: { data: unknown }) => void) | null };
    const fetcher = vi.fn<typeof fetch>(() => new Promise<Response>((resolve) => { finish = resolve; }));
    const client = new ApiClient({ fetcher, channel, locks: null });
    const login = client.login('owner@example.com', 'a sufficiently long password');
    channel.onmessage?.({ data: { type: 'logout' } });
    finish(auth());
    await login;
    expect(client.user).toBeNull();
  });
  it('does not refresh a session after logout while queued on a Web Lock', async () => {
    let release!: () => Promise<unknown>;
    const channel = { postMessage: vi.fn(), close: vi.fn(), onmessage: null as ((event: { data: unknown }) => void) | null };
    const fetcher = vi.fn<typeof fetch>(async () => auth());
    const client = new ApiClient({ fetcher, channel, locks: {
      request: (_name, callback) => new Promise((resolve) => { release = async () => resolve(await callback()); }),
    } });
    const restoring = client.restore();
    channel.onmessage?.({ data: { type: 'logout' } });
    await release();
    await restoring;
    expect(client.user).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('restores a session through a bodyless cookie refresh without persisting credentials', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(auth());
    const storage = vi.spyOn(Storage.prototype, 'setItem');
    const client = new ApiClient({ fetcher, channel: null, locks: null });
    await client.restore();
    expect(client.user).toEqual(user);
    expect(fetcher).toHaveBeenCalledWith('/v1/auth/refresh', expect.objectContaining({ method: 'POST', credentials: 'include' }));
    expect(fetcher.mock.calls[0][1]?.body).toBeUndefined();
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).has('Origin')).toBe(false);
    expect(storage).not.toHaveBeenCalled();
  });

  it('refreshes once on 401 then ends the session after the second 401', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(auth())
      .mockResolvedValueOnce(json({}, 401)).mockResolvedValueOnce(auth('access-2'))
      .mockResolvedValueOnce(json({}, 401));
    const client = new ApiClient({ fetcher, channel: null, locks: null });
    await client.restore();
    await expect(client.get('/v1/projects')).rejects.toMatchObject({ status: 401 });
    expect(fetcher.mock.calls.filter(([url]) => url === '/v1/projects')).toHaveLength(2);
    expect(fetcher.mock.calls.filter(([url]) => url === '/v1/auth/refresh')).toHaveLength(2);
    expect(new Headers(fetcher.mock.calls[3][1]?.headers).get('Authorization')).toBe('Bearer access-2');
    expect(client.user).toBeNull();
  });

  it('coalesces concurrent refreshes and takes the cross-tab Web Lock', async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => auth());
    const request = vi.fn(async (_name: string, callback: () => Promise<unknown>) => callback());
    const client = new ApiClient({ fetcher, locks: { request }, channel: null });
    await Promise.all([client.restore(), client.restore(), client.restore()]);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledWith('alignspace-auth-cookie', expect.any(Function));
  });

  it('clears local state and broadcasts logout even if the revoke request fails', async () => {
    const channel = { postMessage: vi.fn(), onmessage: null, close: vi.fn() };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(auth()).mockRejectedValueOnce(new TypeError('offline'));
    const client = new ApiClient({ fetcher, channel, locks: null });
    await client.restore();
    await expect(client.logout()).rejects.toBeInstanceOf(ApiError);
    expect(client.user).toBeNull();
    expect(channel.postMessage).toHaveBeenCalledWith({ type: 'logout' });
  });

  it('receives cross-tab logout and prevents an in-flight refresh from resurrecting the session', async () => {
    let finish!: (value: Response) => void;
    const channel: { postMessage: ReturnType<typeof vi.fn>; onmessage: ((event: { data: unknown }) => void) | null; close: ReturnType<typeof vi.fn> } = { postMessage: vi.fn(), onmessage: null, close: vi.fn() };
    const client = new ApiClient({ fetcher: vi.fn(() => new Promise<Response>(resolve => { finish = resolve; })), channel, locks: null });
    const refreshing = client.restore();
    await vi.waitFor(() => expect(finish).toBeDefined());
    channel.onmessage?.({ data: { type: 'logout' } });
    finish(auth());
    await refreshing.catch(() => undefined);
    expect(client.user).toBeNull();
  });
});

describe('workflow writes', () => {
  it('ends the session after a write retry also receives 401', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(auth())
      .mockResolvedValueOnce(json({}, 401)).mockResolvedValueOnce(auth('access-2'))
      .mockResolvedValueOnce(json({}, 401));
    const client = new ApiClient({ fetcher, locks: null, channel: null });
    await client.restore();
    await expect(client.execute(prepareWrite('/v1/projects/p/assets', 'POST', 0, {}))).rejects.toMatchObject({ status: 401 });
    expect(client.user).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(4);
  });
  it('retries an ambiguous network write with the exact serialized envelope', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(auth()).mockRejectedValueOnce(new TypeError('lost response')).mockResolvedValueOnce(json({ stateVersion: 3 }));
    const client = new ApiClient({ fetcher, locks: null, channel: null });
    await client.restore();
    const data = { answer: 'warm lighting' };
    const write = prepareWrite('/v1/projects/p/questions/q/answer', 'POST', 2, data);
    data.answer = 'edited after submit';
    await client.execute(write);
    expect(fetcher.mock.calls[1][1]?.body).toBe(fetcher.mock.calls[2][1]?.body);
    expect(JSON.parse(String(fetcher.mock.calls[2][1]?.body))).toEqual({ expectedStateVersion: 2, idempotencyKey: expect.any(String), data: { answer: 'warm lighting' } });
  });

  it('returns structured 409 errors without an automatic write retry', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(auth()).mockResolvedValueOnce(json({ error: { code: 'STATE_VERSION_STALE', message: 'stale', correlationId: 'trace-1', recoverable: true, details: {} } }, 409));
    const client = new ApiClient({ fetcher, locks: null, channel: null });
    await client.restore();
    await expect(client.execute(prepareWrite('/v1/projects/p/assets', 'POST', 0, {}))).rejects.toMatchObject({ status: 409, code: 'STATE_VERSION_STALE', correlationId: 'trace-1' });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});

import { newIdempotencyKey } from './api';

describe('asset transfer', () => {
  it('uploads multipart data without a JSON content type', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(auth())
      .mockResolvedValueOnce(json({ id: 'a1' }, 201));
    const client = new ApiClient({ fetcher, locks: null, channel: null });
    await client.restore();

    const file = new Blob(['x'], { type: 'image/png' });
    await client.upload('/v1/projects/p/assets', file, {
      expectedStateVersion: '0',
      idempotencyKey: 'k1',
    });

    const init = fetcher.mock.calls[1][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.headers as Headers).has('Content-Type')).toBe(false);
  });

  it('downloads image bytes as a blob', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(auth())
      .mockResolvedValueOnce(new Response(new Blob(['img']), { status: 200 }));
    const client = new ApiClient({ fetcher, locks: null, channel: null });
    await client.restore();

    const blob = await client.blob('/v1/projects/p/assets/a1/content');
    expect(blob).toBeInstanceOf(Blob);
  });

  it('generates distinct idempotency keys', () => {
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
  });
});
