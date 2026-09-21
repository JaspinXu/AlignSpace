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

export type QuestionOption = {
  label: string;
  value?: string | null;
  assetId?: string | null;
  targetElement?: string | null;
  dimension?: string | null;
  attributeId?: string | null;
};

export type Question = {
  id: string;
  targetRole: Role;
  text: string;
  rationale: string;
  options: QuestionOption[];
  answer: string | null;
  repetitionFingerprint: string;
  kind?: 'broad_parts' | 'detail' | 'conflict';
  assetId?: string | null;
  targetElement?: string | null;
  dimension?: string | null;
  skipped?: boolean;
  response?: unknown;
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

export type CandidateDimension =
  | 'colour'
  | 'material'
  | 'style'
  | 'laying'
  | 'lighting'
  | 'other';

export type CandidateCertainty = 'inferred' | 'uncertain';

export type CandidateStatus = 'proposed' | 'confirmed' | 'rejected' | 'dismissed';

export type EntryStatus =
  | 'open'
  | 'partially_confirmed'
  | 'confirmed'
  | 'dismissed'
  | 'source_deleted';

/** A model proposal. It is not a preference until the homeowner confirms it. */
export type Candidate = {
  id: string;
  entryId: string;
  dimension: CandidateDimension;
  certainty: CandidateCertainty;
  proposedValue: string | null;
  confirmedValue: string | null;
  status: CandidateStatus;
  attributeId: string | null;
  humanEdited: boolean;
  evidence: Evidence[];
};

export type DesignEntry = {
  id: string;
  analysisRunId: string;
  sourceAssetId: string | null;
  sourceAvailable: boolean;
  targetElement: string;
  attentionDimensions: CandidateDimension[];
  note: string;
  status: EntryStatus;
  candidates: Candidate[];
};

export type AnalysisRun = {
  id: string;
  status: string;
  description: string;
  providerMode: string;
  model: string;
  promptVersion: string;
  schemaVersion: string;
  thirdPartyConsent: boolean;
  inputAssets: { assetId: string; sha256: string }[];
  inputFingerprint: string;
  stale: boolean;
  error: string | null;
  entries: DesignEntry[];
};

export type CandidateBoard = {
  stateVersion: number;
  runs: AnalysisRun[];
};

export type SpacePoint = { x: number; y: number };

export type SpaceWall = {
  id: string;
  start: SpacePoint;
  end: SpacePoint;
  thickness: number;
};

export type SpaceFloor = {
  id: string;
  materialOptionId: string | null;
  bindingId: string | null;
};

export type SpaceRoom = {
  id: string;
  name: string;
  roomType: string;
  origin: SpacePoint;
  size: { width: number; depth: number };
  walls: SpaceWall[];
  floor: SpaceFloor;
};

export type SpaceObject = {
  id: string;
  roomId: string;
  kind: string;
  label: string;
  geometry: Record<string, unknown>;
};

export type SpacePlan = {
  schemaVersion: string;
  units: string;
  rooms: SpaceRoom[];
  objects: SpaceObject[];
};

export type SpaceSnapshot = {
  projectId: string;
  stateVersion: number;
  version: number | null;
  contentHash: string | null;
  source: string | null;
  previousVersion: number | null;
  createdBy: string | null;
  createdRole: Role | null;
  createdAt: string | null;
  plan: SpacePlan | null;
};

export type SpaceVersionSummary = {
  version: number;
  contentHash: string;
  source: string;
  previousVersion: number | null;
  createdBy: string;
  createdRole: Role;
  createdAt: string;
};

export type SpaceVersionList = {
  projectId: string;
  stateVersion: number;
  versions: SpaceVersionSummary[];
};

export type MaterialOption = {
  id: string;
  label: string;
  targets: string[];
  colours: string[];
  patterns: string[];
};

export type MaterialCatalogue = { options: MaterialOption[] };

export type Approximation = 'exact' | 'approximate';

export type BindingStatus = 'active' | 'needs_review' | 'invalidated';

export type SpaceBinding = {
  id: string;
  roomId: string;
  floorObjectId: string | null;
  target: 'floor';
  attributeId: string | null;
  candidateId: string | null;
  materialOptionId: string;
  approximation: Approximation;
  note: string;
  status: BindingStatus;
  boundBy: string;
  boundAt: string;
  spaceVersion: number;
  appliedSpaceVersion: number | null;
};

export type SpaceBindingList = {
  projectId: string;
  stateVersion: number;
  bindings: SpaceBinding[];
  floorPreferences: FloorPreference[];
};

export type FloorPreference = {
  attributeId: string;
  value: string;
  dimension: string;
};

export type JointApproval = {
  role: Role;
  actorId: string;
  briefVersion: number;
  briefHash: string;
  spaceVersion: number;
  spaceHash: string;
  approvedAt: string;
};

export type SpaceApprovalView = {
  projectId: string;
  stateVersion: number;
  briefVersion: number | null;
  briefHash: string | null;
  spaceVersion: number | null;
  spaceHash: string | null;
  approvals: JointApproval[];
  approved: boolean;
};
