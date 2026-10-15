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
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
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

export default function TasksPage() {
  const { workspace } = useAuth();
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [dragId, setDragId] = React.useState<string | null>(null);
  const [overColumn, setOverColumn] = React.useState<TaskStatus | null>(null);
  const [adding, setAdding] = React.useState(false);

  // new task form
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [priority, setPriority] = React.useState<TaskPriority>("medium");
  const [dueDate, setDueDate] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  const load = React.useCallback(async () => {
    if (!workspace) return;
    setLoading(true);
    setError(null);
    try {
      setTasks(await api.listTasks(workspace.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load tasks");
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function moveTask(taskId: string, status: TaskStatus) {
    const current = tasks.find((t) => t.id === taskId);
    if (!current || current.status === status) return;

    const previous = tasks;
    // optimistic update
    setTasks((prev) =>
      prev.map((t) => (t.id === taskId ? { ...t, status } : t))
    );

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

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!workspace || saving) return;
    if (!title.trim()) {
      toast.error("Enter a task title");
      return;
    }
    setSaving(true);
    try {
      const created = await api.createTask({
        workspace_id: workspace.id,
        title: title.trim(),
        description: description.trim() || null,
        priority,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
      });
      setTasks((prev) => [...prev, created]);
      setTitle("");
      setDescription("");
      setPriority("medium");
      setDueDate("");
      setAdding(false);
      toast.success("Task added");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create task");
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
      <div className="flex flex-wrap items-end justify-between gap-4">
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
          <Button onClick={() => setAdding((v) => !v)}>
            {adding ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {adding ? "Cancel" : "New task"}
          </Button>
        </div>
      </div>

      {adding && (
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={onCreate} className="space-y-4">
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
                      value={priority}
                      onChange={(e) =>
                        setPriority(e.target.value as TaskPriority)
                      }
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
              <div className="flex justify-end">
                <Button type="submit" disabled={saving}>
                  {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                  Add task
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
          {KANBAN_COLUMNS.map((col) => {
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
                  "flex min-h-[16rem] flex-col rounded-lg border bg-card/40 transition-colors",
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

                        {/* Quick status controls for touch / no-drag */}
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
