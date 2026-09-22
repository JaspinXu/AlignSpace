import { useCallback, useEffect, useState } from 'react';

import { ApiError, prepareWrite, type ApiClient } from '../api';
import { AssetImage } from '../assets/AssetImage';
import type {
  Asset,
  Candidate,
  CandidateBoard,
  CandidateDimension,
  DesignEntry,
} from '../types';

const DIMENSION_LABELS: Record<CandidateDimension, string> = {
  colour: '颜色',
  material: '材质',
  style: '样式',
  laying: '铺设方式',
  lighting: '灯光',
  other: '其他',
};

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return '操作失败，请重试。';
}

type Props = {
  client: ApiClient;
  projectId: string;
  role: 'homeowner' | 'designer';
  assets: Asset[];
  /** Latest project state version, so a write is never sent against a stale one. */
  stateVersion: number;
};

/**
 * Candidate preferences are proposals. The board keeps three facts apart:
 * the dimensions the homeowner mentioned, what the model inferred (including
 * explicitly uncertain values), and the preference the homeowner confirmed.
 */
export function PreferenceBoard({ client, projectId, role, assets, stateVersion }: Props) {
  const [board, setBoard] = useState<CandidateBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [description, setDescription] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [edits, setEdits] = useState<Record<string, string>>({});

  const isHomeowner = role === 'homeowner';
  const activeAssets = assets.filter((asset) => !asset.deleted);

  const load = useCallback(async () => {
    try {
      setBoard(
        await client.get<CandidateBoard>(
          `/v1/projects/${projectId}/preference-analyses`,
        ),
      );
      setError(null);
    } catch (caught) {
      setError(messageOf(caught));
    }
  }, [client, projectId]);

  useEffect(() => {
    void load();
  }, [load, stateVersion]);

  // The board and the project can each advance the version; the newest observed
  // one is what a write must be based on.
  const expectedVersion = board ? Math.max(board.stateVersion, stateVersion) : stateVersion;

  const runAnalysis = async () => {
    if (!board) return;
    setBusy(true);
    setError(null);
    try {
      const write = prepareWrite(
        `/v1/projects/${projectId}/preference-analyses`,
        'POST',
        expectedVersion,
        { assetIds: selected, description, thirdPartyConsent: consent },
      );
      setBoard(await client.execute<CandidateBoard>(write));
      setDescription('');
      setSelected([]);
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  };

  const decide = async (candidate: Candidate, action: 'confirm' | 'reject') => {
    if (!board) return;
    setBusy(true);
    setError(null);
    try {
      const write = prepareWrite(
        `/v1/projects/${projectId}/candidates/${candidate.id}/${action}`,
        'POST',
        expectedVersion,
        action === 'confirm' && edits[candidate.id]
          ? { value: edits[candidate.id] }
          : {},
      );
      setBoard(await client.execute<CandidateBoard>(write));
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  };

  const editEntry = async (entry: DesignEntry, dismissed: boolean) => {
    if (!board) return;
    setBusy(true);
    setError(null);
    try {
      const write = prepareWrite(
        `/v1/projects/${projectId}/design-entries/${entry.id}`,
        'PATCH',
        expectedVersion,
        { dismissed },
      );
      setBoard(await client.execute<CandidateBoard>(write));
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  };

  const runs = board?.runs ?? [];

  return (
    <section aria-label="图片偏好候选">
      <h3>图片偏好候选</h3>
      <p className="question-hint">
        {isHomeowner
          ? '选择参考图片并描述你喜欢的部分。系统只提出候选，确认后才写入正式偏好。'
          : '候选由屋主确认后才会成为正式偏好；这里仅供查看。'}
      </p>
      {error && <p role="alert">{error}</p>}

      {isHomeowner && (
        <div>
          <fieldset>
            <legend>选择图片</legend>
            <div className="image-picker">
              {activeAssets.map((asset) => {
                const checked = selected.includes(asset.id);
                return (
                  <label key={asset.id} className={checked ? 'image-pick is-selected' : 'image-pick'}>
                    <input
                      type="checkbox"
                      checked={checked}
                      aria-label={`选择图片 ${asset.originalFilename}`}
                      onChange={(event) =>
                        setSelected((current) =>
                          event.target.checked
                            ? [...current, asset.id]
                            : current.filter((item) => item !== asset.id),
                        )
                      }
                    />
                    <AssetImage client={client} projectId={projectId} asset={asset} decorative />
                    <span className="image-pick__name">{asset.originalFilename}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
          <label htmlFor="preference-description">喜欢这张图的哪些部分</label>
          <textarea
            id="preference-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="例如：喜欢床的颜色和样式、墙壁的颜色和材质、地板的铺设方式"
          />
          <label className="option">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
            />
            同意将参考图片和描述发送至第三方模型服务（真实模式需要）
          </label>
          <button type="button" disabled={busy} onClick={() => void runAnalysis()}>
            生成候选偏好
          </button>
        </div>
      )}

      {runs.length === 0 && <p className="question-hint">还没有候选偏好。</p>}

      {runs.map((run) => (
        <div key={run.id} aria-label={`分析任务 ${run.id}`}>
          <p className="question-hint">
            模型模式：{run.providerMode} · 模型：{run.model}
            {run.stale ? ' · 来源图片已被删除，结果已过时' : ''}
          </p>
          {run.entries.map((entry) => (
            <div key={entry.id} className="option">
              <p>
                <strong>部位：</strong>
                {entry.targetElement}
                {entry.sourceAvailable ? '' : '（来源图片已删除）'}
              </p>
              <p>
                <strong>我提到的关注维度：</strong>
                {entry.attentionDimensions.map((item) => DIMENSION_LABELS[item]).join('、') || '（无）'}
              </p>
              <p>
                <strong>模型观察/推断：</strong>
                {entry.candidates
                  .map((candidate) =>
                    candidate.certainty === 'uncertain'
                      ? `${DIMENSION_LABELS[candidate.dimension]}：不确定`
                      : `${DIMENSION_LABELS[candidate.dimension]}：${candidate.proposedValue ?? '不确定'}`,
                  )
                  .join('；') || '（无）'}
              </p>
              <ul>
                {entry.candidates.map((candidate) => (
                  <li key={candidate.id}>
                    <span>
                      {DIMENSION_LABELS[candidate.dimension]} ·{' '}
                      {candidate.certainty === 'uncertain' ? (
                        <em>不确定</em>
                      ) : (
                        candidate.proposedValue
                      )}
                      {candidate.status === 'confirmed' && candidate.confirmedValue
                        ? ` → 已确认：${candidate.confirmedValue}`
                        : ''}
                      {candidate.status === 'rejected' ? ' · 已不采用' : ''}
                    </span>
                    {isHomeowner && candidate.status === 'proposed' && (
                      <>
                        <label htmlFor={`candidate-value-${candidate.id}`}>
                          自定义取值 {DIMENSION_LABELS[candidate.dimension]}
                        </label>
                        <input
                          id={`candidate-value-${candidate.id}`}
                          value={edits[candidate.id] ?? ''}
                          placeholder={candidate.proposedValue ?? '不确定，可自行填写'}
                          onChange={(event) =>
                            setEdits((current) => ({
                              ...current,
                              [candidate.id]: event.target.value,
                            }))
                          }
                        />
                        <button
                          type="button"
                          disabled={busy || !entry.sourceAvailable}
                          onClick={() => void decide(candidate, 'confirm')}
                        >
                          确认{DIMENSION_LABELS[candidate.dimension]}候选
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void decide(candidate, 'reject')}
                        >
                          不采用{DIMENSION_LABELS[candidate.dimension]}候选
                        </button>
                      </>
                    )}
                  </li>
                ))}
              </ul>
              {!entry.sourceAvailable && (
                <p role="note">来源图片已删除，未确认的候选不能再确认。</p>
              )}
              {isHomeowner && (
                <button type="button" disabled={busy} onClick={() => void editEntry(entry, true)}>
                  忽略该条目
                </button>
              )}
            </div>
          ))}
        </div>
      ))}
    </section>
  );
}
