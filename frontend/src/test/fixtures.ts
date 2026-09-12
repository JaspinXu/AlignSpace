import type { ProjectSnapshot } from '../types';

export function snapshot(role: 'homeowner' | 'designer' = 'homeowner'): ProjectSnapshot {
  return {
    project: { id: 'p1', role, roomType: 'living_room', budgetBand: '15k_to_30k_sgd', consent: true, status: 'homeowner_review', stateVersion: 4, designerJoined: true, assets: [{ id: 'a1', fixtureId: 'living-room-1', mediaType: 'image/jpeg', sizeBytes: 1024 }] },
    pendingQuestion: { id: 'question-liked-elements', targetRole: 'homeowner', text: 'Which elements?', rationale: 'Discover liked elements.', options: [], answer: null, repetitionFingerprint: 'liked-elements' },
    projectState: {
      projectId: 'p1', stateVersion: 4, status: 'homeowner_review', currentNode: 'wait_homeowner', waitReason: 'homeowner', completeness: 0,
      attributes: [{ id: 'mock-lighting-lighting', targetElement: 'lighting', dimension: 'lighting', value: 'warm ambient', status: 'proposed', confidence: 0.84, actor: 'vision_agent', evidence: [{ sourceType: 'image', sourceId: 'living-room-1', description: 'Mock image observation: lighting lighting' }] }],
      constraints: [], conflicts: [], questions: [], briefVersions: [], approvals: [],
    },
  };
}
