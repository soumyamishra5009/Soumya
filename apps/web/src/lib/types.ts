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
