import { useCallback, useEffect, useState } from 'react';

import { ApiError, prepareWrite, type ApiClient } from '../api';
import type { SpaceApprovalView } from '../types';

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return '操作失败，请重试。';
}

type Props = {
  client: ApiClient;
  projectId: string;
  stateVersion: number;
  onChanged?: () => void;
};

/**
 * Joint brief + space approval. The backend validates both the brief and the
 * space version/hash, so this component only submits the pair it was shown.
 * Extracted so the space and approval pages share one implementation.
 */
export function JointApproval({ client, projectId, stateVersion, onChanged }: Props) {
  const [approvals, setApprovals] = useState<SpaceApprovalView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setApprovals(await client.get<SpaceApprovalView>(`/v1/projects/${projectId}/space/approvals`));
      setError(null);
    } catch (caught) {
      setError(messageOf(caught));
    }
  }, [client, projectId]);

  useEffect(() => {
    void load();
  }, [load, stateVersion]);

  const expectedVersion = Math.max(approvals?.stateVersion ?? 0, stateVersion);

  const jointApprove = async () => {
    if (!approvals?.briefVersion || !approvals.spaceVersion) return;
    setBusy(true);
    setError(null);
    try {
      await client.execute(
        prepareWrite(`/v1/projects/${projectId}/space/approvals`, 'POST', expectedVersion, {
          briefVersion: approvals.briefVersion,
          briefHash: approvals.briefHash,
          spaceVersion: approvals.spaceVersion,
          spaceHash: approvals.spaceHash,
        }),
      );
      await load();
      onChanged?.();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  };

  const records = Array.isArray(approvals?.approvals) ? approvals.approvals : [];

  return (
    <section aria-label="联合审批">
      <h4>联合审批（说明书 + 空间）</h4>
      {error && <p role="alert">{error}</p>}
      {approvals ? (
        <div>
          <p className="question-hint">
            说明书 v{approvals.briefVersion ?? '—'} · 空间 v{approvals.spaceVersion ?? '—'} ·{' '}
            {approvals.approved ? '双方已批准' : '尚未双方批准'}
          </p>
          <p className="question-hint">
            已记录批准：
            {records.length === 0
              ? '（无）'
              : records.map((item) => (item.role === 'homeowner' ? '屋主' : '设计师')).join('、')}
          </p>
          <button
            type="button"
            disabled={busy || !approvals.briefVersion || !approvals.spaceVersion}
            onClick={() => void jointApprove()}
          >
            联合批准当前方案
          </button>
          <p className="question-hint">
            仅当说明书与空间版本和哈希都匹配当前值时才计入；旧审批不会自动适用于新版本。
          </p>
        </div>
      ) : (
        <p className="question-hint">尚无审批信息。</p>
      )}
    </section>
  );
}
