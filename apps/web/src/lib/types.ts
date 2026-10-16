// Shared types mirroring the FastAPI response schemas (apps/api/app/schemas).

export type MeetingStatus =
  | "uploading"
  | "transcribing"
  | "summarizing"
  | "processing"
  | "completed"
  | "failed";

export type TaskStatus =
  | "todo"
  | "in_progress"
  | "review"
  | "done"
  | "blocked"
  | "cancelled";

export type TaskPriority = "low" | "medium" | "high" | "urgent";

export type DecisionImpact = "low" | "medium" | "high";

export interface User {
  id: string;
  email: string;
  name: string;
  image: string | null;
  role: string;
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
}

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  slug: string;
  owner_id: string;
  is_active: boolean;
  created_at: string;
}

export interface Member {
  membership_id: string;
  user_id: string;
  name: string;
  email: string;
  image: string | null;
  role: string;
  is_owner: boolean;
  accepted_at: string | null;
  invited_at: string;
}

export interface Decision {
  id: string;
  meeting_id: string;
  title: string;
  description: string | null;
  impact: DecisionImpact;
  rationale: string | null;
  sequence: number;
}

export interface TranscriptSegment {
  id: string;
  sequence: number;
  start_time: number | null;
  end_time: number | null;
  speaker: string | null;
  text: string;
  confidence: number | null;
}

export interface Transcript {
  id: string;
  meeting_id: string;
  engine: string | null;
  model: string | null;
  full_text: string | null;
  language: string | null;
  detected_language: string | null;
  duration_seconds: number | null;
  completed_at: string | null;
  created_at: string;
  segments: TranscriptSegment[];
}

export interface Meeting {
  id: string;
  workspace_id: string;
  title: string;
  description: string | null;
  status: MeetingStatus;
  audio_file_name: string | null;
  audio_duration_seconds: number | null;
  meeting_date: string | null;
  meeting_type: string | null;
  participants: string[] | null;
  consent_confirmed: boolean;
  summary: string | null;
  key_points: string[] | null;
  risks: string[] | null;
  unanswered_questions: string[] | null;
  next_steps: string[] | null;
  error_message: string | null;
  language: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface MeetingWithDetails extends Meeting {
  decisions: Decision[];
  transcript: Transcript | null;
}

export interface MeetingSummary {
  summary: string | null;
  key_points: string[];
  risks: string[];
  unanswered_questions: string[];
  next_steps: string[];
  decisions: Decision[];
}

export interface Task {
  id: string;
  workspace_id: string;
  project_id: string | null;
  meeting_id: string | null;
  decision_id: string | null;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  assignee_id: string | null;
  reporter_id: string | null;
  due_date: string | null;
  start_date: string | null;
  completed_at: string | null;
  estimated_hours: number | null;
  actual_hours: number | null;
  tags: string[] | null;
  sequence: number;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Dev Studio (Phase 3)
// ---------------------------------------------------------------------------

export interface StudioFileNode {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number | null;
  language?: string | null;
  editable?: boolean | null;
  children?: StudioFileNode[] | null;
}

export interface StudioTree {
  name: string;
  path: string;
  type: "file" | "dir";
  children: StudioFileNode[];
  empty: boolean;
  count: number;
  truncated: boolean;
}

export interface StudioFile {
  path: string;
  name: string;
  language: string;
  content: string;
  size: number;
  editable: boolean;
  hash: string;
  updated_at: string | null;
}

export type ProposalStatus = "pending" | "approved" | "rejected";

export interface CodeProposal {
  id: string;
  workspace_id: string;
  file_path: string;
  language: string | null;
  original_content: string | null;
  proposed_content: string;
  rationale: string | null;
  source: string; // "llm" | "fallback"
  status: ProposalStatus;
  base_hash: string | null;
  added_lines: number;
  removed_lines: number;
  meeting_id: string | null;
  task_id: string | null;
  created_by: string | null;
  decided_by: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface ProposalDecision {
  proposal: CodeProposal;
  applied: boolean;
  message: string;
}

export interface ChatSuggestion {
  action: string;
  label: string;
  file_path: string | null;
  instruction: string | null;
}

export interface StudioChatResponse {
  answer: string;
  source: string; // "llm" | "fallback"
  suggestions: ChatSuggestion[];
  context_used: Record<string, unknown>;
  fallback_reason: string | null;
}

export interface LintFinding {
  line: number;
  severity: string;
  message: string;
  snippet: string;
}

export interface LintResult {
  path: string;
  language: string;
  findings: LintFinding[];
}

export interface SeedResult {
  created: string[];
  skipped: number;
}

// ---------------------------------------------------------------------------
// Ship it (Phase 4): repositories, git, pull-request proposals, the agent
// ---------------------------------------------------------------------------

export type RepoProvider = "local" | "github";

export type PullRequestStatus = "draft" | "open" | "merged" | "closed" | "failed";

export type PlanStatus = "draft" | "applied";

export interface RepoConnection {
  id: string;
  workspace_id: string;
  provider: RepoProvider;
  name: string;
  repo_full_name: string | null;
  default_branch: string;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepoCheck {
  repo_id: string;
  provider: RepoProvider;
  ok: boolean;
  message: string;
  detail: Record<string, unknown>;
}

export interface GitChangedFile {
  path: string;
  status: string;
}

export interface GitStatus {
  available: boolean;
  initialized: boolean;
  branch: string | null;
  branches: string[];
  clean: boolean;
  changed_files: GitChangedFile[];
  commit_count: number;
}

export interface GitCommit {
  sha: string;
  author_name: string;
  author_email: string;
  date: string;
  message: string;
}

export interface GitDiff {
  branch: string | null;
  diff: string;
  changed_files: GitChangedFile[];
  truncated: boolean;
}

export interface PullRequestFile {
  path: string;
  status: string;
  deleted: boolean;
  added_lines: number;
  removed_lines: number;
}

export interface PullRequest {
  id: string;
  workspace_id: string;
  repo_id: string | null;
  provider: RepoProvider;
  title: string;
  body: string | null;
  branch_name: string;
  base_branch: string;
  status: PullRequestStatus;
  changed_files: PullRequestFile[];
  skipped_files: string[];
  diff: string | null;
  file_count: number;
  added_lines: number;
  removed_lines: number;
  commit_sha: string | null;
  external_number: number | null;
  external_url: string | null;
  error: string | null;
  meeting_id: string | null;
  task_id: string | null;
  created_by: string | null;
  decided_by: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface PullRequestDecision {
  proposal: PullRequest;
  message: string;
}

export interface PlanSubtask {
  title: string;
  kind: string; // "code" | "test" | "docs" | "review"
  files: string[];
}

export interface PlanFile {
  path: string;
  reason: string;
  score: number;
}

export interface PlanChange {
  path: string;
  instruction: string;
}

export interface CodePlan {
  id: string;
  workspace_id: string;
  title: string;
  summary: string | null;
  focus: string | null;
  meeting_id: string | null;
  decision_id: string | null;
  task_id: string | null;
  requirements: string[];
  subtasks: PlanSubtask[];
  affected_files: PlanFile[];
  proposed_changes: PlanChange[];
  source: string; // "llm" | "fallback"
  status: PlanStatus;
  proposal_ids: string[];
  created_by: string | null;
  created_at: string;
}

export interface PlanApply {
  plan: CodePlan;
  created: number;
  proposal_ids: string[];
  skipped: string[];
  message: string;
}
