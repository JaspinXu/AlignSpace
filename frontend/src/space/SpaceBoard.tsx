import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, prepareWrite, type ApiClient } from '../api';
import type {
  MaterialCatalogue,
  SpaceObject,
  SpaceRoom,
  SpaceSnapshot,
} from '../types';
import { BindingPanel } from './BindingPanel';
import {
  buildPreviewMessage,
  isAllowedPreviewOrigin,
  parseEditorMessage,
  roomCorners,
  spaceExtent,
  previewPatternNote,
  upstreamDiff,
  type SpaceSyncOp,
} from './spaceAdapter';

const PREVIEW_URL =
  (import.meta.env.VITE_OPENPLAN3D_URL as string | undefined) ?? 'http://127.0.0.1:4173';
const ROOM_TYPES = [
  { value: 'living_room', label: '客厅' },
  { value: 'bedroom', label: '卧室' },
  { value: 'kitchen', label: '厨房' },
  { value: 'bathroom', label: '卫生间' },
  { value: 'study', label: '书房' },
  { value: 'other', label: '其他' },
];

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return '操作失败，请重试。';
}

type Props = {
  client: ApiClient;
  projectId: string;
  role: 'homeowner' | 'designer';
  stateVersion: number;
  onChanged?: () => void;
};

export function SpaceBoard({ client, projectId, role, stateVersion, onChanged }: Props) {
  const [snapshot, setSnapshot] = useState<SpaceSnapshot | null>(null);
  const [materials, setMaterials] = useState<MaterialCatalogue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newRoomName, setNewRoomName] = useState('客厅');
  const [newRoomType, setNewRoomType] = useState('living_room');
  const [newWidth, setNewWidth] = useState('4000');
  const [newDepth, setNewDepth] = useState('5000');
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null);
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [objectLabel, setObjectLabel] = useState('沙发');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewNote, setPreviewNote] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncNotes, setSyncNotes] = useState<string[]>([]);
  const [syncConflicts, setSyncConflicts] = useState<string[]>([]);
  const [syncConflict, setSyncConflict] = useState(false);
  const frame = useRef<HTMLIFrameElement | null>(null);
  const planRef = useRef<SpaceSnapshot['plan']>(null);
  const readyRef = useRef(false);
  const syncingRef = useRef(false);
  const hasImportedRef = useRef(false);
  const conflictRef = useRef(false);
  // A pending draft is bound to the base it was computed against, so a poll or
  // re-import cannot silently move the deletion/merge baseline.
  const pendingSyncRef = useRef<{ project: unknown; basePlan: SpaceSnapshot['plan'] } | null>(null);
  // The version the editor state was based on, so a concurrent write returns 409
  // instead of being silently overwritten.
  const baseVersionRef = useRef(stateVersion);
  // The plan the editor imported: all merge comparisons use this base.
  const syncBaseRef = useRef<SpaceSnapshot['plan']>(null);
  // Editor temp id -> backend id, learned from create responses.
  const idMapRef = useRef<Map<string, string>>(new Map());
  // Entities created by the editor during this session, captured at creation.
  const createdBaseRef = useRef<NonNullable<SpaceSnapshot['plan']>>({
    schemaVersion: '1.0.0',
    units: 'mm',
    rooms: [],
    objects: [],
  });
  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;

  const isHomeowner = role === 'homeowner';

  const load = useCallback(async () => {
    try {
      const [next, catalogue] = await Promise.all([
        client.get<SpaceSnapshot>(`/v1/projects/${projectId}/space`),
        client.get<MaterialCatalogue>(`/v1/projects/${projectId}/materials`),
      ]);
      setSnapshot(next);
      setMaterials(catalogue);
      setError(null);
    } catch (caught) {
      setError(messageOf(caught));
    }
  }, [client, projectId]);

  useEffect(() => {
    void load();
  }, [load, stateVersion]);

  const expectedVersion = snapshot ? Math.max(snapshot.stateVersion, stateVersion) : stateVersion;
  const plan = snapshot?.plan ?? null;
  planRef.current = plan;
  // Older workspaces and unrelated test doubles may not expose a catalogue yet.
  const materialOptions = Array.isArray(materials?.options) ? materials.options : [];

  const buildWrite = useCallback(
    (op: SpaceSyncOp, version: number) => {
      if (op.op === 'update_room') {
        const data: Record<string, unknown> = {};
        if (op.name !== undefined) data.name = op.name;
        if (op.origin) data.origin = op.origin;
        if (op.size) data.size = op.size;
        if (op.outline) data.outline = op.outline;
        return prepareWrite(`/v1/projects/${projectId}/space/rooms/${op.roomId}`, 'PATCH', version, data);
      }
      if (op.op === 'create_room') {
        const data: Record<string, unknown> = {
          name: op.name,
          width: op.size.width,
          depth: op.size.depth,
          origin: op.origin,
        };
        if (op.outline) data.outline = op.outline;
        return prepareWrite(`/v1/projects/${projectId}/space/rooms`, 'POST', version, data);
      }
      if (op.op === 'delete_room') {
        return prepareWrite(`/v1/projects/${projectId}/space/rooms/${op.roomId}`, 'DELETE', version, {});
      }
      if (op.op === 'update_object') {
        return prepareWrite(
          `/v1/projects/${projectId}/space/objects/${op.objectId}`,
          'PATCH',
          version,
          { geometry: op.geometry },
        );
      }
      if (op.op === 'create_object') {
        return prepareWrite(`/v1/projects/${projectId}/space/objects`, 'POST', version, {
          roomId: op.roomId,
          kind: op.kind,
          label: op.label,
          geometry: op.geometry,
        });
      }
      return prepareWrite(
        `/v1/projects/${projectId}/space/objects/${op.objectId}`,
        'DELETE',
        version,
        {},
      );
    },
    [projectId],
  );

  const applyOps = useCallback(
    async (ops: SpaceSyncOp[]) => {
      // Start from the version the editor state was based on. Each successful
      // write advances to the version our own write produced, so a concurrent
      // write between operations surfaces as a 409 rather than being absorbed.
      let version = baseVersionRef.current;
      let currentPlan = planRef.current;
      for (const op of ops) {
        const beforeRoomIds = new Set((currentPlan?.rooms ?? []).map((room) => room.id));
        const beforeObjectIds = new Set((currentPlan?.objects ?? []).map((item) => item.id));
        const result = await client.execute<SpaceSnapshot>(buildWrite(op, version));
        currentPlan = result.plan;
        // Learn the backend id assigned to an editor-created entity so later
        // snapshots update it instead of creating a duplicate and deleting it.
        if (op.op === 'create_room' && op.upstreamId) {
          const created = result.plan?.rooms.find((room) => !beforeRoomIds.has(room.id));
          if (created) {
            idMapRef.current.set(op.upstreamId, created.id);
            createdBaseRef.current = {
              ...createdBaseRef.current,
              rooms: [...createdBaseRef.current.rooms, created],
            };
          }
        } else if (op.op === 'create_object' && op.upstreamId) {
          const created = result.plan?.objects.find((item) => !beforeObjectIds.has(item.id));
          if (created) {
            idMapRef.current.set(op.upstreamId, created.id);
            createdBaseRef.current = {
              ...createdBaseRef.current,
              objects: [...createdBaseRef.current.objects, created],
            };
          }
        }
        version = result.stateVersion;
        baseVersionRef.current = version;
      }
      const refreshed = await client.get<SpaceSnapshot>(`/v1/projects/${projectId}/space`);
      planRef.current = refreshed.plan;
      syncBaseRef.current = refreshed.plan;
      setSnapshot(refreshed);
      baseVersionRef.current = refreshed.stateVersion;
      onChangedRef.current?.();
    },
    [buildWrite, client, projectId],
  );

  const drain = useCallback(async () => {
    if (syncingRef.current) return;
    const pending = pendingSyncRef.current;
    if (!pending) return;
    pendingSyncRef.current = null;
    const currentPlan = planRef.current;
    if (!currentPlan) return;
    const { ops, unsupported, conflicts } = upstreamDiff(pending.project, currentPlan, role, {
      basePlan: pending.basePlan,
      createdBase: createdBaseRef.current,
      idMap: idMapRef.current,
    });
    setSyncNotes(unsupported);
    setSyncConflicts(conflicts);
    // Deletions are only trusted after a successful import established the base.
    const applicable = hasImportedRef.current
      ? ops
      : ops.filter((op) => op.op !== 'delete_room' && op.op !== 'delete_object');
    if (applicable.length === 0) return;
    syncingRef.current = true;
    setSyncing(true);
    setError(null);
    try {
      await applyOps(applicable);
      conflictRef.current = false;
      setSyncConflict(false);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        // Preserve the draft with its original base; never silently rebase.
        pendingSyncRef.current = pending;
        conflictRef.current = true;
        setSyncConflict(true);
        setError('其他协作者已更新空间，本次 3D 编辑未覆盖新版本。请重试以在当前版本上重新应用。');
      } else {
        setError(messageOf(caught));
      }
    } finally {
      syncingRef.current = false;
      setSyncing(false);
      if (pendingSyncRef.current && !conflictRef.current) void drain();
    }
  }, [applyOps, role]);

  const retrySync = useCallback(async () => {
    const pending = pendingSyncRef.current;
    if (!pending) return;
    conflictRef.current = false;
    setSyncConflict(false);
    // Refresh the server target and version, but keep the draft's original base
    // for the three-way merge so a collaborator's new content is never deleted.
    const current = await client.get<SpaceSnapshot>(`/v1/projects/${projectId}/space`);
    planRef.current = current.plan;
    setSnapshot(current);
    baseVersionRef.current = current.stateVersion;
    pendingSyncRef.current = pending;
    void drain();
  }, [client, projectId, drain]);

  // Preview handshake: only a message from the exact local origin is trusted.
  useEffect(() => {
    if (!previewOpen) return;
    const onMessage = (event: MessageEvent) => {
      const parsed = parseEditorMessage(event, PREVIEW_URL);
      if (!parsed) return;
      if (parsed.kind === 'ready') {
        readyRef.current = true;
        const currentPlan = planRef.current;
        if (!currentPlan) return;
        baseVersionRef.current = Math.max(baseVersionRef.current, stateVersion);
        if (!pendingSyncRef.current) {
          syncBaseRef.current = currentPlan;
          createdBaseRef.current = { schemaVersion: '1.0.0', units: 'mm', rooms: [], objects: [] };
        }
        const target = frame.current?.contentWindow;
        if (!target) return;
        target.postMessage(buildPreviewMessage(currentPlan), PREVIEW_URL);
        setPreviewNote('已将当前空间草稿发送到本地 3D 预览（仅本机，不含令牌）。');
      } else if (parsed.kind === 'applied') {
        hasImportedRef.current = true;
      } else if (parsed.kind === 'project') {
        if (!hasImportedRef.current) return;
        const currentPlan = planRef.current;
        if (!currentPlan) return;
        // Keep the base of an existing draft; only a fresh edit session uses the
        // current base.
        const basePlan = pendingSyncRef.current?.basePlan ?? syncBaseRef.current;
        pendingSyncRef.current = { project: parsed.project, basePlan };
        void drain();
      } else if (parsed.kind === 'error') {
        setError(parsed.message);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [previewOpen, drain, stateVersion]);

  // Keep the 3D editor in sync when the 2D panel changes the plan.
  useEffect(() => {
    if (!previewOpen || !readyRef.current) return;
    const target = frame.current?.contentWindow;
    // Do not re-import over a draft that still needs syncing or conflict review.
    if (target && plan && !pendingSyncRef.current && !conflictRef.current) {
      syncBaseRef.current = plan;
      target.postMessage(buildPreviewMessage(plan), PREVIEW_URL);
    }
  }, [previewOpen, plan]);

  const run = async (write: ReturnType<typeof prepareWrite>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await client.execute<SpaceSnapshot>(write);
      setSnapshot(next);
      onChanged?.();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  };

  const addRoom = () => {
    const width = Number(newWidth);
    const depth = Number(newDepth);
    if (!newRoomName.trim() || !Number.isFinite(width) || !Number.isFinite(depth)) {
      setError('请填写房间名称与有效尺寸。');
      return;
    }
    void run(
      prepareWrite(`/v1/projects/${projectId}/space/rooms`, 'POST', expectedVersion, {
        name: newRoomName.trim(),
        roomType: newRoomType,
        width,
        depth,
      }),
    );
  };

  const renameRoom = (room: SpaceRoom) => {
    const name = window.prompt('房间名称', room.name);
    if (!name || name.trim() === room.name) return;
    void run(
      prepareWrite(`/v1/projects/${projectId}/space/rooms/${room.id}`, 'PATCH', expectedVersion, {
        name: name.trim(),
      }),
    );
  };

  const resizeRoom = (room: SpaceRoom) => {
    const width = window.prompt('房间宽度（mm）', String(room.size.width));
    if (width === null) return;
    const depth = window.prompt('房间进深（mm）', String(room.size.depth));
    if (depth === null) return;
    void run(
      prepareWrite(`/v1/projects/${projectId}/space/rooms/${room.id}`, 'PATCH', expectedVersion, {
        width: Number(width),
        depth: Number(depth),
      }),
    );
  };

  const deleteRoom = (room: SpaceRoom) => {
    if (!window.confirm(`删除房间「${room.name}」？`)) return;
    void run(
      prepareWrite(`/v1/projects/${projectId}/space/rooms/${room.id}`, 'DELETE', expectedVersion, {}),
    );
  };

  const addObject = () => {
    if (!selectedRoomId) {
      setError('请先选择一个房间，再添加家具。');
      return;
    }
    const room = plan?.rooms.find((item) => item.id === selectedRoomId);
    const geometry = room
      ? {
          x: room.origin.x + room.size.width / 2,
          y: room.origin.y + room.size.depth / 2,
          width: 1000,
          depth: 600,
          height: 800,
        }
      : {};
    void run(
      prepareWrite(`/v1/projects/${projectId}/space/objects`, 'POST', expectedVersion, {
        roomId: selectedRoomId,
        kind: 'furniture',
        label: objectLabel.trim() || '家具',
        geometry,
      }),
    );
  };

  const deleteObject = (object: SpaceObject) => {
    void run(
      prepareWrite(
        `/v1/projects/${projectId}/space/objects/${object.id}`,
        'DELETE',
        expectedVersion,
        {},
      ),
    );
  };

  const extent = plan ? spaceExtent(plan) : { minX: 0, minY: 0, width: 4000, height: 5000 };
  const padding = 500;
  const viewBox = `${extent.minX - padding} ${extent.minY - padding} ${extent.width + padding * 2} ${extent.height + padding * 2}`;

  return (
    <section aria-label="空间草稿">
      <div className="section-head">
        <h3>空间草稿（2D / 3D）</h3>
        <span className="question-hint">
          {snapshot?.version ? `空间版本 v${snapshot.version}` : '尚无空间版本'}
          {snapshot?.contentHash ? ` · ${snapshot.contentHash.slice(0, 8)}` : ''}
        </span>
      </div>
      <p className="question-hint">
        屋主与设计师可共同编辑这份草稿；删除房间或家具仅限屋主。本地浏览器只保存临时草稿，权威数据以后端为准。
      </p>
      {error && <p role="alert">{error}</p>}

      <fieldset>
        <legend>添加矩形房间</legend>
        <label htmlFor="space-room-name">房间名称</label>
        <input id="space-room-name" value={newRoomName} onChange={(event) => setNewRoomName(event.target.value)} />
        <label htmlFor="space-room-type">房间类型</label>
        <select id="space-room-type" value={newRoomType} onChange={(event) => setNewRoomType(event.target.value)}>
          {ROOM_TYPES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <label htmlFor="space-room-width">宽度（mm）</label>
        <input id="space-room-width" value={newWidth} onChange={(event) => setNewWidth(event.target.value)} />
        <label htmlFor="space-room-depth">进深（mm）</label>
        <input id="space-room-depth" value={newDepth} onChange={(event) => setNewDepth(event.target.value)} />
        <button type="button" disabled={busy} onClick={addRoom}>
          添加房间
        </button>
      </fieldset>

      {plan && (
        <div className="space-editor">
          <svg
            role="img"
            aria-label="2D 空间编辑"
            viewBox={viewBox}
            width="100%"
            height="320"
            style={{ border: '1px solid #ccc', background: '#fafafa' }}
          >
            {plan.rooms.map((room) => {
              const corners = roomCorners(room);
              const path = corners.map((point) => `${point.x},${point.y}`).join(' ');
              return (
                <polygon
                  key={room.id}
                  points={path}
                  data-testid={`room-${room.id}`}
                  aria-label={`房间 ${room.name}`}
                  onClick={() => {
                    setSelectedRoomId(room.id);
                    setSelectedObjectId(null);
                  }}
                  fill={selectedRoomId === room.id ? '#dbeafe' : '#ffffff'}
                  stroke="#334155"
                  strokeWidth={40}
                />
              );
            })}
            {plan.objects.map((object) => {
              const room = plan.rooms.find((item) => item.id === object.roomId);
              if (!room) return null;
              const width = typeof object.geometry.width === 'number' ? object.geometry.width : 800;
              const depth = typeof object.geometry.depth === 'number' ? object.geometry.depth : 800;
              const centerX =
                typeof object.geometry.x === 'number'
                  ? object.geometry.x
                  : room.origin.x + room.size.width / 2;
              const centerY =
                typeof object.geometry.y === 'number'
                  ? object.geometry.y
                  : room.origin.y + room.size.depth / 2;
              return (
                <rect
                  key={object.id}
                  x={centerX - width / 2}
                  y={centerY - depth / 2}
                  width={width}
                  height={depth}
                  fill="#f59e0b"
                  stroke="#b45309"
                  strokeWidth={30}
                  data-testid={`object-${object.id}`}
                  aria-label={`家具 ${object.label}`}
                  onClick={() => {
                    setSelectedObjectId(object.id);
                    setSelectedRoomId(room.id);
                  }}
                />
              );
            })}
          </svg>

          <ul className="space-rooms">
            {plan.rooms.map((room) => (
              <li key={room.id}>
                <button type="button" onClick={() => setSelectedRoomId(room.id)}>
                  {room.name}
                </button>
                <span className="question-hint">
                  {room.size.width}×{room.size.depth}mm · {room.walls.length} 面墙
                </span>
                <button type="button" disabled={busy} onClick={() => renameRoom(room)}>
                  重命名
                </button>
                <button type="button" disabled={busy} onClick={() => resizeRoom(room)}>
                  修改尺寸
                </button>
                {isHomeowner && (
                  <button type="button" disabled={busy} onClick={() => deleteRoom(room)}>
                    删除房间
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {plan && plan.rooms.length > 0 && (
        <fieldset>
          <legend>添加家具到选中房间</legend>
          <label htmlFor="space-object-label">家具名称</label>
          <input id="space-object-label" value={objectLabel} onChange={(event) => setObjectLabel(event.target.value)} />
          <button type="button" disabled={busy} onClick={addObject}>
            添加家具
          </button>
          <ul>
            {plan.objects.map((object) => (
              <li key={object.id}>
                {object.label}
                <button
                  type="button"
                  onClick={() => {
                    setSelectedObjectId(object.id);
                    setSelectedRoomId(object.roomId);
                  }}
                >
                  选中
                </button>
                {isHomeowner && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => deleteObject(object)}
                    aria-label={`删除家具 ${object.label}`}
                  >
                    删除
                  </button>
                )}
              </li>
            ))}
          </ul>
        </fieldset>
      )}

      <div className="space-preview">
        <button type="button" onClick={() => setPreviewOpen((current) => !current)}>
          {previewOpen ? '关闭 3D 预览' : '打开 3D 预览'}
        </button>
        {previewOpen && (
          <>
            <iframe
              ref={frame}
              title="OpenPlan3D 本地预览"
              src={`${PREVIEW_URL}/editor`}
              sandbox="allow-scripts allow-same-origin"
              style={{ width: '100%', height: 360, border: '1px solid #ccc' }}
            />
            <p className="question-hint">
              预览仅连接本机 OpenPlan3D（{PREVIEW_URL}），不调用上游云分享、统计或账户；访问令牌不会放入 URL。
              {syncing ? ' 正在将 3D 编辑同步回后端…' : ''}
              {previewNote ? ` ${previewNote}` : ''}
            </p>
            {syncConflict && (
              <p role="alert">
                3D 编辑与服务器版本冲突，草稿已保留。
                <button type="button" disabled={syncing} onClick={() => void retrySync()}>
                  重试同步
                </button>
              </p>
            )}
            {syncConflicts.length > 0 && (
              <ul role="alert">
                {syncConflicts.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            )}
            {syncNotes.length > 0 && (
              <ul role="note">
                {syncNotes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            )}
            {!isAllowedPreviewOrigin(PREVIEW_URL, PREVIEW_URL) && <p role="alert">预览地址不受信任。</p>}
          </>
        )}
      </div>

      {materialOptions.length > 0 && (
        <details>
          <summary>受支持的材质目录（{materialOptions.length}）</summary>
          <ul>
            {materialOptions.map((option) => (
              <li key={option.id}>
                {option.label}（{option.targets.join('、')}）
              </li>
            ))}
          </ul>
        </details>
      )}

      <BindingPanel
        client={client}
        projectId={projectId}
        role={role}
        stateVersion={expectedVersion}
        plan={plan}
        materials={materials}
        onApplied={setSnapshot}
        onChanged={onChanged}
      />
    </section>
  );
}
