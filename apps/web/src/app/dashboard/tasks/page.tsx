"use client";

import * as React from "react";
import Link from "next/link";
import {
  Loader2,
  Plus,
  RefreshCw,
  AlertTriangle,
  GripVertical,
  Clock,
  Link2,
  X,
  Search,
  Pencil,
  FilterX,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { useMembers } from "@/components/members-provider";
import { MemberAvatar } from "@/components/member-avatar";
import { api, ApiError } from "@/lib/api";
import type { Task, TaskPriority, TaskStatus } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  KANBAN_COLUMNS,
  TASK_PRIORITY_META,
  TASK_STATUS_META,
  taskDueMeta,
} from "@/lib/format";

const PRIORITIES: TaskPriority[] = ["low", "medium", "high", "urgent"];
const DUE_FILTERS = [
  { id: "", label: "Any due date" },
  { id: "overdue", label: "Overdue" },
  { id: "today", label: "Due today" },
  { id: "week", label: "Due this week" },
] as const;

type DueFilter = (typeof DUE_FILTERS)[number]["id"];

function toDateInput(value: string | null): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

function startOfToday(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

export default function TasksPage() {
  const { workspace } = useAuth();
  const { members, byId } = useMembers();

  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [dragId, setDragId] = React.useState<string | null>(null);
  const [overColumn, setOverColumn] = React.useState<TaskStatus | null>(null);

  // filters
  const [query, setQuery] = React.useState("");
  const [assignee, setAssignee] = React.useState(""); // "" | "me" | "unassigned" | userId
  const [priority, setPriority] = React.useState(""); // "" | TaskPriority
  const [due, setDue] = React.useState<DueFilter>("");

  // create/edit panel
  const [formOpen, setFormOpen] = React.useState(false);
  const [editId, setEditId] = React.useState<string | null>(null);
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [formPriority, setFormPriority] = React.useState<TaskPriority>("medium");
  const [formStatus, setFormStatus] = React.useState<TaskStatus>("todo");
  const [dueDate, setDueDate] = React.useState("");
  const [assigneeId, setAssigneeId] = React.useState("");
  const [estimatedHours, setEstimatedHours] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  const dueRange = React.useMemo(() => {
    const now = new Date();
    if (due === "overdue") return { dueBefore: now.toISOString() };
    if (due === "today") {
      const start = startOfToday();
      const end = new Date(start);
      end.setDate(end.getDate() + 1);
      return { dueAfter: start.toISOString(), dueBefore: end.toISOString() };
    }
    if (due === "week") {
      const end = new Date(now);
      end.setDate(end.getDate() + 7);
      return { dueAfter: now.toISOString(), dueBefore: end.toISOString() };
    }
    return {};
  }, [due]);

  const load = React.useCallback(
    async (opts: { silent?: boolean } = {}) => {
      if (!workspace) return;
      if (!opts.silent) setLoading(true);
      setError(null);
      try {
        const rows = await api.listTasks(workspace.id, {
          q: query.trim() || undefined,
          assignee: assignee || undefined,
          priority: (priority || undefined) as TaskPriority | undefined,
          ...dueRange,
        });
        setTasks(rows);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load tasks");
      } finally {
        if (!opts.silent) setLoading(false);
      }
    },
    [workspace, query, assignee, priority, dueRange]
  );

  // Debounced reload on filter changes.
  React.useEffect(() => {
    const t = setTimeout(() => void load(), query ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, query]);

  const filtersActive = Boolean(query || assignee || priority || due);

  function resetFilters() {
    setQuery("");
    setAssignee("");
    setPriority("");
    setDue("");
  }

  async function moveTask(taskId: string, status: TaskStatus) {
    const current = tasks.find((t) => t.id === taskId);
    if (!current || current.status === status) return;

    const previous = tasks;
    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, status } : t)));
    try {
      const updated = await api.updateTask(taskId, { status });
      setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
      if (status === "done") toast.success("Task completed 🎉");
    } catch (err) {
      setTasks(previous);
      toast.error(err instanceof ApiError ? err.message : "Could not move task");
    }
  }

  async function cyclePriority(task: Task) {
    const next =
      PRIORITIES[(PRIORITIES.indexOf(task.priority) + 1) % PRIORITIES.length];
    const previous = tasks;
    setTasks((prev) =>
      prev.map((t) => (t.id === task.id ? { ...t, priority: next } : t))
    );
    try {
      await api.updateTask(task.id, { priority: next });
    } catch {
      setTasks(previous);
      toast.error("Could not update priority");
    }
  }

  function openCreate() {
    setEditId(null);
    setTitle("");
    setDescription("");
    setFormPriority("medium");
    setFormStatus("todo");
    setDueDate("");
    setAssigneeId("");
    setEstimatedHours("");
    setFormOpen(true);
  }

  function openEdit(t: Task) {
    setEditId(t.id);
    setTitle(t.title);
    setDescription(t.description ?? "");
    setFormPriority(t.priority);
    setFormStatus(t.status);
    setDueDate(toDateInput(t.due_date));
    setAssigneeId(t.assignee_id ?? "");
    setEstimatedHours(t.estimated_hours ? String(t.estimated_hours) : "");
    setFormOpen(true);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!workspace || saving) return;
    if (!title.trim()) {
      toast.error("Enter a task title");
      return;
    }
    setSaving(true);
    const hours = estimatedHours.trim() ? Number(estimatedHours) : null;
    try {
      if (editId) {
        await api.updateTask(editId, {
          title: title.trim(),
          description: description.trim() || null,
          priority: formPriority,
          status: formStatus,
          due_date: dueDate ? new Date(dueDate).toISOString() : null,
          assignee_id: assigneeId || null,
          estimated_hours: hours,
        });
        toast.success("Task updated");
      } else {
        await api.createTask({
          workspace_id: workspace.id,
          title: title.trim(),
          description: description.trim() || null,
          priority: formPriority,
          status: formStatus,
          due_date: dueDate ? new Date(dueDate).toISOString() : null,
          assignee_id: assigneeId || null,
        });
        toast.success("Task added");
      }
      setFormOpen(false);
      await load({ silent: true });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not save task");
    } finally {
      setSaving(false);
    }
  }

  const grouped = React.useMemo(() => {
    const map: Record<TaskStatus, Task[]> = {
      todo: [],
      in_progress: [],
      review: [],
      done: [],
      blocked: [],
      cancelled: [],
    };
    for (const t of tasks) {
      (map[t.status] ?? map.todo).push(t);
    }
    return map;
  }, [tasks]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 animate-fade-in-up">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Task Board</h2>
          <p className="text-muted-foreground">
            Drag cards between columns. Action items from meetings land in To Do.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="icon"
            aria-label="Refresh"
            onClick={() => void load()}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => (formOpen ? setFormOpen(false) : openCreate())}>
            {formOpen ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {formOpen ? "Cancel" : "New task"}
          </Button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 animate-fade-in-up stagger-2">
        <div className="relative min-w-[14rem] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tasks…"
            className="pl-9"
          />
        </div>
        <Button
          variant={assignee === "me" ? "default" : "outline"}
          size="sm"
          onClick={() => setAssignee((v) => (v === "me" ? "" : "me"))}
        >
          My tasks
        </Button>
        <select
          aria-label="Assignee"
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">All assignees</option>
          <option value="unassigned">Unassigned</option>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Priority"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Any priority</option>
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {TASK_PRIORITY_META[p].label}
            </option>
          ))}
        </select>
        <select
          aria-label="Due date"
          value={due}
          onChange={(e) => setDue(e.target.value as DueFilter)}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {DUE_FILTERS.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
        {filtersActive && (
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            <FilterX className="h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      {formOpen && (
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={onSubmit} className="space-y-4">
              <p className="text-sm font-medium">
                {editId ? "Edit task" : "New task"}
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="t-title">Title *</Label>
                  <Input
                    id="t-title"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Follow up with design team"
                    required
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="t-priority">Priority</Label>
                    <select
                      id="t-priority"
                      value={formPriority}
                      onChange={(e) => setFormPriority(e.target.value as TaskPriority)}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {PRIORITIES.map((p) => (
                        <option key={p} value={p}>
                          {TASK_PRIORITY_META[p].label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="t-due">Due date</Label>
                    <Input
                      id="t-due"
                      type="date"
                      value={dueDate}
                      onChange={(e) => setDueDate(e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="t-assignee">Assignee</Label>
                  <select
                    id="t-assignee"
                    value={assigneeId}
                    onChange={(e) => setAssigneeId(e.target.value)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <option value="">Unassigned</option>
                    {members.map((m) => (
                      <option key={m.user_id} value={m.user_id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="t-status">Status</Label>
                  <select
                    id="t-status"
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value as TaskStatus)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {Object.entries(TASK_STATUS_META).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="t-hours">Estimated hours</Label>
                  <Input
                    id="t-hours"
                    type="number"
                    min={0}
                    step={0.5}
                    value={estimatedHours}
                    onChange={(e) => setEstimatedHours(e.target.value)}
                    placeholder="e.g. 4"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="t-desc">Description</Label>
                <Textarea
                  id="t-desc"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  placeholder="Optional details"
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={() => setFormOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={saving}>
                  {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                  {editId ? "Save changes" : "Add task"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          <AlertTriangle className="h-4 w-4" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex h-40 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {KANBAN_COLUMNS.map((col, colIdx) => {
            const meta = TASK_STATUS_META[col];
            const items = grouped[col];
            return (
              <div
                key={col}
                onDragOver={(e) => {
                  e.preventDefault();
                  setOverColumn(col);
                }}
                onDragLeave={() => setOverColumn((c) => (c === col ? null : c))}
                onDrop={(e) => {
                  e.preventDefault();
                  setOverColumn(null);
                  if (dragId) void moveTask(dragId, col);
                  setDragId(null);
                }}
                className={cn(
                  "flex min-h-[16rem] flex-col rounded-lg border bg-card/40 transition-colors animate-fade-in-up",
                  `stagger-${Math.min(colIdx + 1, 8)}`,
                  overColumn === col && "border-primary bg-primary/5"
                )}
              >
                <div className="flex items-center justify-between border-b px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className={cn("h-2 w-2 rounded-full", meta.accent)} />
                    <span className="text-sm font-medium">{meta.label}</span>
                  </div>
                  <Badge variant="outline">{items.length}</Badge>
                </div>

                <div className="flex-1 space-y-2 p-3">
                  {items.length === 0 && (
                    <p className="rounded-md border border-dashed py-6 text-center text-xs text-muted-foreground">
                      Drop tasks here
                    </p>
                  )}
                  {items.map((t) => {
                    const pm = TASK_PRIORITY_META[t.priority];
                    const due = taskDueMeta(t.due_date, t.status);
                    const assignee = t.assignee_id ? byId[t.assignee_id] : undefined;
                    return (
                      <div
                        key={t.id}
                        draggable
                        onDragStart={() => setDragId(t.id)}
                        onDragEnd={() => setDragId(null)}
                        className={cn(
                          "group cursor-grab rounded-lg border bg-background p-3 shadow-sm transition-opacity active:cursor-grabbing",
                          dragId === t.id && "opacity-50"
                        )}
                      >
                        <div className="flex items-start gap-2">
                          <GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/50" />
                          <p
                            className={cn(
                              "flex-1 text-sm",
                              t.status === "done" &&
                                "text-muted-foreground line-through"
                            )}
                          >
                            {t.title}
                          </p>
                          <button
                            type="button"
                            aria-label="Edit task"
                            title="Edit"
                            onClick={() => openEdit(t)}
                            className="rounded p-1 text-muted-foreground/50 opacity-0 transition-opacity hover:bg-accent/20 hover:text-foreground group-hover:opacity-100"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        </div>

                        {t.description && (
                          <p className="mt-1 line-clamp-2 pl-6 text-xs text-muted-foreground">
                            {t.description}
                          </p>
                        )}

                        <div className="mt-2 flex flex-wrap items-center gap-2 pl-6">
                          <button
                            type="button"
                            onClick={() => void cyclePriority(t)}
                            title="Click to change priority"
                          >
                            <Badge variant={pm.variant} className="cursor-pointer">
                              {pm.label}
                            </Badge>
                          </button>
                          {due && (
                            <span
                              className={cn(
                                "inline-flex items-center gap-1 text-xs",
                                due.overdue
                                  ? "text-rose-400"
                                  : "text-muted-foreground"
                              )}
                            >
                              <Clock className="h-3 w-3" />
                              {due.label}
                            </span>
                          )}
                          {t.meeting_id && (
                            <Link
                              href={`/dashboard/meetings/${t.meeting_id}`}
                              className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
                            >
                              <Link2 className="h-3 w-3" />
                              meeting
                            </Link>
                          )}
                        </div>

                        <div className="mt-2 flex items-center justify-between gap-2 pl-6">
                          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                            <MemberAvatar member={assignee} size="xs" />
                            <span className="truncate">
                              {assignee ? assignee.name : "Unassigned"}
                            </span>
                          </div>
                        </div>

                        {/* Quick status controls */}
                        <div className="mt-2 flex gap-1 pl-6 opacity-0 transition-opacity group-hover:opacity-100">
                          {KANBAN_COLUMNS.filter((c) => c !== col).map((c) => (
                            <button
                              key={c}
                              onClick={() => void moveTask(t.id, c)}
                              className="rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-accent/10 hover:text-foreground"
                            >
                              {TASK_STATUS_META[c].label}
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
