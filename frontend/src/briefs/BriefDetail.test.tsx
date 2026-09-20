import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiClient } from '../api';
import { briefSnapshot } from '../test/fixtures';
import { BriefDetail } from './BriefDetail';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
async function setup() {
  let state = briefSnapshot();
  state.projectState.briefVersions.push({ ...state.projectState.briefVersions[0], version: 2,
    contentHash: 'b'.repeat(64), payload: { project: { id: 'p1' }, version: 2, goals: ['新目标'] } });
  let failure = 0;
  const fetcher = vi.fn<typeof fetch>(async (url) => url === '/v1/auth/refresh'
    ? json({ accessToken: 't', user: { id: 'u1' } })
    : failure ? json({ error: { message: '读取失败' } }, failure) : json(state));
  const client = new ApiClient({ fetcher, locks: null, channel: null });
  await client.restore();
  return { client, fetcher, fail: (status: number) => { failure = status; },
    setState: (next: typeof state) => { state = next; }, state };
}

describe('brief reader', () => {
  it('reads a fixed historical snapshot, not live preferences, without write controls', async () => {
    const env = await setup();
    render(<BriefDetail client={env.client} projectId="p1" version="1" onVersion={vi.fn()} onBack={vi.fn()} />);
    expect(await screen.findByText('warm modern')).toBeVisible();
    expect(screen.queryByText('新目标')).not.toBeInTheDocument();
    expect(screen.queryByText('warm ambient')).not.toBeInTheDocument();
    expect(screen.getAllByRole('heading', { name: '项目概况' })).toHaveLength(1);
    expect(screen.getByText(/历史审批记录不可用/)).toBeVisible();
    expect(screen.queryByRole('button', { name: '批准此版本' })).not.toBeInTheDocument();
    expect(env.fetcher.mock.calls.filter(([, init]) => init?.method && init.method !== 'GET')).toHaveLength(1); // auth refresh only
  });

  it('renders hostile content as text, and rejects a snapshot from another project', async () => {
    const env = await setup();
    env.state.projectState.briefVersions[0].payload.goals = ['<img src=x onerror=alert(1)>'];
    render(<BriefDetail client={env.client} projectId="p1" version="1" onVersion={vi.fn()} onBack={vi.fn()} />);
    expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeVisible();
    expect(document.querySelector('.brief-reader img')).toBeNull();
    env.state.projectState.briefVersions[0].payload.project = { id: 'other-project' };
    await userEvent.click(screen.getByRole('button', { name: '刷新状态' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('项目不匹配');
  });

  it('pins an omitted version to latest and delegates explicit version selection', async () => {
    const env = await setup(); const onVersion = vi.fn();
    render(<BriefDetail client={env.client} projectId="p1" version={null} onVersion={onVersion} onBack={vi.fn()} />);
    await waitFor(() => expect(onVersion).toHaveBeenCalledWith(2, true));
    await userEvent.selectOptions(screen.getByLabelText('说明书版本'), '1');
    expect(onVersion).toHaveBeenCalledWith(1);
  });

  it.each(['0', '-1', 'abc', '99', '1.5'])('does not silently replace an invalid version %s', async (version) => {
    const env = await setup(); const onVersion = vi.fn();
    render(<BriefDetail client={env.client} projectId="p1" version={version} onVersion={onVersion} onBack={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('版本不存在或无效');
    expect(onVersion).not.toHaveBeenCalled();
    expect(screen.queryByText('新目标')).not.toBeInTheDocument();
  });

  it('retains the selected content on network errors but clears it when access is denied', async () => {
    const env = await setup();
    render(<BriefDetail client={env.client} projectId="p1" version="1" onVersion={vi.fn()} onBack={vi.fn()} />);
    await screen.findByText('warm modern'); env.fail(500);
    await userEvent.click(screen.getByRole('button', { name: '刷新状态' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('审批状态可能不是最新');
    expect(screen.getByText('warm modern')).toBeVisible();
    env.fail(403);
    await userEvent.click(screen.getByRole('button', { name: '刷新状态' }));
    await waitFor(() => expect(screen.queryByText('warm modern')).not.toBeInTheDocument());
  });

  it('keeps version selected after focus refresh discovers a newer version', async () => {
    const env = await setup(); const onVersion = vi.fn();
    render(<BriefDetail client={env.client} projectId="p1" version="2" onVersion={onVersion} onBack={vi.fn()} />);
    await screen.findByText('新目标');
    const next = structuredClone(env.state);
    next.projectState.briefVersions.push({ ...next.projectState.briefVersions[1], version: 3,
      payload: { project: { id: 'p1' }, version: 3, goals: ['第三版'] } });
    env.setState(next); fireEvent.focus(window);
    expect(await screen.findByText(/已有更新版本/)).toBeVisible();
    expect(screen.queryByText('第三版')).not.toBeInTheDocument();
    expect(onVersion).not.toHaveBeenCalled();
  });

  it('discards late responses after project changes', async () => {
    const env = await setup();
    let finish!: (value: Response) => void;
    env.fetcher.mockImplementationOnce(() => new Promise<Response>((r) => { finish = r; }));
    const view = render(<BriefDetail client={env.client} projectId="p1" version="1" onVersion={vi.fn()} onBack={vi.fn()} />);
    const next = structuredClone(env.state);
    next.project.id = 'p2'; next.projectState.projectId = 'p2';
    next.projectState.briefVersions = [];
    env.setState(next);
    view.rerender(<BriefDetail client={env.client} projectId="p2" version={null} onVersion={vi.fn()} onBack={vi.fn()} />);
    await screen.findByText('尚未生成设计说明书');
    await act(async () => { finish(json(env.state)); });
    expect(screen.queryByText('warm modern')).not.toBeInTheDocument();
  });

  it('ignores an older refresh that arrives after the latest refresh', async () => {
    const env = await setup();
    render(<BriefDetail client={env.client} projectId="p1" version="2" onVersion={vi.fn()} onBack={vi.fn()} />);
    await screen.findByText('新目标');
    let finish!: (value: Response) => void;
    env.fetcher.mockImplementationOnce(() => new Promise<Response>((r) => { finish = r; }));
    fireEvent.focus(window);
    const next = structuredClone(env.state); next.projectState.briefStale = true;
    env.setState(next); fireEvent.focus(window);
    await screen.findByText(/方案已过时/);
    await act(async () => finish(json(env.state)));
    expect(screen.getByText(/方案已过时/)).toBeVisible();
  });
});
