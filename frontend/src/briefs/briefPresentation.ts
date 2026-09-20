import type { BriefVersion, ProjectState } from '../types';

export type BriefPresentation = {
  projectId: string;
  goals: string[] | null;
  sections: { title: string; items: string[] | null }[];
};

type RecordValue = Record<string, unknown>;
type Labels = Record<string, string>;
const missing = '未记录';
const attributeStatuses: Labels = {
  proposed: '待确认', confirmed: '已确认', rejected: '已拒绝',
  conflicted: '有冲突', unresolved: '未决', not_applicable: '不适用',
};
const dimensions: Labels = {
  style: '风格', colour: '颜色', material: '材料', lighting: '照明', layout: '布局',
  furniture: '家具', mood: '氛围', function: '功能', maintenance: '维护', other: '其他',
};
const sources: Labels = { image: '图片', homeowner_answer: '屋主回答', designer_note: '设计师备注', system_rule: '系统规则' };
const categories: Labels = {
  budget: '预算', space: '空间', function: '功能', maintenance: '维护', timeline: '工期',
  safety: '安全', regulatory: '法规', availability: '供应情况', other: '其他',
};
const severities: Labels = { advisory: '建议', important: '重要', critical: '严重' };
const verifications: Labels = {
  unverified: '未核验', designer_asserted: '设计师声明',
  professional_review_required: '需要专业核验', verified: '已核验',
};
const roles: Labels = { homeowner: '屋主', designer: '设计师', qualified_professional: '专业人员' };
const conflictStatuses: Labels = { open: '待解决', resolved: '已解决', escalated: '已升级处理', accepted_unresolved: '接受未解决' };
const projectStatuses: Labels = {
  draft: '草稿', analysing: '分析中', homeowner_review: '屋主审阅中', designer_review: '设计师审阅中',
  alignment: '协调中', awaiting_approval: '等待审批', approved: '已批准', archived: '已归档',
};

function malformed(path: string): never {
  throw new Error(`说明书格式错误：${path}，无法读取此版本。`);
}

function record(value: unknown, path: string): RecordValue {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) malformed(path);
  return value as RecordValue;
}

function text(value: unknown, path: string): string {
  if (value == null) return missing;
  if (typeof value !== 'string') malformed(path);
  return value || missing;
}

function label(value: unknown, labels: Labels, path: string): string {
  const raw = text(value, path);
  if (raw === missing) return raw;
  return Object.prototype.hasOwnProperty.call(labels, raw) ? labels[raw] : `未知（${raw}）`;
}

function list<T>(value: unknown, path: string, convert: (item: unknown, path: string) => T): T[] | null {
  if (value == null) return null;
  if (!Array.isArray(value)) malformed(path);
  return value.map((item, index) => convert(item, `${path}[${index}]`));
}

function strings(value: unknown, path: string): string[] | null {
  return list(value, path, (item, itemPath) => {
    if (typeof item !== 'string') malformed(itemPath);
    return item;
  });
}

// Read only named snapshot fields. In particular, template project metadata is not trustworthy.
export function presentBrief(brief: BriefVersion, projectId: string): BriefPresentation {
  const payload = record(brief.payload, '正文');
  if (!Number.isSafeInteger(brief.version) || brief.version < 1 ||
      (payload.version != null && payload.version !== brief.version)) {
    throw new Error('说明书版本错误：快照版本与所选版本不一致。');
  }
  const sections: BriefPresentation['sections'] = [];
  if (payload.project != null) {
    const project = record(payload.project, '项目');
    if (project.id != null && project.id !== projectId) {
      throw new Error('说明书项目不匹配：快照不属于当前项目。');
    }
    sections.push({ title: '项目概况', items: [
      `项目 ID：${projectId}`,
      `生成时状态：${label(project.status, projectStatuses, '项目状态')}`,
    ] });
  }
  sections.push({ title: '偏好与来源', items: list(payload.attributes, '偏好', (item, path) => {
    const attribute = record(item, path);
    const evidence = list(attribute.evidence, `${path}.evidence`, (entry, evidencePath) => {
      const saved = record(entry, evidencePath);
      return `类型：${label(saved.sourceType, sources, `${evidencePath}.sourceType`)}；来源 ID：${text(saved.sourceId, `${evidencePath}.sourceId`)}；说明：${text(saved.description, `${evidencePath}.description`)}`;
    });
    return [
      `部位：${text(attribute.targetElement, `${path}.targetElement`)}`,
      `维度：${label(attribute.dimension, dimensions, `${path}.dimension`)}`,
      `取值：${text(attribute.value, `${path}.value`)}`,
      `状态：${label(attribute.status, attributeStatuses, `${path}.status`)}`,
      `证据：${evidence === null ? missing : evidence.length === 0 ? '此版本未记录相关内容' : evidence.join(' / ')}`,
    ].join('；');
  }) });
  sections.push({ title: '设计师约束', items: list(payload.constraints, '约束', (item, path) => {
    const constraint = record(item, path);
    return [
      `类别：${label(constraint.category, categories, `${path}.category`)}`,
      `作用对象：${text(constraint.appliesTo, `${path}.appliesTo`)}`,
      `内容：${text(constraint.statement, `${path}.statement`)}`,
      `理由：${text(constraint.rationale, `${path}.rationale`)}`,
      `严重程度：${label(constraint.severity, severities, `${path}.severity`)}`,
      `专业核验：${label(constraint.verificationStatus, verifications, `${path}.verificationStatus`)}`,
      `负责人：${label(constraint.owner, roles, `${path}.owner`)}`,
      `关联偏好 ID：${text(constraint.attributeId, `${path}.attributeId`)}`,
      `提出者：${text(constraint.proposedBy, `${path}.proposedBy`)}`,
    ].join('；');
  }) });
  sections.push({ title: '冲突', items: list(payload.conflicts, '冲突', (item, path) => {
    const conflict = record(item, path);
    return [
      `状态：${label(conflict.status, conflictStatuses, `${path}.status`)}`,
      `摘要：${text(conflict.summary, `${path}.summary`)}`,
      `影响：${text(conflict.impact, `${path}.impact`)}`,
      `结论：${text(conflict.resolution, `${path}.resolution`)}`,
      `严重程度：${label(conflict.severity, severities, `${path}.severity`)}`,
    ].join('；');
  }) });
  sections.push({ title: '未决事项', items: strings(payload.unresolvedDecisions, '未决事项') });
  return { projectId, goals: strings(payload.goals, '设计目标'), sections };
}

export function approvalSummary(brief: BriefVersion, state: ProjectState): string[] {
  const latestVersion = state.briefVersions.reduce((latest, item) => Math.max(latest, item.version), 0);
  const isLatest = brief.version === latestVersion;
  if (isLatest && state.briefStale) {
    return ['方案已过时，原审批不再有效，请返回工作区重新生成'];
  }
  // Snapshot approvals and generation status cannot establish a current approval.
  const matching = state.approvals.filter(approval =>
    approval.briefVersion === brief.version && approval.contentHash === brief.contentHash);
  if (!isLatest && matching.length === 0) {
    return ['历史审批记录不可用，无法据此判断当时是否批准'];
  }
  return (['homeowner', 'designer'] as const).flatMap(role => {
    const records = matching.filter(approval => approval.role === role);
    if (records.length === 0) {
      return [isLatest ? `${roles[role]}尚未批准` : `${roles[role]}历史审批记录不可用，无法据此判断当时是否批准`];
    }
    return records.map(approval =>
      `${isLatest ? '' : '现存审批记录：'}${roles[role]}已批准；时间：${approval.approvedAt}；审批人 ID：${approval.actorId}`);
  });
}
