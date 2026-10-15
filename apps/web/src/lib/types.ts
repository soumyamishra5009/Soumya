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
