import type { AuthResponse, User } from './types';

export type Fetcher = typeof fetch;

type ChannelLike = {
  postMessage: (message: unknown) => void;
  onmessage: ((event: { data: unknown }) => void) | null;
  close: () => void;
};

type LocksLike = {
  request: (name: string, callback: () => Promise<unknown>) => Promise<unknown>;
};

// Persist only logout intent, never credentials, so navigation cannot undo logout.
const LOGOUT_PENDING = 'alignspace-logout-pending';
function hasPendingLogout(): boolean {
  try { return localStorage.getItem(LOGOUT_PENDING) === '1'; }
  catch { return false; }
}
function markPendingLogout(pending: boolean): void {
  try {
    if (pending) localStorage.setItem(LOGOUT_PENDING, '1');
    else localStorage.removeItem(LOGOUT_PENDING);
  } catch { /* Storage may be disabled; in-memory logout still works. */ }
}

function createDefaultChannel(): ChannelLike | null {
  if (typeof BroadcastChannel === 'undefined') return null;
  const underlying = new BroadcastChannel('alignspace-auth');
  return {
    postMessage: (message: unknown) => underlying.postMessage(message),
    get onmessage() {
      return null;
    },
    set onmessage(next: ((event: { data: unknown }) => void) | null) {
      underlying.onmessage = next ? (event) => next(event) : null;
    },
    close: () => underlying.close(),
  };
}

export interface ApiClientOptions {
  fetcher?: Fetcher;
  channel?: ChannelLike | null;
  locks?: LocksLike | null;
}

type ErrorBody = {
  error?: {
    code?: string;
    message?: string;
    correlationId?: string;
    recoverable?: boolean;
    details?: Record<string, unknown>;
  };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly correlationId: string;
  readonly recoverable: boolean;
  readonly details: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    options: { correlationId?: string; recoverable?: boolean; details?: Record<string, unknown> } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.correlationId = options.correlationId ?? '';
    this.recoverable = options.recoverable ?? false;
    this.details = options.details ?? {};
  }
}

export interface PreparedWrite {
  path: string;
  method: string;
  body: string;
}

export function newIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto as Crypto | undefined;
  if (cryptoApi?.randomUUID) return cryptoApi.randomUUID();
  return `key-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Serialises the envelope immediately so later mutation of `data` cannot change
 * what a network retry sends. The key and body are fixed for the write lifetime.
 */
export function prepareWrite<T>(
  path: string,
  method: string,
  expectedStateVersion: number,
  data: T,
): PreparedWrite {
  const envelope = { expectedStateVersion, idempotencyKey: newIdempotencyKey(), data };
  return { path, method, body: JSON.stringify(envelope) };
}

export class ApiClient {
  user: User | null = null;

  private readonly fetcher: Fetcher;
  private readonly channel: ChannelLike | null;
  private readonly locks: LocksLike | null;
  private accessToken: string | null = null;
  private refreshPromise: Promise<void> | null = null;
  private generation = 0;
  private readonly sessionEndedListeners = new Set<() => void>();

  onSessionEnded(listener: () => void): () => void {
    this.sessionEndedListeners.add(listener);
    return () => { this.sessionEndedListeners.delete(listener); };
  }

  constructor(options: ApiClientOptions = {}) {
    this.fetcher = options.fetcher ?? fetch.bind(globalThis);
    this.locks =
      options.locks !== undefined
        ? options.locks
        : ((globalThis.navigator?.locks as unknown as LocksLike | undefined) ?? null);
    this.channel = options.channel !== undefined ? options.channel : createDefaultChannel();
    if (this.channel) {
      this.channel.onmessage = (event) => {
        const data = event.data as { type?: string } | null;
        if (data?.type === 'logout') this.clearSession();
      };
    }
  }

  /** Restores the session from the HttpOnly refresh cookie. */
  async restore(): Promise<void> {
    if (hasPendingLogout()) return this.logout();
    if (this.refreshPromise) return this.refreshPromise;
    const generation = this.generation;
    const promise = this.withAuthLock(async () => {
      if (generation === this.generation) await this.refresh();
    });
    this.refreshPromise = promise;
    try {
      await promise;
    } finally {
      if (this.refreshPromise === promise) this.refreshPromise = null;
    }
  }

  async register(email: string, password: string): Promise<void> {
    await this.authenticate('/v1/auth/register', email, password);
  }

  async login(email: string, password: string): Promise<void> {
    await this.authenticate('/v1/auth/login', email, password);
  }

  private async authenticate(path: string, email: string, password: string): Promise<void> {
    const generation = this.generation;
    await this.withAuthLock(async () => {
      if (generation !== this.generation) return;
      await this.acceptAuth(
        await this.fetcher(path, this.jsonRequest('POST', { email, password })),
        generation,
      );
    });
  }

  /** Clears local state, then revokes the server session; broadcasts to other tabs. */
  async logout(): Promise<void> {
    markPendingLogout(true);
    this.clearSession();
    this.channel?.postMessage({ type: 'logout' });
    let failure: unknown = null;
    try {
      await this.withAuthLock(async () => {
        const response = await this.send('/v1/auth/logout', { method: 'POST', keepalive: true });
        if (!response.ok) failure = await this.toError(response);
        else markPendingLogout(false);
      });
    } catch (error) {
      failure = error;
    }
    if (failure) {
      throw failure instanceof ApiError
        ? failure
        : new ApiError(0, 'LOGOUT_FAILED', '无法连接服务器，已在本地退出。', { recoverable: true });
    }
  }

  async get<T>(path: string): Promise<T> {
    const response = await this.requestWithRefresh(path, { method: 'GET' });
    return (await response.json()) as T;
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const response = await this.requestWithRefresh(path, this.jsonRequest('POST', body));
    return (await response.json()) as T;
  }

  async delete(path: string): Promise<void> {
    await this.requestWithRefresh(path, { method: 'DELETE' });
  }

  async upload<T>(path: string, file: Blob, fields: Record<string, string>): Promise<T> {
    const body = new FormData();
    for (const [key, value] of Object.entries(fields)) body.append(key, value);
    body.append('file', file);
    const response = await this.requestWithRefresh(path, { method: 'POST', body }, true, true);
    return (await response.json()) as T;
  }

  async blob(path: string): Promise<Blob> {
    const response = await this.requestWithRefresh(path, { method: 'GET' });
    return response.blob();
  }

  /** Runs a versioned workflow write, retrying a lost response with the same envelope. */
  async execute<T>(write: PreparedWrite): Promise<T> {
    const init: RequestInit = {
      method: write.method,
      headers: { 'Content-Type': 'application/json' },
      body: write.body,
    };
    let response: Response;
    try {
      response = await this.send(write.path, init);
    } catch {
      response = await this.send(write.path, init);
    }
    if (response.status === 401 && this.user) {
      try {
        await this.restore();
      } catch {
        // fall through to structured error below
      }
      if (this.user) response = await this.send(write.path, init);
    }
    if (response.status === 401) this.clearSession();
    if (!response.ok) throw await this.toError(response);
    return (await response.json()) as T;
  }

  private async requestWithRefresh(
    path: string,
    init: RequestInit,
    allowRefresh = true,
    retryNetwork = false,
  ): Promise<Response> {
    let response: Response;
    try {
      response = await this.send(path, init);
    } catch (error) {
      if (!retryNetwork) throw error;
      response = await this.send(path, init);
    }
    if (response.status !== 401) {
      if (!response.ok) throw await this.toError(response);
      return response;
    }
    if (allowRefresh && this.user) {
      try {
        await this.restore();
      } catch {
        // session could not be recovered
      }
      if (this.user) return this.requestWithRefresh(path, init, false);
    }
    this.clearSession();
    throw await this.toError(response);
  }

  private async refresh(): Promise<void> {
    const generation = this.generation;
    const response = await this.fetcher('/v1/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    });
    if (!response.ok) {
      this.clearSession();
      throw await this.toError(response);
    }
    const body = (await response.json()) as AuthResponse;
    if (this.generation !== generation) return; // logged out while refreshing
    this.accessToken = body.accessToken;
    this.user = body.user;
  }

  private withAuthLock(callback: () => Promise<void>): Promise<void> {
    if (this.locks) return this.locks.request('alignspace-auth-cookie', callback) as Promise<void>;
    return callback();
  }

  private async send(path: string, init: RequestInit): Promise<Response> {
    const headers = new Headers(init.headers);
    if (this.accessToken) headers.set('Authorization', `Bearer ${this.accessToken}`);
    return this.fetcher(path, { ...init, headers, credentials: 'include' });
  }

  private jsonRequest(method: string, body: unknown): RequestInit {
    return {
      method,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    };
  }

  private async acceptAuth(response: Response, generation: number): Promise<void> {
    if (!response.ok) throw await this.toError(response);
    const body = (await response.json()) as AuthResponse;
    if (generation !== this.generation) return;
    markPendingLogout(false);
    this.accessToken = body.accessToken;
    this.user = body.user;
  }

  private clearSession(): void {
    this.accessToken = null;
    this.user = null;
    this.generation += 1;
    for (const listener of this.sessionEndedListeners) listener();
  }

  private async toError(response: Response): Promise<ApiError> {
    let payload: ErrorBody | null = null;
    try {
      payload = (await response.json()) as ErrorBody;
    } catch {
      payload = null;
    }
    const error = payload?.error ?? {};
    return new ApiError(
      response.status,
      error.code ?? 'REQUEST_FAILED',
      error.message ?? `请求失败（${response.status}）。`,
      {
        correlationId: error.correlationId,
        recoverable: error.recoverable,
        details: error.details,
      },
    );
  }
}
