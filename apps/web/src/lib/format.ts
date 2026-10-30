import type { MeetingStatus, TaskPriority, TaskStatus } from "./types";

type BadgeVariant =
  | "default"
  | "secondary"
  | "destructive"
  | "outline"
  | "success"
  | "warning"
  | "info";

export const MEETING_STATUS_META: Record<
  MeetingStatus,
  { label: string; variant: BadgeVariant; pulse?: boolean }
> = {
  pending: { label: "Pending", variant: "secondary" },
  uploading: { label: "Uploaded", variant: "secondary" },
  transcribing: { label: "Transcribing", variant: "info", pulse: true },
  summarizing: { label: "Summarizing", variant: "info", pulse: true },
  processing: { label: "Processing", variant: "info", pulse: true },
  completed: { label: "Completed", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
};

export const TASK_STATUS_META: Record<
  TaskStatus,
  { label: string; variant: BadgeVariant; accent: string }
> = {
  todo: { label: "To Do", variant: "secondary", accent: "bg-slate-400" },
  in_progress: { label: "In Progress", variant: "info", accent: "bg-sky-400" },
  review: { label: "Review", variant: "warning", accent: "bg-amber-400" },
  done: { label: "Done", variant: "success", accent: "bg-emerald-400" },
  blocked: { label: "Blocked", variant: "destructive", accent: "bg-rose-400" },
  cancelled: { label: "Cancelled", variant: "outline", accent: "bg-zinc-500" },
};

export const TASK_PRIORITY_META: Record<
  TaskPriority,
  { label: string; variant: BadgeVariant; dot: string }
> = {
  low: { label: "Low", variant: "outline", dot: "bg-slate-400" },
  medium: { label: "Medium", variant: "secondary", dot: "bg-sky-400" },
  high: { label: "High", variant: "warning", dot: "bg-amber-400" },
  urgent: { label: "Urgent", variant: "destructive", dot: "bg-rose-500" },
};

export const KANBAN_COLUMNS: TaskStatus[] = [
  "todo",
  "in_progress",
  "review",
  "done",
];

export function isMeetingBusy(status: MeetingStatus): boolean {
  return ["uploading", "transcribing", "summarizing", "processing"].includes(
    status
  );
}

export function formatMinutes(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "—";
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value).getTime();
  if (Number.isNaN(d)) return "—";
  const diff = Date.now() - d;
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}

export function taskDueMeta(
  dueDate: string | null,
  status: TaskStatus
): { label: string; overdue: boolean } | null {
  if (!dueDate) return null;
  const due = new Date(dueDate);
  if (Number.isNaN(due.getTime())) return null;
  const overdue = status !== "done" && due.getTime() < Date.now();
  return { label: formatDate(dueDate), overdue };
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}
