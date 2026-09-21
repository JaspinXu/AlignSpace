import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiClient, ApiError, newIdempotencyKey, prepareWrite } from '../api';
import { PreferenceBoard } from '../preferences/PreferenceBoard';
import { SpaceBoard } from '../space/SpaceBoard';
import type { Asset, Attribute, Conflict, Constraint, ProjectSnapshot } from '../types';

const BROAD_OPTIONS: { label: string; keyword: string }[] = [];

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

const CONSTRAINT_CATEGORIES = [
  { value: 'budget', label: '预算' },
  { value: 'space', label: '空间' },
  { value: 'function', label: '功能' },
  { value: 'maintenance', label: '维护' },
  { value: 'timeline', label: '工期' },
  { value: 'safety', label: '安全' },
  { value: 'regulatory', label: '法规' },
  { value: 'availability', label: '供货' },
  { value: 'other', label: '其他' },
];

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

type QuestionDraft = {
  text: string;
  answer: string;
  parts: string[];
  decisions: Record<string, 'confirmed' | 'not_applicable'>;
  customs: Record<string, string>;
};

function emptyDraft(text: string): QuestionDraft {
  return { text, answer: '', parts: [], decisions: {}, customs: {} };
}

function draftText(draft: QuestionDraft): string {
  return draft.answer || draft.parts.join('、') || Object.keys(draft.decisions).join('、');
}

function AssetThumb({ client, projectId, asset }: { client: ApiClient; projectId: string; asset: Asset }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (asset.deleted) return;
    let active = true;
    let objectUrl: string | null = null;
    client
      .blob(`/v1/projects/${projectId}/assets/${asset.id}/content`)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [client, projectId, asset.id, asset.deleted]);
  if (asset.deleted) return <span className="asset-missing">已删除</span>;
  return url ? (
    <a href={url} target="_blank" rel="noreferrer" aria-label={`查看原图：${asset.originalFilename}`}>
      <img className="asset-thumb" src={url} alt={asset.originalFilename} />
    </a>
  ) : null;
}

export function Workspace({ client, projectId, onOpenBrief, briefLeaveGuard }: {
  client: ApiClient; projectId: string; onOpenBrief?: (version: number) => void;
  briefLeaveGuard?: { current: (() => boolean) | null };
}) {
  const [snapshot, setSnapshot] = useState<ProjectSnapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [questionDrafts, setQuestionDrafts] = useState<Record<string, QuestionDraft>>({});
  const [value, setValue] = useState('');
  const [dimension, setDimension] = useState('style');
  const [showForm, setShowForm] = useState(true);
  const [conflictResolution, setConflictResolution] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [goalsDraft, setGoalsDraft] = useState('');
  const [constraintCategory, setConstraintCategory] = useState('budget');
  const [constraintStatement, setConstraintStatement] = useState('');
  const [constraintRationale, setConstraintRationale] = useState('');
  const [constraintSeverity, setConstraintSeverity] = useState('important');
  const [constraintAppliesTo, setConstraintAppliesTo] = useState('');
  const [constraintAttributeId, setConstraintAttributeId] = useState('');
  const [constraintIncompatible, setConstraintIncompatible] = useState('');
  const [editingConstraintId, setEditingConstraintId] = useState<string | null>(null);
  const [editAttributeId, setEditAttributeId] = useState('');
  const [editAttributeValue, setEditAttributeValue] = useState('');
  const goalsDirty = useRef(false);
  const goalsRevision = useRef(0);

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
  const currentDraft = pending ? questionDrafts[pending.id] : undefined;
  const answerDraft = currentDraft?.answer ?? '';
  const partKeys = currentDraft?.parts ?? [];
  const decisions = currentDraft?.decisions ?? {};
  const customs = currentDraft?.customs ?? {};
  const questionKind = pending?.kind ?? 'detail';
  const isBroadQuestion = questionKind === 'broad_parts';
  const shouldPoll = Boolean(snapshot && (pending || snapshot.projectState.waitReason ||
    snapshot.projectState.status === 'awaiting_approval'));
  useEffect(() => {
    if (!shouldPoll) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) void load();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [shouldPoll, load]);

  const latestBrief =
    snapshot && snapshot.projectState.briefVersions.length > 0
      ? snapshot.projectState.briefVersions.reduce((latest, brief) =>
          brief.version > latest.version ? brief : latest,
        )
      : null;

  useEffect(() => {
    if (!latestBrief || goalsDirty.current) return;
    const goals = Array.isArray(latestBrief.payload.goals) ? latestBrief.payload.goals : [];
    setGoalsDraft(goals.map((goal) => String(goal)).join('\n'));
  }, [latestBrief?.version, latestBrief?.contentHash]);

  const confirmBriefLeave = () => {
    const hasQuestionInput = Object.values(questionDrafts).some((draft) =>
      draft.answer.trim() || draft.parts.length || Object.keys(draft.decisions).length ||
      Object.values(draft.customs).some((text) => text.trim()));
    const hasInput = goalsDirty.current || hasQuestionInput || [value, reviewNote, conflictResolution,
      constraintStatement, constraintRationale, constraintAppliesTo, constraintAttributeId,
      constraintIncompatible, editAttributeValue].some((text) => text.trim());
    return !hasInput || window.confirm('有未保存的输入，离开后将丢弃。是否继续查看设计说明书？');
  };

  useEffect(() => {
    if (!briefLeaveGuard) return;
    briefLeaveGuard.current = confirmBriefLeave;
    return () => { briefLeaveGuard.current = null; };
  });

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
  const isDesigner = project.role === 'designer';
  const openConflict =
    projectState.conflicts.find((conflict) => conflict.status === 'open') ?? null;
  const deletedAssetIds = new Set(project.assets.filter((asset) => asset.deleted).map((asset) => asset.id));
  const assetName = (assetId?: string | null) =>
    project.assets.find((asset) => asset.id === assetId)?.originalFilename ??
    (assetId ? `图片 ${assetId.slice(0, 6)}` : '图片');

  const updateQuestionDraft = (change: Partial<QuestionDraft>) => {
    if (!pending) return;
    setQuestionDrafts((current) => ({
      ...current,
      [pending.id]: {
        ...(current[pending.id] ?? emptyDraft(pending.text)), ...change,
      },
    }));
  };
  const goalsMatchBrief = latestBrief && JSON.stringify(goalsDraft.split('\n')
    .map((line) => line.trim()).filter(Boolean)) === JSON.stringify(latestBrief.payload.goals);
  const canApprove = !goalsDirty.current && Boolean(goalsMatchBrief) && !projectState.briefStale;

  const openBrief = () => {
    if (!latestBrief || !onOpenBrief) return;
    if (!confirmBriefLeave()) return;
    onOpenBrief(latestBrief.version);
  };

  const handleWriteError = async (error: unknown) => {
    if (error instanceof ApiError && error.status === 409) {
      setNotice('输入已保留。项目状态已被另一方更新，请检查后重新提交。');
      await load();
      return;
    }
    setNotice(error instanceof ApiError ? error.message : '提交失败，请重试。');
  };

  const submitQuestionData = async (data: Record<string, unknown>) => {
    if (!pending) return;
    const questionId = pending.id;
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/questions/${questionId}/answer`,
          'POST',
          project.stateVersion,
          data,
        ),
      );
      setQuestionDrafts((current) => {
        if (current[questionId] !== currentDraft) return current;
        const next = { ...current };
        delete next[questionId];
        return next;
      });
      setNotice('回答已提交。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const submitAnswer = async () => {
    if (!pending) return;
    const note = answerDraft.trim();
    if (questionKind === 'broad_parts') {
      const parts = pending.options
        .filter(
          (option) =>
            option.assetId &&
            option.targetElement &&
            partKeys.includes(`${option.assetId}::${option.targetElement}`),
        )
        .map((option) => ({ assetId: option.assetId, targetElement: option.targetElement }));
      if (!parts.length && !note) {
        setNotice('请选择喜欢的部位，或点击跳过。');
        return;
      }
      await submitQuestionData({ parts, ...(note ? { answer: note } : {}) });
      return;
    }
    const selection = pending.options
      .filter((option) => option.attributeId && decisions[option.attributeId])
      .map((option) => ({
        attributeId: option.attributeId,
        assetId: option.assetId,
        targetElement: option.targetElement,
        dimension: option.dimension,
        decision: decisions[option.attributeId as string],
        value: customs[option.attributeId as string] || option.value,
      }));
    if (!selection.length && !note) {
      setNotice('请选择取值或“不在意”，或点击跳过。');
      return;
    }
    await submitQuestionData({ selection, ...(note ? { answer: note } : {}) });
  };

  const skipQuestion = async () => {
    await submitQuestionData({ skipped: true });
  };

  const savePreference = async () => {
    if (!value.trim()) {
      setNotice('请填写偏好内容。');
      return;
    }
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/attributes/manual-${dimension}`,
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

  const uploadAsset = async (file: File) => {
    try {
      await client.upload(`/v1/projects/${projectId}/assets`, file, {
        expectedStateVersion: String(project.stateVersion),
        idempotencyKey: newIdempotencyKey(),
      });
      setNotice('图片已上传。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const deleteAsset = async (asset: Asset) => {
    if (!window.confirm(`确认删除 ${asset.originalFilename}？`)) return;
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/assets/${asset.id}`,
          'DELETE',
          project.stateVersion,
          {},
        ),
      );
      setNotice('图片已删除，相关观察仍会保留并标注来源已删除。');
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

  const setAttributeStatus = async (attribute: Attribute, status: 'confirmed' | 'rejected') => {
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/attributes/${attribute.id}`,
          'PATCH',
          project.stateVersion,
          { status, value: attribute.value },
        ),
      );
      setNotice(status === 'confirmed' ? '已确认该偏好。' : '已拒绝该偏好。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const resolveConflict = async (conflict: Conflict) => {
    if (!conflictResolution.trim()) {
      setNotice('请填写冲突解决说明。');
      return;
    }
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/conflicts/${conflict.id}/resolve`,
          'POST',
          project.stateVersion,
          { status: 'resolved', resolution: conflictResolution },
        ),
      );
      setConflictResolution('');
      setNotice('冲突决定已提交。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const createConstraint = async () => {
    if (!constraintStatement.trim()) {
      setNotice('请填写约束内容。');
      return;
    }
    const incompatibleWith = constraintIncompatible
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    try {
      const path = editingConstraintId
        ? `/v1/projects/${projectId}/constraints/${editingConstraintId}`
        : `/v1/projects/${projectId}/constraints`;
      await client.execute(
        prepareWrite(path, editingConstraintId ? 'PATCH' : 'POST', project.stateVersion, {
          category: constraintCategory,
          statement: constraintStatement,
          rationale: constraintRationale,
          severity: constraintSeverity,
          appliesTo: constraintAppliesTo,
          attributeId: constraintAttributeId || null,
          incompatibleWith,
        }),
      );
      const wasEditing = Boolean(editingConstraintId);
      setEditingConstraintId(null);
      setConstraintStatement('');
      setConstraintRationale('');
      setConstraintIncompatible('');
      setNotice(
        wasEditing ? '约束已更新，过时审批已失效。' : '约束已录入，冲突与方案审批已重新计算。',
      );
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const editConstraint = (constraint: Constraint) => {
    setEditingConstraintId(constraint.id);
    setConstraintCategory(constraint.category);
    setConstraintStatement(constraint.statement);
    setConstraintRationale(constraint.rationale ?? '');
    setConstraintSeverity(constraint.severity);
    setConstraintAppliesTo(constraint.appliesTo ?? '');
    setConstraintAttributeId(constraint.attributeId ?? '');
    setConstraintIncompatible((constraint.incompatibleWith ?? []).join(', '));
  };

  const updateAttribute = async () => {
    const target = projectState.attributes.find((item) => item.id === editAttributeId);
    if (!target || !editAttributeValue.trim()) {
      setNotice('请选择要修改的偏好并填写新内容。');
      return;
    }
    const editable = ['confirmed', 'rejected', 'unresolved', 'not_applicable'];
    const status = editable.includes(target.status) ? target.status : 'confirmed';
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/attributes/${target.id}`,
          'PATCH',
          project.stateVersion,
          { status, value: editAttributeValue },
        ),
      );
      setEditAttributeValue('');
      setNotice('偏好已修改，关联冲突与方案已重新检查。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const withdrawConstraint = async (constraint: Constraint) => {
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/constraints/${constraint.id}/withdraw`,
          'POST',
          project.stateVersion,
          {},
        ),
      );
      setNotice('约束已撤销。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const submitDesignerReview = async () => {
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/designer-reviews`,
          'POST',
          project.stateVersion,
          { note: reviewNote },
        ),
      );
      setReviewNote('');
      setNotice('设计师反馈已提交。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const approveBrief = async (version: number, contentHash: string) => {
    if (!canApprove) return;
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/briefs/${version}/approvals`,
          'POST',
          project.stateVersion,
          { contentHash },
        ),
      );
      setNotice('已批准当前版本。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const realignBrief = async () => {
    try {
      await client.execute(
        prepareWrite(`/v1/projects/${projectId}/realign`, 'POST', project.stateVersion, {}),
      );
      setNotice('已根据当前约束重新生成方案。');
      await load();
    } catch (error) {
      await handleWriteError(error);
    }
  };

  const saveBriefEdit = async () => {
    if (!latestBrief) return;
    const submittedRevision = goalsRevision.current;
    const goals = goalsDraft
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    try {
      await client.execute(
        prepareWrite(
          `/v1/projects/${projectId}/briefs/${latestBrief.version}`,
          'PATCH',
          project.stateVersion,
          { payload: { ...latestBrief.payload, goals } },
        ),
      );
      if (goalsRevision.current === submittedRevision) goalsDirty.current = false;
      setNotice(goalsDirty.current
        ? '已保存提交时的方案，后续输入仍为未保存草稿。'
        : '已保存方案修改，旧审批已失效。');
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
        <p className="demo-badge">真实图片 · 分析为模拟（第 2 步接入）</p>
      </header>

      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}

      <div className="workspace-body">
        <main className="task">
          <h2>当前任务</h2>

          {Object.entries(questionDrafts).filter(([id, draft]) => id !== pending?.id && draftText(draft))
            .map(([id, draft]) => (
              <section key={id} aria-label="保留的未提交回答">
                <h3>上一问题的未提交回答</h3>
                <p>{draft.text}</p>
                <textarea readOnly aria-label={`未提交的回答：${draft.text}`} value={draftText(draft)} />
                <p className="hint">问题已更新，旧草稿保留在本页，供您复制参考，不会自动提交到新问题。</p>
              </section>
            ))}

          {pending && pending.targetRole !== project.role && (
            <p className="waiting">等待{ROLE_LABEL[pending.targetRole] ?? pending.targetRole}回答</p>
          )}

          {!pending && projectState.waitReason === 'designer' && isHomeowner && (
            <p className="waiting">等待设计师反馈</p>
          )}

          {pending && pending.targetRole === 'homeowner' && isHomeowner && (
            <section aria-label={isBroadQuestion ? '广泛偏好问题' : '当前问题'}>
              <p className="question-text">{pending.text}</p>
              {isBroadQuestion ? (
                <>
                  <p className="question-hint">
                    选择希望保留的部位；部位指参考图片中的元素，不代表整张图片。
                  </p>
                  <fieldset>
                    <legend className="sr-only">喜欢的部位</legend>
                    {pending.options.map((option) => {
                      const key = `${option.assetId}::${option.targetElement}`;
                      return (
                        <label key={key} className="option">
                          <input
                            type="checkbox"
                            checked={partKeys.includes(key)}
                            onChange={(event) =>
                              updateQuestionDraft({
                                parts: event.target.checked
                                  ? [...partKeys, key]
                                  : partKeys.filter((item) => item !== key),
                              })
                            }
                          />
                          {assetName(option.assetId)} · {option.targetElement}
                        </label>
                      );
                    })}
                  </fieldset>
                </>
              ) : (
                <>
                  <p className="question-hint">
                    {pending.targetElement && pending.dimension
                      ? `「${pending.targetElement}」的${pending.dimension}：选择你喜欢的取值，或标记“不在意”。`
                      : '请阅读说明并给出你的决定。'}
                  </p>
                  <fieldset>
                    <legend className="sr-only">部位属性取值</legend>
                    {pending.options.map((option) => {
                      const id = option.attributeId ?? '';
                      return (
                        <div key={id} className="option">
                          <span>
                            {assetName(option.assetId)} · {option.label}
                          </span>
                          <button
                            type="button"
                            aria-pressed={decisions[id] === 'confirmed'}
                            onClick={() =>
                              updateQuestionDraft({
                                decisions: { ...decisions, [id]: 'confirmed' },
                              })
                            }
                          >
                            喜欢
                          </button>
                          <button
                            type="button"
                            aria-pressed={decisions[id] === 'not_applicable'}
                            onClick={() =>
                              updateQuestionDraft({
                                decisions: { ...decisions, [id]: 'not_applicable' },
                              })
                            }
                          >
                            不在意
                          </button>
                          <input
                            aria-label={`自定义取值 ${id}`}
                            placeholder="自定义取值"
                            value={customs[id] ?? ''}
                            onChange={(event) =>
                              updateQuestionDraft({
                                customs: { ...customs, [id]: event.target.value },
                              })
                            }
                          />
                        </div>
                      );
                    })}
                  </fieldset>
                </>
              )}
              <label htmlFor="question-answer">您的回答</label>
              <textarea id="question-answer" value={answerDraft}
                onChange={(event) => updateQuestionDraft({ answer: event.target.value })} />
              <p className="hint">备注仅作为文字保存，系统不会自动理解其含义。</p>
              <div className="actions">
                <button type="button" onClick={() => void submitAnswer()}>
                  提交回答
                </button>
                <button type="button" onClick={() => void skipQuestion()}>
                  跳过
                </button>
              </div>
            </section>
          )}

          {projectState.waitReason === 'designer' && !isHomeowner && (
            <section aria-label="设计师反馈">
              <p className="question-text">请提交当前支持的约束反馈。</p>
              <label htmlFor="designer-review">设计师反馈</label>
              <textarea
                id="designer-review"
                value={reviewNote}
                onChange={(event) => setReviewNote(event.target.value)}
              />
              <button type="button" onClick={() => void submitDesignerReview()}>
                提交设计师反馈
              </button>
            </section>
          )}

          <PreferenceBoard
            client={client}
            projectId={projectId}
            role={project.role}
            assets={project.assets}
            stateVersion={project.stateVersion}
          />

          <SpaceBoard
            client={client}
            projectId={projectId}
            role={project.role}
            stateVersion={project.stateVersion}
          />

          <section aria-label="参考图片">
            <h3>参考图片</h3>
            {isHomeowner && <>
              <label htmlFor="asset-upload">上传参考图片</label>
              <input
                id="asset-upload"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = '';
                  if (file) void uploadAsset(file);
                }}
              />
              <p className="question-hint">
                支持 JPEG / PNG / WebP，单张不超过 10MB，最多 10 张。
              </p>
            </>}
            <ul className="assets">
              {project.assets.map((asset: Asset) => (
                <li key={asset.id}>
                  <AssetThumb client={client} projectId={projectId} asset={asset} />
                  <span>
                    {asset.originalFilename}（{asset.mediaType}）
                  </span>
                  {isHomeowner && !asset.deleted && (
                    <button
                      type="button"
                      aria-label={`删除 ${asset.originalFilename}`}
                      onClick={() => void deleteAsset(asset)}
                    >
                      删除
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {isHomeowner && <button type="button" onClick={() => void startAnalysis()}>
              启动分析
            </button>}
          </section>

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

          {isHomeowner && projectState.attributes.length > 0 && (
            <section aria-label="修改已有偏好">
              <h3>修改已有偏好</h3>
              <label htmlFor="edit-attribute">选择偏好</label>
              <select
                id="edit-attribute"
                value={editAttributeId}
                onChange={(event) => setEditAttributeId(event.target.value)}
              >
                <option value="">（请选择）</option>
                {projectState.attributes.map((attribute) => (
                  <option key={attribute.id} value={attribute.id}>
                    {attribute.dimension}：{attribute.value}（{attribute.status}）
                  </option>
                ))}
              </select>
              <label htmlFor="edit-attribute-value">新的取值</label>
              <input
                id="edit-attribute-value"
                value={editAttributeValue}
                onChange={(event) => setEditAttributeValue(event.target.value)}
              />
              <button type="button" onClick={() => void updateAttribute()}>
                保存偏好修改
              </button>
            </section>
          )}

          {latestBrief && (
            <section aria-label="设计方案">
              <h3>设计方案</h3>
              {onOpenBrief && <button type="button" onClick={openBrief}>查看设计说明书</button>}
              <p>
                方案版本 v{latestBrief.version} · 完整度{' '}
                {Math.round(latestBrief.completeness * 100)}%
              </p>
              <p className="hash">内容哈希 {latestBrief.contentHash.slice(0, 12)}…</p>
              <label htmlFor="brief-goals">方案目标</label>
              <textarea
                id="brief-goals"
                value={goalsDraft}
                onChange={(event) => {
                  goalsDirty.current = true;
                  goalsRevision.current += 1;
                  setGoalsDraft(event.target.value);
                }}
              />
              <div className="actions">
                <button type="button" onClick={() => void saveBriefEdit()}>
                  保存方案修改
                </button>
                {projectState.briefStale ? (
                  <button type="button" onClick={() => void realignBrief()}>
                    重新生成方案
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={!canApprove}
                    onClick={() => void approveBrief(latestBrief.version, latestBrief.contentHash)}
                  >
                    批准此版本
                  </button>
                )}
              </div>
              {projectState.briefStale ? (
                <p role="status" className="notice">
                  方案已过时，请重新生成后再审批。
                </p>
              ) : (
                goalsDirty.current && <p className="hint">方案目标有未保存的修改，请先保存再审批。</p>
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
                  <span>
                    {assetName(attribute.evidence.find((item) => item.sourceType === 'image')?.sourceId)} ·{' '}
                    {attribute.targetElement} · {attribute.dimension}：{attribute.value}（{attribute.status}）
                  </span>
                  {attribute.evidence.some(
                    (evidence) =>
                      evidence.sourceType === 'image' && deletedAssetIds.has(evidence.sourceId),
                  ) && <span className="asset-missing">来源图片已删除</span>}
                  {isHomeowner && attribute.status === 'proposed' && (
                    <span className="actions">
                      <button
                        type="button"
                        aria-label={`确认 ${attribute.value}`}
                        onClick={() => void setAttributeStatus(attribute, 'confirmed')}
                      >
                        确认
                      </button>
                      <button
                        type="button"
                        aria-label={`拒绝 ${attribute.value}`}
                        onClick={() => void setAttributeStatus(attribute, 'rejected')}
                      >
                        拒绝
                      </button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3>约束</h3>
            <ul>
              {projectState.constraints.map((constraint: Constraint) => (
                <li key={constraint.id}>
                  <strong>{constraint.statement}</strong>
                  {constraint.withdrawn && <span className="asset-missing">已撤销</span>}
                  <div className="hint">
                    {constraint.category} · {constraint.severity}
                    {constraint.appliesTo ? ` · 作用对象：${constraint.appliesTo}` : ''}
                    {constraint.attributeId ? ` · 关联偏好：${constraint.attributeId}` : ''}
                  </div>
                  {constraint.rationale && <div className="hint">理由：{constraint.rationale}</div>}
                  {isDesigner && !constraint.withdrawn && (
                    <span className="actions">
                      <button
                        type="button"
                        aria-label={`编辑 ${constraint.statement}`}
                        onClick={() => editConstraint(constraint)}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        aria-label={`撤销 ${constraint.statement}`}
                        onClick={() => void withdrawConstraint(constraint)}
                      >
                        撤销
                      </button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
            {isDesigner && (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void createConstraint();
                }}
              >
                <h4>{editingConstraintId ? '编辑约束' : '新增约束'}</h4>
                <label htmlFor="constraint-category">约束类别</label>
                <select
                  id="constraint-category"
                  value={constraintCategory}
                  onChange={(event) => setConstraintCategory(event.target.value)}
                >
                  {CONSTRAINT_CATEGORIES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <label htmlFor="constraint-severity">限制性质</label>
                <select
                  id="constraint-severity"
                  value={constraintSeverity}
                  onChange={(event) => setConstraintSeverity(event.target.value)}
                >
                  <option value="advisory">提示</option>
                  <option value="important">重要</option>
                  <option value="critical">关键</option>
                </select>
                <label htmlFor="constraint-applies-to">作用对象</label>
                <input
                  id="constraint-applies-to"
                  value={constraintAppliesTo}
                  onChange={(event) => setConstraintAppliesTo(event.target.value)}
                />
                <label htmlFor="constraint-attribute">关联偏好</label>
                <select
                  id="constraint-attribute"
                  value={constraintAttributeId}
                  onChange={(event) => setConstraintAttributeId(event.target.value)}
                >
                  <option value="">（不关联）</option>
                  {projectState.attributes
                    .filter((attribute) => attribute.status === 'confirmed')
                    .map((attribute) => (
                      <option key={attribute.id} value={attribute.id}>
                        {attribute.dimension}：{attribute.value}
                      </option>
                    ))}
                </select>
                <label htmlFor="constraint-statement">约束内容</label>
                <textarea
                  id="constraint-statement"
                  value={constraintStatement}
                  onChange={(event) => setConstraintStatement(event.target.value)}
                />
                <label htmlFor="constraint-rationale">约束理由</label>
                <textarea
                  id="constraint-rationale"
                  value={constraintRationale}
                  onChange={(event) => setConstraintRationale(event.target.value)}
                />
                <label htmlFor="constraint-incompatible">不兼容取值（逗号分隔）</label>
                <input
                  id="constraint-incompatible"
                  value={constraintIncompatible}
                  onChange={(event) => setConstraintIncompatible(event.target.value)}
                />
                <div className="actions">
                  <button type="submit">
                    {editingConstraintId ? '更新约束' : '保存约束'}
                  </button>
                  {editingConstraintId && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditingConstraintId(null);
                        setConstraintStatement('');
                        setConstraintRationale('');
                        setConstraintIncompatible('');
                      }}
                    >
                      取消编辑
                    </button>
                  )}
                </div>
              </form>
            )}
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
            {openConflict && pending?.id === `question-conflict-${openConflict.id}` && (
              <p className="hint">请由屋主回答当前冲突问题，提交后继续对齐流程。</p>
            )}
            {openConflict && pending?.id !== `question-conflict-${openConflict.id}` && (
              <div className="resolve">
                <label htmlFor="conflict-resolution">冲突解决说明</label>
                <textarea
                  id="conflict-resolution"
                  value={conflictResolution}
                  onChange={(event) => setConflictResolution(event.target.value)}
                />
                <button type="button" onClick={() => void resolveConflict(openConflict)}>
                  提交冲突决定
                </button>
              </div>
            )}
          </section>
          <section>
            <h3>审批</h3>
            <ul>
              {projectState.approvals.map((approval) => (
                <li key={`${approval.role}-${approval.briefVersion}`}>
                  {ROLE_LABEL[approval.role] ?? approval.role}已批准 v{approval.briefVersion}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </div>
  );
}
