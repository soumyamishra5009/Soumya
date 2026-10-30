// Typed client for the SyncForge FastAPI backend.
//
// Auth uses a bearer JWT issued by /api/v1/auth/*. The token is kept in
// localStorage so the app stays stateless (no server session needed for MVP).

import type {
  CodePlan,
  CodeProposal,
  Decision,
  DemoSeedResult,
  GitCommit,
  GitDiff,
  GitStatus,
  LintResult,
  Member,
  Meeting,
  MeetingSummary,
  MeetingWithDetails,
  MemoryHit,
  MemoryIndexResult,
  MemorySearchResult,
  MemoryStats,
  PlanApply,
  ProposalDecision,
  PullRequest,
  PullRequestDecision,
  RepoCheck,
  RepoConnection,
  SeedResult,
  StudioChatResponse,
  StudioFile,
  StudioTree,
  SystemStatus,
  Task,
  TaskPriority,
  TaskStatus,
  TestRun,
  TestRunRequest,
  TokenResponse,
  Transcript,
  User,
  Workspace,
} from "./types";

// Base URL for every API call.
//
// - Dev: `NEXT_PUBLIC_API_URL=http://localhost:8000` (see apps/web/.env.local).
// - Split deploy: set `NEXT_PUBLIC_API_URL` to the backend origin.
// - Single deploy (Vercel `services` + rewrites, i.e. production today): leave
//   it unset so requests stay same-origin and inherit whatever domain the
//   deployment gets. That avoids baking a preview URL into the bundle.
const CONFIGURED_API_URL = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "");

export const API_URL =
  CONFIGURED_API_URL || (typeof window === "undefined" ? "http://localhost:8000" : "");

const TOKEN_KEY = "syncforge_token";
const WORKSPACE_KEY = "syncforge_workspace";

export const tokenStore = {
  get(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
  },
  set(token: string) {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(TOKEN_KEY);
  },
};

export const workspaceStore = {
  get(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(WORKSPACE_KEY);
  },
  set(id: string) {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(WORKSPACE_KEY, id);
  },
  clear() {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(WORKSPACE_KEY);
  },
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { auth?: boolean; raw?: boolean } = {}
): Promise<T> {
  const { auth = true, raw = false, ...init } = options;
  const headers = new Headers(init.headers);

  if (!raw && !headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = tokenStore.get();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Is the backend running?");
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    const detail = (body as { detail?: unknown })?.detail;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) {
      message = detail
        .map((d) => (d as { msg?: string })?.msg ?? JSON.stringify(d))
        .join(", ");
    } else if (typeof body === "string" && body.trim()) {
      message = body;
    }
    if (res.status === 401 && auth) {
      tokenStore.clear();
    }
    throw new ApiError(res.status, message);
  }

  return body as T;
}

export const api = {
  // ---- auth ----
  register(email: string, password: string, name: string) {
    return request<TokenResponse>("/api/v1/auth/register", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ email, password, name }),
    });
  },
  login(email: string, password: string) {
    return request<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ email, password }),
    });
  },
  me() {
    return request<User>("/api/v1/auth/me");
  },

  // ---- workspaces ----
  listWorkspaces() {
    return request<Workspace[]>("/api/v1/workspaces");
  },
  createWorkspace(name: string, description?: string) {
    return request<Workspace>("/api/v1/workspaces", {
      method: "POST",
      body: JSON.stringify({ name, description: description ?? null }),
    });
  },

  // ---- members ----
  listMembers(workspaceId: string) {
    return request<Member[]>(`/api/v1/workspaces/${workspaceId}/members`);
  },
  addMember(workspaceId: string, email: string, role = "member") {
    return request<Member>(`/api/v1/workspaces/${workspaceId}/members`, {
      method: "POST",
      body: JSON.stringify({ email, role }),
    });
  },
  removeMember(workspaceId: string, userId: string) {
    return request<void>(`/api/v1/workspaces/${workspaceId}/members/${userId}`, {
      method: "DELETE",
    });
  },

  // ---- meetings ----
  listMeetings(
    workspaceId: string,
    filters: { q?: string; archived?: boolean; status?: string } = {}
  ) {
    const params = new URLSearchParams();
    if (filters.q) params.set("q", filters.q);
    if (filters.archived !== undefined) params.set("archived", String(filters.archived));
    if (filters.status) params.set("meeting_status", filters.status);
    const qs = params.toString();
    return request<Meeting[]>(
      `/api/v1/workspaces/${workspaceId}/meetings${qs ? `?${qs}` : ""}`
    );
  },
  createMeeting(input: {
    workspace_id: string;
    title: string;
    description?: string | null;
    meeting_date?: string | null;
    participants?: string[] | null;
    consent_confirmed?: boolean;
  }) {
    return request<Meeting>("/api/v1/meetings", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  getMeeting(meetingId: string) {
    return request<MeetingWithDetails>(`/api/v1/meetings/${meetingId}`);
  },
  getMeetingSummary(meetingId: string) {
    return request<MeetingSummary>(`/api/v1/meetings/${meetingId}/summary`);
  },
  // Human-in-the-loop: edit meeting metadata and/or the AI output.
  updateMeeting(
    meetingId: string,
    patch: Partial<{
      title: string;
      description: string | null;
      summary: string | null;
      key_points: string[];
      risks: string[];
      unanswered_questions: string[];
      next_steps: string[];
      archived: boolean;
    }>
  ) {
    return request<Meeting>(`/api/v1/meetings/${meetingId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },
  createDecision(
    meetingId: string,
    input: { title: string; description?: string | null; impact?: string; rationale?: string | null }
  ) {
    return request<Decision>(`/api/v1/meetings/${meetingId}/decisions`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  updateDecision(
    decisionId: string,
    patch: Partial<{
      title: string;
      description: string | null;
      impact: string;
      rationale: string | null;
      sequence: number;
    }>
  ) {
    return request<Decision>(`/api/v1/decisions/${decisionId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },
  deleteDecision(decisionId: string) {
    return request<void>(`/api/v1/decisions/${decisionId}`, { method: "DELETE" });
  },
  listMeetingTasks(meetingId: string) {
    return request<Task[]>(`/api/v1/meetings/${meetingId}/tasks`);
  },
  processMeeting(meetingId: string) {
    return request<Meeting>(`/api/v1/meetings/${meetingId}/process`, {
      method: "POST",
    });
  },
  async uploadAudio(meetingId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return request<Meeting>(`/api/v1/meetings/${meetingId}/audio`, {
      method: "POST",
      raw: true,
      body: form,
    });
  },
  // <audio> cannot send an Authorization header, so the token is passed as a
  // query parameter (the backend accepts both).
  audioUrl(meetingId: string) {
    const token = tokenStore.get();
    const suffix = token ? `?token=${encodeURIComponent(token)}` : "";
    return `${API_URL}/api/v1/meetings/${meetingId}/audio${suffix}`;
  },

  // ---- tasks ----
  listTasks(
    workspaceId: string,
    filters: {
      status?: TaskStatus;
      assignee?: string; // user id, or "me" / "unassigned"
      priority?: TaskPriority;
      q?: string;
      meetingId?: string;
      dueBefore?: string;
      dueAfter?: string;
    } = {}
  ) {
    const params = new URLSearchParams();
    if (filters.status) params.set("task_status", filters.status);
    if (filters.assignee) params.set("assignee_id", filters.assignee);
    if (filters.priority) params.set("priority", filters.priority);
    if (filters.q) params.set("q", filters.q);
    if (filters.meetingId) params.set("meeting_id", filters.meetingId);
    if (filters.dueBefore) params.set("due_before", filters.dueBefore);
    if (filters.dueAfter) params.set("due_after", filters.dueAfter);
    const qs = params.toString();
    return request<Task[]>(`/api/v1/workspaces/${workspaceId}/tasks${qs ? `?${qs}` : ""}`);
  },
  createTask(input: {
    workspace_id: string;
    title: string;
    description?: string | null;
    status?: TaskStatus;
    priority?: TaskPriority;
    assignee_id?: string | null;
    meeting_id?: string | null;
    due_date?: string | null;
  }) {
    return request<Task>("/api/v1/tasks", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  updateTask(
    taskId: string,
    patch: Partial<{
      title: string;
      description: string | null;
      status: TaskStatus;
      priority: TaskPriority;
      assignee_id: string | null;
      due_date: string | null;
      estimated_hours: number | null;
      actual_hours: number | null;
      sequence: number;
    }>
  ) {
    return request<Task>(`/api/v1/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  // ---- dev studio ----
  studioTree(workspaceId: string) {
    return request<StudioTree>(`/api/v1/workspaces/${workspaceId}/studio/tree`);
  },
  studioSeed(workspaceId: string) {
    return request<SeedResult>(`/api/v1/workspaces/${workspaceId}/studio/seed`, {
      method: "POST",
    });
  },
  studioFile(workspaceId: string, path: string) {
    return request<StudioFile>(
      `/api/v1/workspaces/${workspaceId}/studio/files/${encodeStudioPath(path)}`
    );
  },
  studioSaveFile(workspaceId: string, path: string, content: string) {
    return request<StudioFile>(
      `/api/v1/workspaces/${workspaceId}/studio/files/${encodeStudioPath(path)}`,
      { method: "PUT", body: JSON.stringify({ content }) }
    );
  },
  studioCreateEntry(
    workspaceId: string,
    input: { path: string; kind: "file" | "dir"; content?: string }
  ) {
    return request<{ path: string; type: string }>(
      `/api/v1/workspaces/${workspaceId}/studio/files`,
      { method: "POST", body: JSON.stringify(input) }
    );
  },
  studioDeleteEntry(workspaceId: string, path: string) {
    return request<{ path: string; deleted: boolean }>(
      `/api/v1/workspaces/${workspaceId}/studio/files/${encodeStudioPath(path)}`,
      { method: "DELETE" }
    );
  },
  studioLint(workspaceId: string, path: string, content: string) {
    const qs = new URLSearchParams({ path }).toString();
    return request<LintResult>(
      `/api/v1/workspaces/${workspaceId}/studio/lint?${qs}`,
      { method: "POST", body: JSON.stringify({ content }) }
    );
  },
  studioChat(
    workspaceId: string,
    input: {
      message: string;
      file_path?: string | null;
      meeting_id?: string | null;
      task_id?: string | null;
      history?: { role: "user" | "assistant"; content: string }[];
    }
  ) {
    return request<StudioChatResponse>(
      `/api/v1/workspaces/${workspaceId}/studio/chat`,
      { method: "POST", body: JSON.stringify(input) }
    );
  },
  studioProposals(workspaceId: string, status?: string) {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<CodeProposal[]>(
      `/api/v1/workspaces/${workspaceId}/studio/proposals${qs}`
    );
  },
  studioCreateProposal(
    workspaceId: string,
    input: {
      file_path: string;
      instruction: string;
      meeting_id?: string | null;
      task_id?: string | null;
    }
  ) {
    return request<CodeProposal>(
      `/api/v1/workspaces/${workspaceId}/studio/proposals`,
      { method: "POST", body: JSON.stringify(input) }
    );
  },
  studioApproveProposal(workspaceId: string, proposalId: string) {
    return request<ProposalDecision>(
      `/api/v1/workspaces/${workspaceId}/studio/proposals/${proposalId}/approve`,
      { method: "POST" }
    );
  },
  studioRejectProposal(workspaceId: string, proposalId: string) {
    return request<ProposalDecision>(
      `/api/v1/workspaces/${workspaceId}/studio/proposals/${proposalId}/reject`,
      { method: "POST" }
    );
  },

  // ---- ship: repositories ----
  listRepos(workspaceId: string) {
    return request<RepoConnection[]>(`/api/v1/workspaces/${workspaceId}/repos`);
  },
  connectRepo(
    workspaceId: string,
    input: {
      provider: "local" | "github";
      name?: string | null;
      repo_full_name?: string | null;
      default_branch?: string;
    }
  ) {
    return request<RepoConnection>(`/api/v1/workspaces/${workspaceId}/repos`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  deleteRepo(workspaceId: string, repoId: string) {
    return request<void>(`/api/v1/workspaces/${workspaceId}/repos/${repoId}`, {
      method: "DELETE",
    });
  },
  checkRepo(workspaceId: string, repoId: string) {
    return request<RepoCheck>(
      `/api/v1/workspaces/${workspaceId}/repos/${repoId}/check`,
      { method: "POST" }
    );
  },

  // ---- ship: local git ----
  gitStatus(workspaceId: string) {
    return request<GitStatus>(`/api/v1/workspaces/${workspaceId}/git/status`);
  },
  gitDiff(workspaceId: string) {
    return request<GitDiff>(`/api/v1/workspaces/${workspaceId}/git/diff`);
  },
  gitLog(workspaceId: string, limit = 20) {
    return request<GitCommit[]>(
      `/api/v1/workspaces/${workspaceId}/git/log?limit=${limit}`
    );
  },

  // ---- ship: pull-request proposals ----
  listPullRequests(workspaceId: string, status?: string) {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<PullRequest[]>(
      `/api/v1/workspaces/${workspaceId}/pull-requests${qs}`
    );
  },
  createPullRequest(
    workspaceId: string,
    input: {
      title: string;
      body?: string | null;
      provider?: "local" | "github" | null;
      repo_id?: string | null;
      base_branch?: string | null;
      meeting_id?: string | null;
      task_id?: string | null;
      proposal_ids?: string[];
    }
  ) {
    return request<PullRequest>(`/api/v1/workspaces/${workspaceId}/pull-requests`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  openPullRequest(workspaceId: string, prId: string) {
    return request<PullRequestDecision>(
      `/api/v1/workspaces/${workspaceId}/pull-requests/${prId}/open`,
      { method: "POST" }
    );
  },
  mergePullRequest(workspaceId: string, prId: string) {
    return request<PullRequestDecision>(
      `/api/v1/workspaces/${workspaceId}/pull-requests/${prId}/merge`,
      { method: "POST" }
    );
  },
  closePullRequest(workspaceId: string, prId: string) {
    return request<PullRequestDecision>(
      `/api/v1/workspaces/${workspaceId}/pull-requests/${prId}/close`,
      { method: "POST" }
    );
  },

  // ---- agent: meeting -> code ----
  agentPlan(
    workspaceId: string,
    input: {
      meeting_id?: string | null;
      decision_id?: string | null;
      task_id?: string | null;
      focus?: string | null;
    }
  ) {
    return request<CodePlan>(`/api/v1/workspaces/${workspaceId}/agent/plan`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  listPlans(workspaceId: string) {
    return request<CodePlan[]>(`/api/v1/workspaces/${workspaceId}/agent/plans`);
  },
  getPlan(workspaceId: string, planId: string) {
    return request<CodePlan>(`/api/v1/workspaces/${workspaceId}/agent/plans/${planId}`);
  },
  applyPlan(workspaceId: string, planId: string) {
    return request<PlanApply>(
      `/api/v1/workspaces/${workspaceId}/agent/plans/${planId}/apply`,
      { method: "POST" }
    );
  },

  // ---- verify: sandboxed test runs (Phase 5) ----
  runTests(workspaceId: string, input: TestRunRequest = {}) {
    return request<TestRun>(`/api/v1/workspaces/${workspaceId}/tests/run`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  listTestRuns(workspaceId: string, status?: string) {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<TestRun[]>(`/api/v1/workspaces/${workspaceId}/tests${qs}`);
  },
  latestTestRun(workspaceId: string) {
    return request<TestRun>(`/api/v1/workspaces/${workspaceId}/tests/latest`);
  },

  // ---- project memory: workspace RAG (Phase 5) ----
  memoryStats(workspaceId: string) {
    return request<MemoryStats>(`/api/v1/workspaces/${workspaceId}/memory/stats`);
  },
  indexMemory(
    workspaceId: string,
    input: { include_code?: boolean; force?: boolean } = {}
  ) {
    return request<MemoryIndexResult>(
      `/api/v1/workspaces/${workspaceId}/memory/index`,
      { method: "POST", body: JSON.stringify(input) }
    );
  },
  searchMemory(
    workspaceId: string,
    input: { query: string; k?: number; types?: string[] }
  ) {
    return request<MemorySearchResult>(
      `/api/v1/workspaces/${workspaceId}/memory/search`,
      { method: "POST", body: JSON.stringify(input) }
    );
  },
  listMemoryChunks(
    workspaceId: string,
    opts: { type?: string; limit?: number } = {}
  ) {
    const params = new URLSearchParams();
    if (opts.type) params.set("type", opts.type);
    if (opts.limit) params.set("limit", String(opts.limit));
    const qs = params.toString() ? `?${params.toString()}` : "";
    return request<MemoryHit[]>(
      `/api/v1/workspaces/${workspaceId}/memory/chunks${qs}`
    );
  },
  deleteMemoryChunk(workspaceId: string, chunkId: string) {
    return request<void>(
      `/api/v1/workspaces/${workspaceId}/memory/chunks/${chunkId}`,
      { method: "DELETE" }
    );
  },
  clearMemory(workspaceId: string, type?: string) {
    const qs = type ? `?type=${encodeURIComponent(type)}` : "";
    return request<{ removed: number; message: string }>(
      `/api/v1/workspaces/${workspaceId}/memory${qs}`,
      { method: "DELETE" }
    );
  },

  // ---- system / demo ----
  getSystemStatus() {
    return request<SystemStatus>("/api/v1/system/status");
  },
  seedDemo() {
    return request<DemoSeedResult>("/api/v1/demo/seed", { method: "POST" });
  },
};

// Sandbox paths are POSIX-relative and may contain nested directories; encode
// each segment so characters like "#" or "?" survive the round-trip.
function encodeStudioPath(path: string): string {
  return path
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
}

export type {
  CodePlan,
  CodeProposal,
  Decision,
  DemoSeedResult,
  GitChangedFile,
  GitCommit,
  GitDiff,
  GitStatus,
  LintFinding,
  LintResult,
  Meeting,
  MeetingSummary,
  MeetingWithDetails,
  Member,
  MemoryHit,
  MemoryIndexResult,
  MemorySearchResult,
  MemoryStats,
  PlanApply,
  PlanChange,
  PlanFile,
  PlanSubtask,
  PullRequest,
  PullRequestDecision,
  PullRequestFile,
  RepoCheck,
  RepoConnection,
  StudioChatResponse,
  StudioFile,
  StudioFileNode,
  StudioTree,
  SystemStatus,
  Task,
  Transcript,
  User,
  Workspace,
} from "./types";
