import { useCallback, useEffect, useState } from 'react';

import { ApiError, prepareWrite, type ApiClient } from '../api';
import type {
  MaterialCatalogue,
  SpaceApprovalView,
  SpaceBinding,
  SpaceBindingList,
  SpacePlan,
  SpaceSnapshot,
} from '../types';

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return '操作失败，请重试。';
}

type Props = {
  client: ApiClient;
  projectId: string;
  role: 'homeowner' | 'designer';
  stateVersion: number;
  plan: SpacePlan | null;
  materials: MaterialCatalogue | null;
  onApplied: (snapshot: SpaceSnapshot) => void;
  onChanged?: () => void;
};

const STATUS_LABELS: Record<string, string> = {
  active: '已绑定',
  needs_review: '需要复核',
  invalidated: '已作废',
};

const APPROXIMATION_LABELS: Record<string, string> = {
  exact: '完全匹配',
  approximate: '近似替代（需确认）',
};

/**
 * Confirmed floor preference -> room -> supported material. Applying a binding
 * creates a new space version; an approximation must be explicitly
 * acknowledged. Joint approval requires both the brief and space hashes.
 */
export function BindingPanel({ client, projectId, role, stateVersion, plan, materials, onApplied, onChanged }: Props) {
  const [bindingList, setBindingList] = useState<SpaceBindingList | null>(null);
  const [approvals, setApprovals] = useState<SpaceApprovalView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [attributeId, setAttributeId] = useState('');
  const [roomId, setRoomId] = useState('');
  const [materialOptionId, setMaterialOptionId] = useState('');
  const [confirmApproximation, setConfirmApproximation] = useState(false);

  const isHomeowner = role === 'homeowner';
  const rooms = plan?.rooms ?? [];
  const floorMaterials = (materials?.options ?? []).filter((option) => option.targets.includes('floor'));

  const load = useCallback(async () => {
    try {
      const [nextBindings, nextApprovals] = await Promise.all([
        client.get<SpaceBindingList>(`/v1/projects/${projectId}/space/bindings`),
        client.get<SpaceApprovalView>(`/v1/projects/${projectId}/space/approvals`),
      ]);
      setBindingList(nextBindings);
      setApprovals(nextApprovals);
      setError(null);
    } catch (caught) {
      setError(messageOf(caught));
    }
  }, [client, projectId]);

  useEffect(() => {
    void load();
  }, [load, stateVersion]);

  const expectedVersion = Math.max(
    bindingList?.stateVersion ?? 0,
    approvals?.stateVersion ?? 0,
    stateVersion,
  );

  const run = async (write: ReturnType<typeof prepareWrite>, applied: boolean) => {
    setBusy(true);
    setError(null);
    try {
      if (applied) {
        onApplied(await client.execute<SpaceSnapshot>(write));
      } else {
        await client.execute(write);
      }
      await load();
      onChanged?.();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  };

  const createBinding = () => {
    const data: Record<string, unknown> = { attributeId, roomId };
    if (materialOptionId) data.materialOptionId = materialOptionId;
    if (confirmApproximation) data.confirmApproximation = true;
    void run(
      prepareWrite(`/v1/projects/${projectId}/space/bindings`, 'POST', expectedVersion, data),
      false,
    );
  };

  const applyBinding = (binding: SpaceBinding) => {
    void run(
      prepareWrite(
        `/v1/projects/${projectId}/space/bindings/${binding.id}/apply`,
        'POST',
        expectedVersion,
        {},
      ),
      true,
    );
  };

  const reviewBinding = (binding: SpaceBinding, status: 'active' | 'invalidated', room?: string) => {
    const data: Record<string, unknown> = { status };
    if (room) data.roomId = room;
    void run(
      prepareWrite(
        `/v1/projects/${projectId}/space/bindings/${binding.id}/review`,
        'POST',
        expectedVersion,
        data,
      ),
      false,
    );
  };

  const jointApprove = () => {
    if (!approvals?.briefVersion || !approvals.spaceVersion) return;
    void run(
      prepareWrite(`/v1/projects/${projectId}/space/approvals`, 'POST', expectedVersion, {
        briefVersion: approvals.briefVersion,
        briefHash: approvals.briefHash,
        spaceVersion: approvals.spaceVersion,
        spaceHash: approvals.spaceHash,
      }),
      false,
    );
  };

  const floorPreferences = bindingList?.floorPreferences ?? [];
  const bindings = bindingList?.bindings ?? [];
  const approvalRecords = Array.isArray(approvals?.approvals) ? approvals.approvals : [];

  return (
    <div className="binding-panel">
      <h4>地板偏好 → 空间材质</h4>
      <p className="question-hint">
        只有屋主确认过的地板偏好可以绑定；近似替代必须明确确认；应用材质会生成新的空间版本。
      </p>
      {error && <p role="alert">{error}</p>}

      {isHomeowner && floorPreferences.length > 0 && rooms.length > 0 && (
        <fieldset>
          <legend>新建绑定</legend>
          <label htmlFor="binding-attribute">已确认地板偏好</label>
          <select
            id="binding-attribute"
            value={attributeId}
            onChange={(event) => setAttributeId(event.target.value)}
          >
            <option value="">请选择</option>
            {floorPreferences.map((item) => (
              <option key={item.attributeId} value={item.attributeId}>
                {item.value}（{item.dimension}）
              </option>
            ))}
          </select>
          <label htmlFor="binding-room">房间</label>
          <select id="binding-room" value={roomId} onChange={(event) => setRoomId(event.target.value)}>
            <option value="">请选择</option>
            {rooms.map((room) => (
              <option key={room.id} value={room.id}>
                {room.name}
              </option>
            ))}
          </select>
          <label htmlFor="binding-material">受支持材质</label>
          <select
            id="binding-material"
            value={materialOptionId}
            onChange={(event) => setMaterialOptionId(event.target.value)}
          >
            <option value="">按偏好值自动匹配</option>
            {floorMaterials.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
          <label className="option">
            <input
              type="checkbox"
              checked={confirmApproximation}
              onChange={(event) => setConfirmApproximation(event.target.checked)}
            />
            我理解近似替代（如以瓷砖近似天然石材），并确认继续
          </label>
          <button
            type="button"
            disabled={busy || !attributeId || !roomId}
            onClick={createBinding}
          >
            绑定到房间
          </button>
        </fieldset>
      )}

      {bindings.length === 0 && <p className="question-hint">还没有绑定。</p>}
      <ul className="bindings">
        {bindings.map((binding) => {
          const room = rooms.find((item) => item.id === binding.roomId);
          const material = (materials?.options ?? []).find((item) => item.id === binding.materialOptionId);
          return (
            <li key={binding.id}>
              <span>
                {room?.name ?? binding.roomId} · {material?.label ?? binding.materialOptionId} ·{' '}
                {STATUS_LABELS[binding.status] ?? binding.status} ·{' '}
                {APPROXIMATION_LABELS[binding.approximation] ?? binding.approximation}
                {binding.appliedSpaceVersion ? ` · 已应用到 v${binding.appliedSpaceVersion}` : ''}
              </span>
              {binding.note && <em className="question-hint"> {binding.note}</em>}
              {binding.status === 'active' && (
                <button type="button" disabled={busy} onClick={() => applyBinding(binding)}>
                  应用材质到空间
                </button>
              )}
              {binding.status === 'needs_review' && (
                <>
                  <button
                    type="button"
                    disabled={busy || rooms.length === 0}
                    onClick={() => reviewBinding(binding, 'active', rooms[0]?.id)}
                  >
                    重新绑定
                  </button>
                  <button type="button" disabled={busy} onClick={() => reviewBinding(binding, 'invalidated')}>
                    作废绑定
                  </button>
                </>
              )}
            </li>
          );
        })}
      </ul>

      <h4>联合审批（说明书 + 空间）</h4>
      {approvals ? (
        <div aria-label="联合审批">
          <p className="question-hint">
            说明书 v{approvals.briefVersion ?? '—'} · 空间 v{approvals.spaceVersion ?? '—'} ·{' '}
            {approvals.approved ? '双方已批准' : '尚未双方批准'}
          </p>
          <p className="question-hint">
            已记录批准：
            {approvalRecords.length === 0
              ? '（无）'
              : approvalRecords.map((item) => (item.role === 'homeowner' ? '屋主' : '设计师')).join('、')}
          </p>
          <button
            type="button"
            disabled={busy || !approvals.briefVersion || !approvals.spaceVersion}
            onClick={jointApprove}
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
    </div>
  );
}
