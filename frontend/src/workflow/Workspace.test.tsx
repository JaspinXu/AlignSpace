import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiClient } from '../api';
import { BRIEF_HASH, briefSnapshot, conflictSnapshot, snapshot } from '../test/fixtures';
import type { ProjectSnapshot } from '../types';
import { Workspace } from './Workspace';
import type { WorkspacePage } from '../navigation/workspaceRoute';

const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function setup(
  role: 'homeowner' | 'designer' = 'homeowner',
  initial: ProjectSnapshot = snapshot(role),
) {
  let state = initial;
  const writes: RequestInit[] = [];
  let conflict = false;
  let heldWrite: ReturnType<typeof deferred<Response>> | undefined;
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url, init) => {
    if (url === '/v1/auth/refresh') return response({ accessToken: 'token', user: { id: 'u1', email: 'user@example.com', emailVerified: false } });
    if (init?.method === 'GET') return response(state);
    writes.push(init || {});
    if (heldWrite) {
      const held = heldWrite;
      heldWrite = undefined;
      return held.promise;
    }
    if (conflict) {
      conflict = false;
      state = { ...state, projectState: { ...state.projectState, stateVersion: 5 }, project: { ...state.project, stateVersion: 5 } };
      return response({ error: { code: 'STATE_VERSION_STALE', message: 'stale', correlationId: 'c1', recoverable: true, details: {} } }, 409);
    }
    return response({ projectState: state.projectState });
  });
  const client = new ApiClient({ fetcher, locks: null, channel: null });
  return { client, fetcher, writes, conflict: () => { conflict = true; }, setState: (next: typeof state) => { state = next; },
    holdWrite: () => { heldWrite = deferred<Response>(); return heldWrite; },
  };
}

function detailSnapshot(): ProjectSnapshot {
  const base = snapshot();
  return { ...base, pendingQuestion: { ...base.pendingQuestion!, id: 'detail-lighting',
    repetitionFingerprint: 'detail:lighting', text: '您喜欢什么样的灯光？', kind: 'detail',
    targetElement: 'lighting', dimension: 'lighting',
    options: [{ label: 'lighting · lighting · warm ambient', value: 'warm ambient', assetId: 'a1',
      targetElement: 'lighting', dimension: 'lighting', attributeId: 'mock-lighting-lighting' }] } };
}

describe('read-only brief entry', () => {
  it.each(['偏好内容', '约束内容', '您的回答'])('protects unsaved %s before opening the reader', async (label) => {
    const initial = briefSnapshot(label === '约束内容' ? 'designer' : 'homeowner');
    if (label === '您的回答') initial.pendingQuestion = detailSnapshot().pendingQuestion;
    const env = setup(initial.project.role, initial);
    await env.client.restore();
    const open = vi.fn();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<Workspace page={label === '约束内容' ? 'negotiation' : 'inspiration'} client={env.client} projectId="p1" onOpenBrief={open} />);
    fireEvent.change(await screen.findByLabelText(label), { target: { value: '未保存的内容' } });
    await userEvent.click(screen.getByRole('button', { name: '查看设计说明书' }));
    expect(confirm).toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
    expect(screen.getByLabelText(label)).toHaveValue('未保存的内容');
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole('button', { name: '查看设计说明书' }));
    expect(open).toHaveBeenCalledWith(1);
    confirm.mockRestore();
  });
});

describe('question draft recovery', () => {
  it.each(['changes', 'disappears'])('keeps an unsent answer recoverable when the remote question %s', async (transition) => {
    const initial = detailSnapshot();
    const env = setup('homeowner', initial);
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    fireEvent.change(await screen.findByLabelText('您的回答'), { target: { value: '未提交的暖光想法' } });
    env.setState({ ...initial, pendingQuestion: transition === 'changes'
      ? { ...initial.pendingQuestion!, id: 'detail-layout', text: '您喜欢什么样的布局？' } : null });
    await act(async () => { fireEvent.focus(window); });
    expect(screen.getByRole('textbox', { name: '未提交的回答：您喜欢什么样的灯光？' })).toHaveValue('未提交的暖光想法');
    if (transition === 'changes') {
      expect(screen.getByLabelText('您的回答')).toHaveValue('');
      await userEvent.click(screen.getByRole('button', { name: '提交回答' }));
      expect(env.writes).toHaveLength(0);
    }
    env.setState(initial);
    await act(async () => { fireEvent.focus(window); });
    expect(screen.getByLabelText('您的回答')).toHaveValue('未提交的暖光想法');
  });

  it('retains broad selections under their original question', async () => {
    const initial = snapshot();
    const env = setup('homeowner', initial);
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await userEvent.click(await screen.findByRole('checkbox', { name: /wall/ }));
    env.setState(detailSnapshot());
    await act(async () => { fireEvent.focus(window); });
    expect(screen.getByRole('textbox', { name: '未提交的回答：Which elements?' })).toHaveValue('a1::wall');
    expect(screen.getByLabelText('您的回答')).toHaveValue('');
    env.setState(initial);
    await act(async () => { fireEvent.focus(window); });
    expect(screen.getByRole('checkbox', { name: /wall/ })).toBeChecked();
  });

  it.each([false, true])('clears only the submitted question revision (edited during request: %s)', async (edited) => {
    const initial = detailSnapshot();
    const env = setup('homeowner', initial);
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    const field = await screen.findByLabelText('您的回答');
    fireEvent.change(field, { target: { value: '原回答' } });
    const held = env.holdWrite();
    await userEvent.click(screen.getByRole('button', { name: '提交回答' }));
    if (edited) {
      fireEvent.change(field, { target: { value: '后续修改' } });
      // Returning to the submitted text is still a newer, unsent revision.
      fireEvent.change(field, { target: { value: '原回答' } });
    }
    env.setState({ ...initial, pendingQuestion: { ...initial.pendingQuestion!, id: 'next-question', text: '下一个问题' } });
    await act(async () => { fireEvent.focus(window); });
    fireEvent.change(screen.getByLabelText('您的回答'), { target: { value: '新问题的草稿' } });
    await act(async () => { held.resolve(response({ projectState: initial.projectState })); });
    expect(screen.getByLabelText('您的回答')).toHaveValue('新问题的草稿');
    const previous = screen.queryByRole('textbox', { name: '未提交的回答：您喜欢什么样的灯光？' });
    if (edited) expect(previous).toHaveValue('原回答');
    else expect(previous).not.toBeInTheDocument();
    expect(env.writes).toHaveLength(1);
  });

  it('keeps the question draft on a rejected write', async () => {
    const env = setup('homeowner', detailSnapshot());
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    fireEvent.change(await screen.findByLabelText('您的回答'), { target: { value: '保留回答' } });
    env.conflict();
    await userEvent.click(screen.getByRole('button', { name: '提交回答' }));
    await screen.findByText(/输入已保留/);
    expect(screen.getByLabelText('您的回答')).toHaveValue('保留回答');
  });
});

describe('role-aware work area', () => {
  it('shows the actual detail question and submits the written answer', async () => {
    const base = snapshot();
    const env = setup('homeowner', { ...base, pendingQuestion: {
      ...base.pendingQuestion!, id: 'question-lighting-lighting',
      repetitionFingerprint: 'detail:lighting:lighting', text: '您喜欢什么样的灯光？',
    } });
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await screen.findByText('您喜欢什么样的灯光？');
    expect(screen.queryByRole('checkbox', { name: /暖色灯光/ })).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole('textbox', { name: '您的回答' }), '2700K 暖色间接光');
    await userEvent.click(screen.getByRole('button', { name: '提交回答' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    expect(JSON.parse(String(env.writes[0].body)).data.answer).toBe('2700K 暖色间接光');
  });

  it('creates separate attributes when the owner saves multiple preferences', async () => {
    const env = setup();
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    const field = await screen.findByRole('textbox', { name: '偏好内容' });
    await userEvent.type(field, '温暖现代');
    await userEvent.click(screen.getByRole('button', { name: '保存偏好' }));
    await waitFor(() => expect(field).toHaveValue(''));
    await userEvent.selectOptions(screen.getByLabelText('偏好维度'), 'layout');
    await userEvent.type(field, '开阔布局');
    await userEvent.click(screen.getByRole('button', { name: '保存偏好' }));
    await waitFor(() => expect(env.writes).toHaveLength(2));
    const paths = env.fetcher.mock.calls.filter(([, init]) => init?.method === 'PATCH').map(([url]) => url);
    expect(paths[0]).not.toBe(paths[1]);
  });

  it('polls designer waits without a pending question and pauses while hidden', async () => {
    const base = snapshot();
    const env = setup('homeowner', { ...base, pendingQuestion: null,
      projectState: { ...base.projectState, waitReason: 'designer' } });
    await env.client.restore();
    const view = render(<Workspace page="overview" client={env.client} projectId="p1" />);
    await screen.findByRole('heading', { name: '当前任务' });
    vi.useFakeTimers();
    // Remount so the polling interval is installed on the controlled clock.
    view.unmount();
    render(<Workspace page="overview" client={env.client} projectId="p1" />);
    try {
      await act(async () => {});
      const before = env.fetcher.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
      expect(env.fetcher.mock.calls.length).toBeGreaterThan(before);
      vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
      const hidden = env.fetcher.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
      expect(env.fetcher.mock.calls.length).toBe(hidden);
    } finally { vi.useRealTimers(); }
  });
  it('lets the homeowner pick parts and sends structured parts', async () => {
    const env = setup();
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await userEvent.click(await screen.findByRole('checkbox', { name: /lighting/ }));
    await userEvent.click(screen.getByRole('button', { name: '提交回答' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    expect(JSON.parse(String(env.writes[0].body)).data.parts).toEqual([
      { assetId: 'a1', targetElement: 'lighting' },
    ]);
  });

  it('shows a designer the shared state without homeowner answer or sample controls', async () => {
    const env = setup('designer');
    await env.client.restore();
    render(<Workspace page="overview" client={env.client} projectId="p1" />);
    await screen.findByText('等待屋主回答');
    expect(screen.queryByRole('button', { name: '提交回答' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '登记演示样本' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新增偏好' })).not.toBeInTheDocument();
  });

  it('lets a designer view reference images without upload or delete controls', async () => {
    const env = setup('designer');
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await screen.findByRole('heading', { name: '参考图片' });
    expect(screen.getAllByText(/room\.png/).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText('上传参考图片')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /删除 room\.png/ })).not.toBeInTheDocument();
  });

  it('preserves an edited attribute on 409, refetches and uses a new key/version on deliberate resubmit', async () => {
    const env = setup();
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    const field = await screen.findByRole('textbox', { name: /偏好内容/ });
    await userEvent.clear(field);
    await userEvent.type(field, '柔和的阅读灯');
    env.conflict();
    await userEvent.click(screen.getByRole('button', { name: '保存偏好' }));
    await screen.findByText(/输入已保留/);
    expect(field).toHaveValue('柔和的阅读灯');
    expect(env.writes).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: '保存偏好' }));
    await waitFor(() => expect(env.writes).toHaveLength(2));
    const first = JSON.parse(String(env.writes[0].body));
    const second = JSON.parse(String(env.writes[1].body));
    expect(second.expectedStateVersion).toBe(5);
    expect(second.idempotencyKey).not.toBe(first.idempotencyKey);
    expect(second.data.value).toBe('柔和的阅读灯');
  });

  it('refreshes on focus and stops listening on navigation', async () => {
    const env = setup('designer');
    await env.client.restore();
    const view = render(<Workspace page="overview" client={env.client} projectId="p1" />);
    await screen.findByText('等待屋主回答');
    const before = env.fetcher.mock.calls.length;
    fireEvent.focus(window);
    await waitFor(() => expect(env.fetcher.mock.calls.length).toBeGreaterThan(before));
    view.unmount();
    const after = env.fetcher.mock.calls.length;
    fireEvent.focus(window);
    expect(env.fetcher).toHaveBeenCalledTimes(after);
  });
});

describe('preference and conflict decisions', () => {
  it('lets the homeowner confirm a proposed visual observation', async () => {
    const env = setup('homeowner', conflictSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await userEvent.click(await screen.findByRole('button', { name: '确认 warm ambient' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data).toEqual({ status: 'confirmed', value: 'warm ambient' });
    expect(env.writes[0].method).toBe('PATCH');
  });

  it('lets the homeowner reject a proposed visual observation', async () => {
    const env = setup('homeowner', conflictSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await userEvent.click(await screen.findByRole('button', { name: '拒绝 warm ambient' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data.status).toBe('rejected');
  });

  it('hides homeowner preference controls from the designer', async () => {
    const env = setup('designer', conflictSnapshot('designer'));
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await screen.findByText(/天然石材与预算冲突/);
    expect(screen.queryByRole('button', { name: '确认 warm ambient' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '拒绝 warm ambient' })).not.toBeInTheDocument();
  });

  it('resolves an open conflict with a written decision', async () => {
    const env = setup('homeowner', conflictSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace page="negotiation" client={env.client} projectId="p1" />);
    const field = await screen.findByRole('textbox', { name: /冲突解决说明/ });
    await userEvent.type(field, '改用低成本的石材效果饰面');
    await userEvent.click(screen.getByRole('button', { name: '提交冲突决定' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data).toEqual({ status: 'resolved', resolution: '改用低成本的石材效果饰面' });
  });
});

describe('designer review and brief approval', () => {
  it.each(['poll-before-PATCH', 'PATCH-before-poll'])('preserves newer goals and blocks mismatched approval: %s', async (order) => {
    const initial = briefSnapshot();
    const env = setup('homeowner', initial);
    await env.client.restore();
    render(<Workspace page="approval" client={env.client} projectId="p1" />);
    const field = await screen.findByLabelText('方案目标');
    fireEvent.change(field, { target: { value: '提交目标 A' } });
    const held = env.holdWrite();
    await userEvent.click(screen.getByRole('button', { name: '保存方案修改' }));
    fireEvent.change(field, { target: { value: '较新的草稿 B' } });
    const saved = { ...initial, project: { ...initial.project, stateVersion: 9 },
      projectState: { ...initial.projectState, stateVersion: 9, briefVersions: [{
        ...initial.projectState.briefVersions[0], version: 2, contentHash: 'b'.repeat(64),
        payload: { ...initial.projectState.briefVersions[0].payload, goals: ['提交目标 A'] },
      }] } };
    env.setState(saved);
    vi.useFakeTimers();
    // Re-install the existing interval on the controlled clock without remounting drafts.
    const poll = async () => { await act(async () => { fireEvent.focus(window); }); };
    try {
      if (order === 'poll-before-PATCH') await poll();
      await act(async () => { held.resolve(response(saved.projectState.briefVersions[0])); });
      if (order === 'PATCH-before-poll') await poll();
      expect(screen.getByText(/方案版本 v2/)).toBeInTheDocument();
      expect(field).toHaveValue('较新的草稿 B');
      expect(screen.getByRole('button', { name: '批准此版本' })).toBeDisabled();
      fireEvent.click(screen.getByRole('button', { name: '批准此版本' }));
      expect(env.writes).toHaveLength(1);
    } finally { vi.useRealTimers(); }
    // A subsequent save of B may clear that revision and enable approval of B's hash.
    env.setState({ ...saved, project: { ...saved.project, stateVersion: 10 },
      projectState: { ...saved.projectState, stateVersion: 10, briefVersions: [{
        ...saved.projectState.briefVersions[0], version: 3, contentHash: 'c'.repeat(64),
        payload: { ...saved.projectState.briefVersions[0].payload, goals: ['较新的草稿 B'] },
      }] } });
    await userEvent.click(screen.getByRole('button', { name: '保存方案修改' }));
    await screen.findByText(/方案版本 v3/);
    expect(field).toHaveValue('较新的草稿 B');
    expect(screen.getByRole('button', { name: '批准此版本' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: '批准此版本' }));
    expect(JSON.parse(String(env.writes[2].body)).data.contentHash).toBe('c'.repeat(64));
  });

  it('requires saving the displayed draft before approving a server version', async () => {
    const env = setup('homeowner', briefSnapshot());
    await env.client.restore();
    render(<Workspace page="approval" client={env.client} projectId="p1" />);
    const field = await screen.findByLabelText('方案目标');
    await waitFor(() => expect(field).toHaveValue('warm modern'));
    await userEvent.type(field, ' with softer lighting');
    expect(screen.getByRole('button', { name: '批准此版本' })).toBeDisabled();
  });
  it('retains a brief draft after 409 and loading the newer brief version', async () => {
    const initial = briefSnapshot();
    const env = setup('homeowner', initial);
    await env.client.restore();
    render(<Workspace page="approval" client={env.client} projectId="p1" />);
    const field = await screen.findByLabelText('方案目标');
    await waitFor(() => expect(field).toHaveValue('warm modern'));
    await userEvent.clear(field);
    await userEvent.type(field, '我的本地修改');
    env.setState({ ...initial, projectState: { ...initial.projectState,
      briefVersions: [{ ...initial.projectState.briefVersions[0], version: 2,
        contentHash: 'b'.repeat(64), payload: { goals: ['另一方的新目标'] } }],
    } });
    env.conflict();
    await userEvent.click(screen.getByRole('button', { name: '保存方案修改' }));
    await screen.findByText(/方案版本 v2/);
    expect(field).toHaveValue('我的本地修改');
  });
  it('lets a designer submit a review note', async () => {
    const base = snapshot('designer');
    const initial: ProjectSnapshot = {
      ...base,
      pendingQuestion: null,
      projectState: { ...base.projectState, waitReason: 'designer', currentNode: 'wait_designer' },
    };
    const env = setup('designer', initial);
    await env.client.restore();
    render(<Workspace page="negotiation" client={env.client} projectId="p1" />);
    const field = await screen.findByRole('textbox', { name: /设计师反馈/ });
    await userEvent.type(field, '预算内可用石材效果替代');
    await userEvent.click(screen.getByRole('button', { name: '提交设计师反馈' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data).toEqual({ note: '预算内可用石材效果替代' });
  });

  it('approves the exact brief version and content hash shown', async () => {
    const env = setup('homeowner', briefSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace page="approval" client={env.client} projectId="p1" />);
    await screen.findByText(/方案版本 v1/);
    await userEvent.click(await screen.findByRole('button', { name: '批准此版本' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data).toEqual({ contentHash: BRIEF_HASH });
  });

  it('shows an existing approval from the other party', async () => {
    const env = setup('designer', briefSnapshot('designer'));
    await env.client.restore();
    render(<Workspace page="approval" client={env.client} projectId="p1" />);
    expect(await screen.findByText(/屋主已批准 v1/)).toBeInTheDocument();
  });

  it('edits the brief into a new version using the full payload', async () => {
    const env = setup('designer', briefSnapshot('designer'));
    await env.client.restore();
    render(<Workspace page="approval" client={env.client} projectId="p1" />);
    const field = await screen.findByRole('textbox', { name: /方案目标/ });
    await waitFor(() => expect(field).toHaveValue('warm modern'));
    await userEvent.clear(field);
    await userEvent.type(field, 'warm modern{enter}calm lighting');
    await userEvent.click(screen.getByRole('button', { name: '保存方案修改' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data.payload.project.id).toBe('p1');
    expect(body.data.payload.goals).toEqual(['warm modern', 'calm lighting']);
  });
});

describe('real image uploads', () => {
  it('uploads a selected file with the current version and a new key', async () => {
    const env = setup('homeowner');
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    const input = await screen.findByLabelText('上传参考图片');
    const file = new File([new Uint8Array([1, 2, 3])], 'room.png', { type: 'image/png' });
    await userEvent.upload(input, file);
    await waitFor(() => expect(env.writes).toHaveLength(1));
    expect(env.writes[0].method).toBe('POST');
    expect(env.writes[0].body).toBeInstanceOf(FormData);
    expect((env.writes[0].body as FormData).get('expectedStateVersion')).toBe('4');
    expect((env.writes[0].body as FormData).get('file')).toBeInstanceOf(File);
  });

  it('marks observations whose source image was deleted', async () => {
    const base = snapshot('homeowner');
    const initial: ProjectSnapshot = {
      ...base,
      project: {
        ...base.project,
        assets: [{ ...base.project.assets[0], deleted: true, deletedAt: 1 }],
      },
    };
    const env = setup('homeowner', initial);
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    expect(await screen.findByText('来源图片已删除')).toBeInTheDocument();
  });
});

describe('designer constraints', () => {
  it('lets the designer create a constraint and shows the rationale to everyone', async () => {
    const env = setup('designer', conflictSnapshot('designer'));
    await env.client.restore();
    render(<Workspace page="negotiation" client={env.client} projectId="p1" />);
    expect(await screen.findByText(/理由：/)).toBeInTheDocument();

    await userEvent.type(
      await screen.findByLabelText('约束内容'),
      '工作台石材需控制在当前预算档位',
    );
    await userEvent.type(screen.getByLabelText('约束理由'), '改用石材效果饰面');
    await userEvent.click(screen.getByRole('button', { name: '保存约束' }));

    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data.category).toBe('budget');
    expect(body.data.statement).toBe('工作台石材需控制在当前预算档位');
    expect(body.data.rationale).toBe('改用石材效果饰面');
  });

  it('hides constraint write controls from the homeowner', async () => {
    const env = setup('homeowner', conflictSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace page="negotiation" client={env.client} projectId="p1" />);
    expect(await screen.findByText(/理由：/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存约束' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^撤销 / })).not.toBeInTheDocument();
  });

  it('lets the designer withdraw a constraint', async () => {
    const env = setup('designer', conflictSnapshot('designer'));
    await env.client.restore();
    render(<Workspace page="negotiation" client={env.client} projectId="p1" />);
    await userEvent.click(
      await screen.findByRole('button', { name: '撤销 天然石材超出预算' }),
    );
    await waitFor(() => expect(env.writes).toHaveLength(1));
    expect(env.writes[0].method).toBe('POST');
    expect(JSON.parse(String(env.writes[0].body)).data).toEqual({});
  });
});

describe('constraint editing and preference revision', () => {
  it('lets the designer edit an existing constraint', async () => {
    const env = setup('designer', conflictSnapshot('designer'));
    await env.client.restore();
    render(<Workspace page="negotiation" client={env.client} projectId="p1" />);
    await userEvent.click(
      await screen.findByRole('button', { name: '编辑 天然石材超出预算' }),
    );
    const statement = screen.getByLabelText('约束内容');
    await userEvent.clear(statement);
    await userEvent.type(statement, '天然石材改为关键限制');
    await userEvent.click(screen.getByRole('button', { name: '更新约束' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const write = env.writes[0];
    expect(write.method).toBe('PATCH');
    const body = JSON.parse(String(write.body));
    expect(body.data.statement).toBe('天然石材改为关键限制');
  });

  it('sends declared incompatible values from the constraint form', async () => {
    const env = setup('designer', conflictSnapshot('designer'));
    await env.client.restore();
    render(<Workspace page="negotiation" client={env.client} projectId="p1" />);
    await userEvent.type(await screen.findByLabelText('约束内容'), '新约束');
    await userEvent.type(screen.getByLabelText('不兼容取值（逗号分隔）'), 'warm ambient, pale oak');
    await userEvent.click(screen.getByRole('button', { name: '保存约束' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data.incompatibleWith).toEqual(['warm ambient', 'pale oak']);
  });

  it('lets the homeowner revise an existing confirmed preference', async () => {
    const env = setup('homeowner', conflictSnapshot('homeowner'));
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await userEvent.selectOptions(
      await screen.findByLabelText('选择偏好'),
      'mock-lighting-lighting',
    );
    await userEvent.type(screen.getByLabelText('新的取值'), 'warm ambient');
    await userEvent.click(screen.getByRole('button', { name: '保存偏好修改' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    expect(env.writes[0].method).toBe('PATCH');
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data.value).toBe('warm ambient');
  });
});

describe('structured homeowner interview', () => {
  it('sends a confirmed detail selection together with a note', async () => {
    const env = setup('homeowner', detailSnapshot());
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await userEvent.click(await screen.findByRole('button', { name: '喜欢' }));
    await userEvent.type(screen.getByLabelText('您的回答'), '备注文字');
    await userEvent.click(screen.getByRole('button', { name: '提交回答' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    const body = JSON.parse(String(env.writes[0].body));
    expect(body.data.selection).toEqual([
      {
        attributeId: 'mock-lighting-lighting',
        assetId: 'a1',
        targetElement: 'lighting',
        dimension: 'lighting',
        decision: 'confirmed',
        value: 'warm ambient',
      },
    ]);
    expect(body.data.answer).toBe('备注文字');
  });

  it('marks a detail option as not applicable and skips without preferences', async () => {
    const env = setup('homeowner', detailSnapshot());
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    await userEvent.click(await screen.findByRole('button', { name: '不在意' }));
    await userEvent.click(screen.getByRole('button', { name: '提交回答' }));
    await waitFor(() => expect(env.writes).toHaveLength(1));
    expect(JSON.parse(String(env.writes[0].body)).data.selection[0].decision).toBe(
      'not_applicable',
    );

    await userEvent.click(screen.getByRole('button', { name: '跳过' }));
    await waitFor(() => expect(env.writes).toHaveLength(2));
    expect(JSON.parse(String(env.writes[1].body)).data.skipped).toBe(true);
  });

  it('labels the free-text field as a note the system does not parse', async () => {
    const env = setup('homeowner', detailSnapshot());
    await env.client.restore();
    render(<Workspace page="inspiration" client={env.client} projectId="p1" />);
    expect(await screen.findByText(/系统不会自动理解/)).toBeInTheDocument();
  });
});


describe('page lifecycle', () => {
  it('keeps an unsaved preference draft across page switches', async () => {
    const env = setup();
    await env.client.restore();
    function Harness() {
      const [page, setPage] = useState<WorkspacePage>('inspiration');
      return (
        <Workspace page={page} onNavigate={setPage} client={env.client} projectId="p1" />
      );
    }
    render(<Harness />);
    fireEvent.change(await screen.findByLabelText('偏好内容'), { target: { value: '暖白与橄榄绿' } });
    await userEvent.click(screen.getByRole('button', { name: '方案审批' }));
    expect(screen.queryByRole('textbox', { name: '偏好内容' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: '灵感与偏好' }));
    expect(screen.getByLabelText('偏好内容')).toHaveValue('暖白与橄榄绿');
  });

  it('keeps the space panel mounted when switching pages', async () => {
    const env = setup();
    await env.client.restore();
    function Harness() {
      const [page, setPage] = useState<WorkspacePage>('space');
      return (
        <Workspace page={page} onNavigate={setPage} client={env.client} projectId="p1" />
      );
    }
    render(<Harness />);
    const panel = await screen.findByRole('region', { name: '空间草稿' });
    await userEvent.click(screen.getByRole('button', { name: '设计协商' }));
    await userEvent.click(screen.getByRole('button', { name: '空间方案' }));
    expect(screen.getByRole('region', { name: '空间草稿' })).toBe(panel);
  });
});


describe('overview content', () => {
  it('shows budget, members and the next step', async () => {
    const env = setup();
    await env.client.restore();
    render(<Workspace page="overview" client={env.client} projectId="p1" />);
    const overview = await screen.findByRole('region', { name: '项目概览摘要' });
    expect(overview).toHaveTextContent('预算');
    expect(overview).toHaveTextContent('15k_to_30k_sgd');
    expect(overview).toHaveTextContent('设计师已加入');
    expect(overview).toHaveTextContent('下一步');
  });
});
