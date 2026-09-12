import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiClient, ApiError, prepareWrite } from '../api';
import type { Attribute, Conflict, ProjectSnapshot } from '../types';

const BROAD_OPTIONS = [
  { label: '暖色灯光', keyword: 'lighting' },
  { label: '木质家具', keyword: 'furniture' },
  { label: '浅色墙面', keyword: 'colour' },
  { label: '自然材质', keyword: 'material' },
  { label: '开阔布局', keyword: 'layout' },
  { label: '温馨氛围', keyword: 'mood' },
];

const DIMENSIONS = [
  { value: 'style', label: '风格' },
  { value: 'colour', label: '色彩' },
  { value: 'material', label: '材质' },
  { value: 'lighting', label: '灯光' },
  { value: 'layout', label: '布局' },
  { value: 'furniture', label: '家具' },
  { value: 'mood', label: '氛围' },
  { value: 'function', label: '功能' },
];

const SAMPLE_FIXTURES = ['living-room-1', 'living-room-2', 'living-room-3'];

const ROLE_LABEL: Record<string, string> = { homeowner: '屋主', designer: '设计师' };
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

export function Workspace({ client, projectId }: { client: ApiClient; projectId: string }) {
  const [snapshot, setSnapshot] = useState<ProjectSnapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [value, setValue] = useState('');
  const [dimension, setDimension] = useState('style');
  const [showForm, setShowForm] = useState(true);
  const attributeId = useRef(`manual-${Math.random().toString(36).slice(2)}`);

  const load = useCallback(async () => {
    try {
      const next = await client.get<ProjectSnapshot>(`/v1/projects/${projectId}/state`);
      setSnapshot(next);
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof ApiError ? error.message : '无法加载项目状态。');
    }
  }, [client, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onFocus = () => {
      void load();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [load]);

  const pending = snapshot?.pendingQuestion ?? null;
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) void load();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [pending, load]);

  if (loadError && !snapshot) {
    return (
      <div className="workspace">
        <p role="alert" className="error">
          {loadError}
        </p>
        <button type="button" onClick={() => void load()}>
          重试
        </button>
      </div>
    );
  }

  if (!snapshot) {
    return (
      <div className="workspace">
        <p>正在加载项目状态…</p>
      </div>
    );
  }

  const { project, projectState } = snapshot;
  const isHomeowner = project.role === 'homeowner';

  const handleWriteError = async (error: unknown) => {
    if (error instanceof ApiError && error.status === 409) {
      setNotice('输入已保留。项目状态已被另一方更新，请检查后重新提交。');
      await load();
      return;
    }
    setNotice(error instanceof ApiError ? error.message : '提交失败，请重试。');
  };

  const submitAnswer = async () => {
    if (!pending) return;
    const keywords = BROAD_OPTIONS.filter((option) => selected.includes(option.keyword)).map(
      (option) => option.keyword,
    );
    if (keywords.length === 0) {
      setNotice('请先选择至少一个喜欢的部分。');
      return;
    }
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/questions/${pending.id}/answer`,
          'POST',
          project.stateVersion,
          { answer: `I also like the ${keywords.join(', ')}` },
        ),
      );
      setSelected([]);
      setNotice('回答已提交。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const savePreference = async () => {
    if (!value.trim()) {
      setNotice('请填写偏好内容。');
      return;
    }
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/attributes/${attributeId.current}`,
          'PATCH',
          project.stateVersion,
          { targetElement: 'living_room', dimension, value, status: 'confirmed' },
        ),
      );
      setValue('');
      setNotice('偏好已保存。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const registerSample = async () => {
    const index = project.assets.length % SAMPLE_FIXTURES.length;
    try {
      await client.execute(
        prepareWrite(`/v1/projects/${projectId}/assets`, 'POST', project.stateVersion, {
          fixtureId: SAMPLE_FIXTURES[index],
          mediaType: 'image/jpeg',
          sizeBytes: 1024,
        }),
      );
      setNotice('已登记一张演示样本。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const startAnalysis = async () => {
    try {
      await client.execute(
        prepareWrite(`/v1/projects/${projectId}/analysis-runs`, 'POST', project.stateVersion, {}),
      );
      setNotice('已启动样本分析。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  return (
    <div className="workspace">
      <header className="workspace-head">
        <div>
          <h1>{project.roomType === 'living_room' ? '客厅' : project.roomType}</h1>
          <p className="meta">
            {ROLE_LABEL[project.role] ?? project.role} ·{' '}
            {STATUS_LABEL[project.status] ?? project.status} · v{project.stateVersion}
          </p>
        </div>
        <p className="demo-badge">演示样本 · 模拟分析</p>
      </header>

      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}

      <div className="workspace-body">
        <main className="task">
          <h2>当前任务</h2>

          {pending && pending.targetRole !== project.role && (
            <p className="waiting">等待{ROLE_LABEL[pending.targetRole] ?? pending.targetRole}回答</p>
          )}

          {pending && pending.targetRole === 'homeowner' && isHomeowner && (
            <section aria-label="广泛偏好问题">
              <p className="question-text">除了已识别的部分，您还喜欢哪些？</p>
              <p className="question-hint">
                演示模式：请选择受支持的样本选项，系统会映射为后端可识别的内容。
              </p>
              <fieldset>
                <legend className="sr-only">喜欢的部分</legend>
                {BROAD_OPTIONS.map((option) => (
                  <label key={option.keyword} className="option">
                    <input
                      type="checkbox"
                      checked={selected.includes(option.keyword)}
                      onChange={(event) =>
                        setSelected((current) =>
                          event.target.checked
                            ? [...current, option.keyword]
                            : current.filter((item) => item !== option.keyword),
                        )
                      }
                    />
                    {option.label}
                  </label>
                ))}
              </fieldset>
              <button type="button" onClick={() => void submitAnswer()}>
                提交回答
              </button>
            </section>
          )}

          {pending && pending.targetRole === 'designer' && !isHomeowner && (
            <section aria-label="设计师反馈">
              <p className="question-text">请提交当前支持的约束反馈。</p>
              <button type="button" onClick={() => setNotice('设计师反馈功能将在后续迭代完善。')}>
                提交设计师反馈
              </button>
            </section>
          )}

          {isHomeowner && (
            <section aria-label="演示样本">
              <h3>参考样本</h3>
              <ul className="assets">
                {project.assets.map((asset) => (
                  <li key={asset.id}>{asset.fixtureId}（{asset.mediaType}）</li>
                ))}
              </ul>
              <button type="button" onClick={() => void registerSample()}>
                登记演示样本
              </button>
              <button type="button" onClick={() => void startAnalysis()}>
                启动分析
              </button>
            </section>
          )}

          {isHomeowner && (
            <section aria-label="显式偏好">
              <div className="section-head">
                <h3>显式偏好</h3>
                <button type="button" onClick={() => setShowForm((current) => !current)}>
                  新增偏好
                </button>
              </div>
              {showForm && (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void savePreference();
                  }}
                >
                  <label htmlFor="preference-dimension">偏好维度</label>
                  <select
                    id="preference-dimension"
                    value={dimension}
                    onChange={(event) => setDimension(event.target.value)}
                  >
                    {DIMENSIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  <label htmlFor="preference-value">偏好内容</label>
                  <input
                    id="preference-value"
                    value={value}
                    onChange={(event) => setValue(event.target.value)}
                  />
                  <button type="submit">保存偏好</button>
                </form>
              )}
            </section>
          )}
        </main>

        <aside className="sidebar">
          <h2>共享状态</h2>
          <section>
            <h3>偏好</h3>
            <ul>
              {projectState.attributes.map((attribute: Attribute) => (
                <li key={attribute.id}>
                  {attribute.dimension}：{attribute.value}（{attribute.status}）
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3>约束</h3>
            <ul>
              {projectState.constraints.map((constraint) => (
                <li key={constraint.id}>{constraint.statement}</li>
              ))}
            </ul>
          </section>
          <section>
            <h3>冲突</h3>
            <ul>
              {projectState.conflicts.map((conflict: Conflict) => (
                <li key={conflict.id}>
                  {conflict.summary}（{conflict.status}）
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3>审批</h3>
            <ul>
              {projectState.approvals.map((approval) => (
                <li key={`${approval.role}-${approval.briefVersion}`}>
                  {ROLE_LABEL[approval.role] ?? approval.role} 已批准 v{approval.briefVersion}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </div>
  );
}
