import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiClient, ApiError } from '../api';
import type { ProjectSnapshot } from '../types';
import { approvalSummary, presentBrief } from './briefPresentation';

type Props = {
  client: ApiClient;
  projectId: string;
  version: string | null;
  onVersion: (version: number, replace?: boolean) => void;
  onBack: () => void;
};

export function BriefDetail({ client, projectId, version, onVersion, onBack }: Props) {
  const [loaded, setLoaded] = useState<{ id: string; data: ProjectSnapshot } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const serial = useRef(0);
  const snapshot = loaded?.id === projectId ? loaded.data : null;

  const load = useCallback(async () => {
    const request = ++serial.current;
    setBusy(true);
    try {
      const data = await client.get<ProjectSnapshot>(`/v1/projects/${encodeURIComponent(projectId)}/state`);
      if (request !== serial.current) return;
      if (data.project?.id !== projectId || data.projectState?.projectId !== projectId ||
          !Array.isArray(data.projectState?.briefVersions) || !Array.isArray(data.projectState?.approvals)) {
        setLoaded(null);
        throw new Error('无法读取设计说明书：项目数据无效。');
      }
      setLoaded({ id: projectId, data });
      setError(null);
    } catch (cause) {
      if (request !== serial.current) return;
      if (cause instanceof ApiError && [401, 403, 404].includes(cause.status)) setLoaded(null);
      setError(cause instanceof Error ? cause.message : '无法加载设计说明书。');
    } finally {
      if (request === serial.current) setBusy(false);
    }
  }, [client, projectId]);

  useEffect(() => {
    setError(null);
    void load();
    const onFocus = () => { void load(); };
    window.addEventListener('focus', onFocus);
    const unsubscribe = client.onSessionEnded(() => {
      ++serial.current;
      setLoaded(null);
      setError('会话已结束，请重新登录。');
      setBusy(false);
    });
    return () => { ++serial.current; window.removeEventListener('focus', onFocus); unsubscribe(); };
  }, [client, load, version]);

  const versions = [...(snapshot?.projectState.briefVersions ?? [])].sort((a, b) => b.version - a.version);
  const latest = versions[0];
  const numericVersion = version === null ? latest?.version : /^[1-9]\d*$/.test(version) ? Number(version) : NaN;
  const selected = versions.find((item) => item.version === numericVersion);
  useEffect(() => {
    if (version === null && latest) onVersion(latest.version, true);
  }, [version, latest?.version, onVersion]);

  let content;
  if (!snapshot) {
    content = error ? <p role="alert">{error}</p> : <p>正在加载设计说明书…</p>;
  } else if (version !== null && !selected) {
    content = <p role="alert">版本不存在或无效，请选择可用版本。</p>;
  } else if (!latest) {
    content = <p>尚未生成设计说明书</p>;
  } else if (selected) {
    try {
      const display = presentBrief(selected, projectId);
      content = <>
        <p>{selected.version === latest.version ? '最新版本' : '历史版本 · 只读'} · v{selected.version}</p>
        {selected.version !== latest.version && <p className="notice">已有更新版本 v{latest.version}，可通过版本选择器查看。</p>}
        <p className="hash">内容哈希：{selected.contentHash}</p>
        <section aria-label="项目概况"><h2>项目概况</h2>
          <Entries items={display.sections.find((section) => section.title === '项目概况')?.items ?? [`项目 ID：${display.projectId}`]} />
          <p>房间类型、预算等历史项目信息：未记录</p></section>
        <section aria-label="设计目标"><h2>设计目标</h2><Entries items={display.goals} /></section>
        {display.sections.filter((section) => section.title !== '项目概况').map((section) => <section key={section.title} aria-label={section.title}>
          <h2>{section.title}</h2><Entries items={section.items} />
        </section>)}
        <section aria-label="版本完整度"><h2>版本完整度</h2>
          <p>{Math.round(selected.completeness * 100)}%（系统记录完整度，不代表双方一致率或设计可行性）</p></section>
        <section aria-label="审批信息"><h2>审批信息</h2>
          {approvalSummary(selected, snapshot.projectState).map((line, i) => <p key={i}>{line}</p>)}
        </section>
      </>;
    } catch (cause) {
      content = <p role="alert">{cause instanceof Error ? cause.message : '无法读取设计说明书内容。'}</p>;
    }
  }

  return <main className="brief-reader">
    <header><h1>设计说明书</h1><p>只读版本快照 · 图片分析仍为模拟</p>
      <div className="actions">
        <button type="button" onClick={onBack}>返回工作区</button>
        <button type="button" disabled={busy} onClick={() => void load()}>刷新状态</button>
      </div>
      {latest && <label>说明书版本<select value={selected?.version ?? ''}
        onChange={(event) => onVersion(Number(event.target.value))}>
        {!selected && <option value="" disabled>请选择版本</option>}
        {versions.map((item) => <option key={item.version} value={item.version}>v{item.version}{item.version === latest.version ? ' · 最新' : ''}</option>)}
      </select></label>}
    </header>
    {error && snapshot && <p role="alert" className="error">状态更新失败，审批状态可能不是最新。{error}</p>}
    {content}
  </main>;
}

function Entries({ items }: { items: string[] | null }) {
  if (items === null) return <p>未记录</p>;
  if (!items.length) return <p>此版本未记录相关内容</p>;
  return <ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul>;
}
