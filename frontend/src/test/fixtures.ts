import type { ProjectSnapshot } from '../types';

export const BRIEF_HASH = 'a'.repeat(64);

export function conflictSnapshot(role: 'homeowner' | 'designer' = 'homeowner'): ProjectSnapshot {
  const base = snapshot(role);
  return {
    ...base,
    project: { ...base.project, status: 'alignment', stateVersion: 6 },
    pendingQuestion: null,
    projectState: {
      ...base.projectState,
      stateVersion: 6,
      status: 'alignment',
      waitReason: null,
      currentNode: 'alignment',
      completeness: 0.75,
      constraints: [
        {
          id: 'budget-stone',
          category: 'budget',
          statement: '天然石材超出预算',
          severity: 'important',
          verificationStatus: 'designer_asserted',
          owner: 'designer',
        },
      ],
      conflicts: [
        {
          id: 'finish-budget-conflict',
          type: 'preference_vs_constraint',
          summary: '天然石材与预算冲突',
          impact: '需要选择低成本替代方案',
          status: 'open',
          severity: 'important',
          resolutionAttempts: 0,
        },
      ],
    },
  };
}

export function briefSnapshot(role: 'homeowner' | 'designer' = 'homeowner'): ProjectSnapshot {
  const base = snapshot(role);
  return {
    ...base,
    project: { ...base.project, status: 'awaiting_approval', stateVersion: 8 },
    pendingQuestion: null,
    projectState: {
      ...base.projectState,
      stateVersion: 8,
      status: 'awaiting_approval',
      waitReason: null,
      currentNode: 'awaiting_approval',
      completeness: 0.875,
      briefVersions: [
        {
          version: 1,
          contentHash: BRIEF_HASH,
          completeness: 0.875,
          payload: {
            version: 1,
            completeness: 0.875,
            goals: ['warm modern'],
            project: { id: 'p1', status: 'awaiting_approval' },
          },
        },
      ],
      approvals:
        role === 'designer'
          ? [
              {
                role: 'homeowner',
                actorId: 'homeowner-1',
                briefVersion: 1,
                contentHash: BRIEF_HASH,
                approvedAt: '2026-09-12T00:00:00Z',
              },
            ]
          : [],
    },
  };
}

export function snapshot(role: 'homeowner' | 'designer' = 'homeowner'): ProjectSnapshot {
  return {
    project: { id: 'p1', role, roomType: 'living_room', budgetBand: '15k_to_30k_sgd', consent: true, status: 'homeowner_review', stateVersion: 4, designerJoined: true, assets: [
        {
          id: 'a1',
          originalFilename: 'living-room.png',
          mediaType: 'image/png',
          sizeBytes: 1024,
          sha256: 'b'.repeat(64),
          deleted: false,
          deletedAt: null,
        },
      ] },
    pendingQuestion: { id: 'question-liked-elements', targetRole: 'homeowner', text: 'Which elements?', rationale: 'Discover liked elements.', options: [], answer: null, repetitionFingerprint: 'liked-elements' },
    projectState: {
      projectId: 'p1', stateVersion: 4, status: 'homeowner_review', currentNode: 'wait_homeowner', waitReason: 'homeowner', completeness: 0,
      attributes: [{ id: 'mock-lighting-lighting', targetElement: 'lighting', dimension: 'lighting', value: 'warm ambient', status: 'proposed', confidence: 0.84, actor: 'vision_agent', evidence: [{ sourceType: 'image', sourceId: 'a1', description: 'Mock image observation: lighting lighting' }] }],
      constraints: [], conflicts: [], questions: [], briefVersions: [], approvals: [],
    },
  };
}
