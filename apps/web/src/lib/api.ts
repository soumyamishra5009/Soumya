// Typed client for the SyncForge FastAPI backend.
//
// Auth uses a bearer JWT issued by /api/v1/auth/*. The token is kept in
// localStorage so the app stays stateless (no server session needed for MVP).

import type {
  Decision,
  Meeting,
  MeetingSummary,
  MeetingWithDetails,
  Task,
  TaskPriority,
  TaskStatus,
  TokenResponse,
  Transcript,
  User,
  Workspace,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

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

  // ---- meetings ----
  listMeetings(workspaceId: string) {
    return request<Meeting[]>(`/api/v1/workspaces/${workspaceId}/meetings`);
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
  listTasks(workspaceId: string, status?: TaskStatus) {
    const qs = status ? `?task_status=${status}` : "";
    return request<Task[]>(`/api/v1/workspaces/${workspaceId}/tasks${qs}`);
  },
  createTask(input: {
    workspace_id: string;
    title: string;
    description?: string | null;
    status?: TaskStatus;
    priority?: TaskPriority;
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
};

export type { Decision, Meeting, MeetingSummary, MeetingWithDetails, Task, Transcript, User, Workspace };
