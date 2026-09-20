import { describe, expect, it } from 'vitest';
import type { Approval, BriefVersion, ProjectState } from '../types';
import { approvalSummary, presentBrief } from './briefPresentation';

function brief(payload: unknown = {}): BriefVersion {
  return { version: 1, contentHash: 'hash-1', completeness: 0.75,
    payload: payload as BriefVersion['payload'] };
}
function state(overrides: Partial<ProjectState> = {}): ProjectState {
  return { projectId: 'p1', stateVersion: 5, status: 'approved', attributes: [],
    constraints: [], questions: [], conflicts: [], briefVersions: [brief()], approvals: [],
    completeness: 1, currentNode: null, waitReason: null, ...overrides };
}
function approval(overrides: Partial<Approval> = {}): Approval {
  return { role: 'homeowner', actorId: 'owner-1', briefVersion: 1, contentHash: 'hash-1',
    approvedAt: '2026-09-20T10:00:00Z', ...overrides };
}
const items = (payload: unknown, title: string) =>
  presentBrief(brief(payload), 'p1').sections.find(section => section.title === title)?.items;

describe('presentBrief', () => {
  it('distinguishes absent fields from explicitly empty lists', () => {
    const missing = presentBrief(brief(), 'p1');
    expect(missing.projectId).toBe('p1');
    expect(missing.goals).toBeNull();
    for (const title of ['偏好与来源', '设计师约束', '冲突', '未决事项']) {
      expect(missing.sections.find(section => section.title === title)?.items).toBeNull();
    }
    const empty = presentBrief(brief({ goals: [], attributes: [], constraints: [], conflicts: [], unresolvedDecisions: [] }), 'p1');
    expect(empty.goals).toEqual([]);
    expect(empty.sections.every(section => section.items?.length === 0)).toBe(true);
  });

  it('only exposes trustworthy project data and labels generation status', () => {
    const result = presentBrief(brief({ project: { id: 'p1', status: 'awaiting_approval',
      roomType: 'template-room', budgetBand: 'template-budget', name: 'template-name', housingType: 'template-housing' } }), 'p1');
    const text = JSON.stringify(result);
    expect(text).not.toContain('template-');
    expect(text).toContain('生成时状态');
    expect(text).toContain('等待审批');
  });

  it.each([null, [], 'text', 42, { project: [] }, { project: 'p1' },
    { project: { id: 'other' } }, { project: { id: 1 } }, { project: { status: [] } },
    { version: 2 }, { version: '1' }, { version: 0 },
    { goals: 'goal' }, { goals: [null] }, { attributes: {} }, { attributes: [null] },
    { attributes: [{ value: {} }] }, { attributes: [{ evidence: {} }] },
    { attributes: [{ evidence: [4] }] }, { attributes: [{ evidence: [{ sourceId: [] }] }] },
    { constraints: [false] }, { constraints: [{ appliesTo: [] }] },
    { conflicts: [{ resolution: {} }] }, { unresolvedDecisions: [1] },
  ])('rejects malformed or mismatched payload %j with a readable error', payload => {
    expect(() => presentBrief(brief(payload), 'p1')).toThrow(/说明书.*(格式|项目|版本)/);
  });

  it('rejects an invalid envelope version', () => {
    expect(() => presentBrief({ ...brief(), version: -1 }, 'p1')).toThrow(/版本/);
  });

  it('keeps every attribute status distinct and includes saved evidence IDs and types', () => {
    const statuses = ['proposed', 'confirmed', 'rejected', 'conflicted', 'unresolved', 'not_applicable'];
    const labels = ['待确认', '已确认', '已拒绝', '有冲突', '未决', '不适用'];
    const result = items({ attributes: statuses.map(status => ({ targetElement: 'sofa', dimension: 'material',
      value: 'saved-value', status, evidence: [{ sourceType: 'image', sourceId: 'original-image', description: 'saved evidence' }] })) }, '偏好与来源')!;
    labels.forEach((label, index) => {
      expect(result[index]).toContain(`状态：${label}`);
      for (const text of ['sofa', '材料', 'saved-value', '图片', 'original-image', 'saved evidence']) expect(result[index]).toContain(text);
    });
  });

  it('uses safe text fallbacks for unknown enums, including prototype property names', () => {
    const text = items({ attributes: [{ status: 'toString', dimension: 'future', evidence: [{ sourceType: '__proto__', sourceId: 'e1' }] }] }, '偏好与来源')!.join();
    for (const value of ['未知（toString）', '未知（future）', '未知（__proto__）', '未记录']) expect(text).toContain(value);
  });

  it('renders saved constraint fields and conflict conclusions without invented values', () => {
    const payload = { constraints: [{ category: 'safety', appliesTo: 'wall', statement: 'saved constraint',
      rationale: 'saved reason', severity: 'critical', verificationStatus: 'professional_review_required', owner: 'designer', attributeId: 'a1', proposedBy: 'd1' }],
      conflicts: [{ status: 'accepted_unresolved', summary: 'saved conflict', impact: 'saved impact', resolution: 'saved conclusion' }],
      unresolvedDecisions: ['saved decision'] };
    const constraint = items(payload, '设计师约束')!.join();
    for (const text of ['安全', 'wall', 'saved constraint', 'saved reason', '严重', '需要专业核验', '设计师', 'a1', 'd1']) expect(constraint).toContain(text);
    const conflict = items(payload, '冲突')!.join();
    for (const text of ['接受未解决', 'saved conflict', 'saved impact', 'saved conclusion']) expect(conflict).toContain(text);
    expect(items(payload, '未决事项')).toEqual(['saved decision']);
    expect(items({ conflicts: [{}] }, '冲突')!.join()).toContain('结论：未记录');
  });

  it('preserves literal user text, reads only the snapshot, and does not mutate inputs', () => {
    const text = '<img src=x onerror=alert(1)>';
    const selected = brief({ project: { id: 'p1' }, goals: [text], attributes: [{ value: 'historical value' }] });
    const current = state({ attributes: [{ value: 'current value' } as ProjectState['attributes'][number]] });
    const before = JSON.stringify({ selected, current });
    const result = presentBrief(selected, current.projectId);
    approvalSummary(selected, current);
    expect(result.goals).toEqual([text]);
    expect(JSON.stringify(result)).toContain('historical value');
    expect(JSON.stringify(result)).not.toContain('current value');
    result.goals!.push('local display change');
    expect(JSON.stringify({ selected, current })).toBe(before);
  });
});

describe('approvalSummary', () => {
  it('shows current approvals only when both version and hash match', () => {
    const result = approvalSummary(brief({ approvals: [approval({ role: 'designer' })] }), state({ approvals: [approval(), approval({ role: 'designer', contentHash: 'wrong' }), approval({ role: 'designer', briefVersion: 2 })] })).join();
    for (const text of ['屋主已批准', '2026-09-20T10:00:00Z', '设计师尚未批准']) expect(result).toContain(text);
  });
  it('invalidates all approvals for a stale latest version', () => {
    const result = approvalSummary(brief(), state({ briefStale: true, approvals: [approval()] })).join();
    expect(result).toContain('方案已过时，原审批不再有效，请返回工作区重新生成');
    expect(result).not.toContain('屋主已批准');
  });
  it('explicitly marks missing historical records unavailable, including wrong hash matches', () => {
    const result = approvalSummary(brief(), state({ briefVersions: [{ ...brief(), version: 2 }, brief()], approvals: [approval({ contentHash: 'wrong' })] })).join();
    expect(result).toContain('历史审批记录不可用，无法据此判断当时是否批准');
    expect(result).not.toContain('尚未批准');
  });
  it('labels matching historical records without inferring missing roles or invalidating history', () => {
    const result = approvalSummary(brief(), state({ briefStale: true, briefVersions: [brief(), { ...brief(), version: 2 }], approvals: [approval()] })).join();
    for (const text of ['现存审批记录', '屋主', '2026-09-20T10:00:00Z']) expect(result).toContain(text);
    expect(result).toContain('设计师历史审批记录不可用');
    expect(result).not.toContain('尚未批准');
    expect(result).not.toContain('方案已过时');
  });
});
