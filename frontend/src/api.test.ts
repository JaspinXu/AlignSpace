import { describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError, prepareWrite } from './api';

const user = { id: 'u1', email: 'owner@example.com', emailVerified: false as const };
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
const auth = (token = 'access-1') => json({ accessToken: token, user });

describe('session and request boundaries', () => {
  it('restores a session through a bodyless cookie refresh without browser storage', async () => {
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
