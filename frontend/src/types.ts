export type Role = 'homeowner' | 'designer';

export type User = {
  id: string;
  email: string;
  emailVerified: false;
};

export type AuthResponse = {
  accessToken: string;
  user: User;
};

export type Asset = {
  id: string;
  originalFilename: string;
  mediaType: string;
  sizeBytes: number;
  sha256: string;
  deleted: boolean;
  deletedAt: number | null;
};

export type Project = {
  id: string;
  roomType: string;
  budgetBand: string;
  consent: boolean;
  status: string;
  stateVersion: number;
  assets: Asset[];
  role: Role;
  designerJoined: boolean;
};

export type AttributeStatus =
  | 'proposed'
  | 'confirmed'
  | 'rejected'
  | 'conflicted'
  | 'unresolved'
  | 'not_applicable';

export type Evidence = {
  sourceType: string;
  sourceId: string;
  description: string;
};

export type Attribute = {
  id: string;
  targetElement: string;
  dimension: string;
  value: string;
  status: AttributeStatus;
  confidence: number;
  actor: string;
  evidence: Evidence[];
};

export type Constraint = {
  id: string;
  category: string;
  statement: string;
  rationale?: string;
  severity: string;
  verificationStatus: string;
  owner: string;
  appliesTo?: string;
  attributeId?: string | null;
  proposedBy?: string;
  withdrawn?: boolean;
  revision?: number;
  incompatibleWith?: string[];
};

export type Conflict = {
  id: string;
  type: string;
  summary: string;
  impact: string;
  status: string;
  resolution?: string | null;
  severity: string;
  resolutionAttempts: number;
  constraintId?: string | null;
};

export type Question = {
  id: string;
  targetRole: Role;
  text: string;
  rationale: string;
  options: string[];
  answer: string | null;
  repetitionFingerprint: string;
};

export type Approval = {
  role: Role;
  actorId: string;
  briefVersion: number;
  contentHash: string;
  approvedAt: string;
};

export type BriefVersion = {
  version: number;
  contentHash: string;
  payload: Record<string, unknown>;
  completeness: number;
};

export type ProjectState = {
  projectId: string;
  stateVersion: number;
  status: string;
  attributes: Attribute[];
  constraints: Constraint[];
  questions: Question[];
  conflicts: Conflict[];
  briefVersions: BriefVersion[];
  approvals: Approval[];
  completeness: number;
  currentNode: string | null;
  waitReason: string | null;
  briefStale?: boolean;
};

export type ProjectSnapshot = {
  project: Project;
  projectState: ProjectState;
  pendingQuestion: Question | null;
};

export type JoinCode = {
  code: string;
  expiresAt: number;
};

export type WriteEnvelope<T> = {
  expectedStateVersion: number;
  idempotencyKey: string;
  data: T;
};
