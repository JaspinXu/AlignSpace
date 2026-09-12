import { useCallback, useEffect, useState } from 'react';
import { ApiClient, ApiError } from './api';
import type { JoinCode, Project, Role } from './types';
import { Workspace } from './workflow/Workspace';

const ROLE_LABEL: Record<Role, string> = { homeowner: '屋主', designer: '设计师' };
const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  analysing: '分析中',
  homeowner_review: '待屋主确认',
  designer_review: '待设计师反馈',
  alignment: '对齐中',
  awaiting_approval: '待审批',
  approved: '已批准',
  archived: '已归档',
};
const ROOM_TYPES = [
  { value: 'living_room', label: '客厅' },
  { value: 'bedroom', label: '卧室' },
];
const BUDGET_BANDS = [
  { value: 'under_15k_sgd', label: '低于 S$15,000' },
  { value: '15k_to_30k_sgd', label: 'S$15,000 – S$30,000' },
  { value: 'above_30k_sgd', label: '高于 S$30,000' },
];

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return '无法连接服务器，请检查网络后重试。';
    return error.message;
  }
  return '发生未知错误，请重试。';
}

export function App({ client = new ApiClient() }: { client?: ApiClient }) {
  const [session, setSession] = useState<'loading' | 'anonymous' | 'ready'>('loading');
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    setProjects(await client.get<Project[]>('/v1/projects'));
  }, [client]);

  useEffect(() => {
    let active = true;
    client
      .restore()
      .then(async () => {
        if (!active) return;
        if (!client.user) {
          setSession('anonymous');
          return;
        }
        await loadProjects();
        if (active) setSession('ready');
      })
      .catch((error) => {
        if (!active) return;
        setRestoreError(errorMessage(error));
        setSession('anonymous');
      });
    return () => {
      active = false;
    };
  }, [client, loadProjects]);

  const onAuthenticated = useCallback(async () => {
    await loadProjects();
    setSession('ready');
  }, [loadProjects]);

  const onLogout = useCallback(async () => {
    try {
      await client.logout();
    } catch {
      // Local state is already cleared; surface it as a local logout.
    }
    setSelectedProjectId(null);
    setProjects([]);
    setSession('anonymous');
  }, [client]);

  if (session === 'loading') {
    return (
      <div className="app-shell">
        <p>正在恢复会话…</p>
      </div>
    );
  }

  if (session === 'anonymous') {
    return <AuthScreen client={client} restoreError={restoreError} onAuthenticated={onAuthenticated} />;
  }

  const selected = projects.find((project) => project.id === selectedProjectId);
  if (selected) {
    return (
      <div className="app-shell">
        <nav className="topbar">
          <button type="button" onClick={() => setSelectedProjectId(null)}>
            返回我的项目
          </button>
          <button type="button" onClick={() => void onLogout()}>
            退出登录
          </button>
        </nav>
        <Workspace client={client} projectId={selected.id} />
      </div>
    );
  }

  return (
    <ProjectsScreen
      client={client}
      projects={projects}
      onRefresh={loadProjects}
      onOpen={setSelectedProjectId}
      onLogout={onLogout}
    />
  );
}

function AuthScreen({
  client,
  restoreError,
  onAuthenticated,
}: {
  client: ApiClient;
  restoreError: string | null;
  onAuthenticated: () => Promise<void>;
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (mode === 'register') {
      if (password.length < 15 || password.length > 128) {
        setError('密码长度需为 15–128 个字符。');
        return;
      }
      if (password !== confirm) {
        setError('两次输入的密码不一致。');
        return;
      }
    }
    setBusy(true);
    try {
      if (mode === 'register') await client.register(email, password);
      else await client.login(email, password);
      await onAuthenticated();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-shell auth">
      <h1>AlignSpace</h1>
      <p className="tagline">让家的想象，成为共同的方向。</p>
      {restoreError && <p className="error">{restoreError}</p>}
      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={mode === 'login'} onClick={() => setMode('login')}>
          登录
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'register'}
          onClick={() => setMode('register')}
        >
          注册
        </button>
      </div>
      <form onSubmit={submit}>
        <label htmlFor="email">邮箱</label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <label htmlFor="password">密码</label>
        <input
          id="password"
          type="password"
          autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {mode === 'register' && (
          <>
            <label htmlFor="confirm">确认密码</label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
            <p className="hint">
              首版不提供邮箱验证与密码找回，请使用密码管理器保存密码。
            </p>
          </>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {busy ? '处理中…' : mode === 'register' ? '注册' : '登录'}
        </button>
      </form>
    </div>
  );
}

function ProjectsScreen({
  client,
  projects,
  onRefresh,
  onOpen,
  onLogout,
}: {
  client: ApiClient;
  projects: Project[];
  onRefresh: () => Promise<void>;
  onOpen: (projectId: string) => void;
  onLogout: () => Promise<void>;
}) {
  const [roomType, setRoomType] = useState('living_room');
  const [budgetBand, setBudgetBand] = useState('15k_to_30k_sgd');
  const [consent, setConsent] = useState(false);
  const [joinCode, setJoinCode] = useState('');
  const [issued, setIssued] = useState<Record<string, JoinCode>>({});
  const [error, setError] = useState<string | null>(null);

  const createProject = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await client.post<Project>('/v1/projects', { roomType, budgetBand, consent });
      setConsent(false);
      await onRefresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  const join = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const project = await client.post<Project>('/v1/projects/join', { code: joinCode.trim() });
      setJoinCode('');
      await onRefresh();
      onOpen(project.id);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  const issueCode = async (project: Project) => {
    setError(null);
    try {
      const code = await client.post<JoinCode>(`/v1/projects/${project.id}/join-code`, {});
      setIssued((current) => ({ ...current, [project.id]: code }));
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  return (
    <div className="app-shell">
      <nav className="topbar">
        <h1>我的项目</h1>
        <button type="button" onClick={() => void onLogout()}>
          退出登录
        </button>
      </nav>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <ul className="project-list">
        {projects.map((project) => (
          <li key={project.id} className="project-card">
            <button type="button" className="project-open" onClick={() => onOpen(project.id)}>
              <strong>{ROOM_TYPES.find((item) => item.value === project.roomType)?.label ?? project.roomType}</strong>
              <span>{ROLE_LABEL[project.role]}</span>
              <span>{STATUS_LABEL[project.status] ?? project.status}</span>
              <span>{project.designerJoined ? '设计师已加入' : '等待设计师加入'}</span>
            </button>
            {project.role === 'homeowner' && (
              <div className="project-actions">
                <button type="button" onClick={() => void issueCode(project)}>
                  生成项目码
                </button>
                {issued[project.id] && (
                  <p className="join-code">
                    项目码 <code>{issued[project.id].code}</code>（24 小时内有效，仅可使用一次）
                  </p>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>

      <div className="panels">
        <form onSubmit={createProject} aria-label="创建项目">
          <h2>创建项目</h2>
          <label htmlFor="room-type">房间</label>
          <select id="room-type" value={roomType} onChange={(event) => setRoomType(event.target.value)}>
            {ROOM_TYPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <label htmlFor="budget-band">预算区间</label>
          <select id="budget-band" value={budgetBand} onChange={(event) => setBudgetBand(event.target.value)}>
            {BUDGET_BANDS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <label className="option">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
            />
            同意处理参考图片（演示样本）
          </label>
          <button type="submit">创建</button>
        </form>

        <form onSubmit={join} aria-label="加入项目">
          <h2>加入项目</h2>
          <label htmlFor="join-code">项目码</label>
          <input
            id="join-code"
            value={joinCode}
            onChange={(event) => setJoinCode(event.target.value)}
            required
          />
          <button type="submit">加入</button>
        </form>
      </div>
    </div>
  );
}
