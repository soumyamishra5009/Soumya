"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  RefreshCw,
  PlayCircle,
  FileText,
  ListChecks,
  Gavel,
  AlertTriangle,
  HelpCircle,
  ArrowRight,
  Search,
  CheckCircle2,
  Sparkles,
  Clock,
  Users,
  Pencil,
  Plus,
  Trash2,
  Save,
  X,
  Archive,
  ArchiveRestore,
} from "lucide-react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { Decision, MeetingWithDetails, Task } from "@/lib/types";
import { useMembers } from "@/components/members-provider";
import { MemberAvatar } from "@/components/member-avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  MEETING_STATUS_META,
  TASK_PRIORITY_META,
  formatMinutes,
  formatDate,
  isMeetingBusy,
  relativeTime,
} from "@/lib/format";

type Tab = "summary" | "decisions" | "tasks";

const IMPACTS = ["low", "medium", "high"] as const;

/** Inline-editable bullet list (key points, risks, next steps, questions). */
function EditableList({
  icon: Icon,
  title,
  items,
  tone = "default",
  placeholder,
  onSave,
}: {
  icon: React.ElementType;
  title: string;
  items: string[];
  tone?: "default" | "warning" | "muted";
  placeholder: string;
  onSave: (items: string[]) => Promise<void>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  async function save() {
    setSaving(true);
    try {
      await onSave(
        draft
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean)
      );
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <Icon
          className={cn(
            "h-4 w-4",
            tone === "warning" ? "text-amber-400" : "text-accent"
          )}
        />
        <span className="flex-1 text-sm font-medium">{title}</span>
        {!editing && (
          <button
            type="button"
            aria-label={`Edit ${title}`}
            title="Edit"
            onClick={() => {
              setDraft(items.join("\n"));
              setEditing(true);
            }}
            className="rounded p-1 text-muted-foreground/60 transition-colors hover:bg-accent/20 hover:text-foreground"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={Math.max(3, Math.min(8, items.length + 2))}
            placeholder={placeholder}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => void save()} disabled={saving}>
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              Save
            </Button>
          </div>
        </div>
      ) : items.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nothing yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item, i) => (
            <li
              key={i}
              className="flex items-start gap-2 text-sm text-muted-foreground"
            >
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/60" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Human-in-the-loop editor for a single AI-extracted decision. */
function DecisionItem({
  decision,
  onUpdate,
  onDelete,
}: {
  decision: Decision;
  onUpdate: (
    patch: Partial<{ title: string; description: string | null; impact: string; rationale: string | null }>
  ) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [title, setTitle] = React.useState(decision.title);
  const [description, setDescription] = React.useState(decision.description ?? "");
  const [impact, setImpact] = React.useState<string>(decision.impact);
  const [rationale, setRationale] = React.useState(decision.rationale ?? "");
  const [saving, setSaving] = React.useState(false);

  async function save() {
    if (!title.trim()) {
      toast.error("Decision needs a title");
      return;
    }
    setSaving(true);
    try {
      await onUpdate({
        title: title.trim(),
        description: description.trim() || null,
        impact,
        rationale: rationale.trim() || null,
      });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <li className="space-y-2 rounded-lg border border-primary/40 bg-muted/20 p-3">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Decision" />
        <Textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="What was decided?"
        />
        <Textarea
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          rows={2}
          placeholder="Why? (optional)"
        />
        <div className="flex items-center gap-2">
          <select
            value={impact}
            onChange={(e) => setImpact(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {IMPACTS.map((i) => (
              <option key={i} value={i}>
                {i} impact
              </option>
            ))}
          </select>
          <div className="flex-1" />
          <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => void save()} disabled={saving}>
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            Save
          </Button>
        </div>
      </li>
    );
  }

  return (
    <li className="group rounded-lg border bg-muted/20 p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium">{decision.title}</p>
        <div className="flex shrink-0 items-center gap-1">
          <Badge
            variant={
              decision.impact === "high"
                ? "warning"
                : decision.impact === "low"
                  ? "outline"
                  : "secondary"
            }
          >
            {decision.impact} impact
          </Badge>
          <button
            type="button"
            aria-label="Edit decision"
            title="Edit"
            onClick={() => setEditing(true)}
            className="rounded p-1 text-muted-foreground/60 transition-colors hover:bg-accent/20 hover:text-foreground"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Delete decision"
            title="Delete"
            onClick={() => void onDelete()}
            className="rounded p-1 text-muted-foreground/60 transition-colors hover:bg-destructive/20 hover:text-rose-400"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      {decision.description && (
        <p className="mt-1 text-sm text-muted-foreground">{decision.description}</p>
      )}
      {decision.rationale && (
        <p className="mt-1 text-xs text-muted-foreground">Why: {decision.rationale}</p>
      )}
    </li>
  );
}

export default function MeetingRoomPage() {
  const params = useParams<{ id: string }>();
  const meetingId = params?.id;
  const { byId, members } = useMembers();

  const [meeting, setMeeting] = React.useState<MeetingWithDetails | null>(null);
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<Tab>("summary");
  const [search, setSearch] = React.useState("");
  const [reprocessing, setReprocessing] = React.useState(false);

  // header title editing
  const [editingTitle, setEditingTitle] = React.useState(false);
  const [titleDraft, setTitleDraft] = React.useState("");

  // summary editing
  const [editingSummary, setEditingSummary] = React.useState(false);
  const [summaryDraft, setSummaryDraft] = React.useState("");
  const [savingSummary, setSavingSummary] = React.useState(false);

  // new decision form
  const [addingDecision, setAddingDecision] = React.useState(false);
  const [newDecisionTitle, setNewDecisionTitle] = React.useState("");
  const [newDecisionImpact, setNewDecisionImpact] = React.useState<string>("medium");
  const [savingDecision, setSavingDecision] = React.useState(false);

  const load = React.useCallback(async () => {
    if (!meetingId) return;
    try {
      const [m, t] = await Promise.all([
        api.getMeeting(meetingId),
        api.listMeetingTasks(meetingId),
      ]);
      setMeeting(m);
      setTasks(t);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load meeting");
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  React.useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  // Poll while processing
  React.useEffect(() => {
    if (!meeting || !isMeetingBusy(meeting.status)) return;
    const t = setTimeout(() => void load(), 3000);
    return () => clearTimeout(t);
  }, [meeting, load]);

  async function reprocess() {
    if (!meetingId || reprocessing) return;
    setReprocessing(true);
    try {
      await api.processMeeting(meetingId);
      toast.success("Re-processing started");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not reprocess");
    } finally {
      setReprocessing(false);
    }
  }

  // Persist an editable change locally + on the server.
  async function patchMeeting(
    patch: Parameters<typeof api.updateMeeting>[1],
    successMessage?: string
  ) {
    if (!meetingId) return;
    try {
      const updated = await api.updateMeeting(meetingId, patch);
      setMeeting((prev) => (prev ? { ...prev, ...updated } : prev));
      if (successMessage) toast.success(successMessage);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not save changes");
      throw err;
    }
  }

  async function saveTitle() {
    const next = titleDraft.trim();
    if (!next) {
      toast.error("Title cannot be empty");
      return;
    }
    await patchMeeting({ title: next }, "Title updated");
    setEditingTitle(false);
  }

  async function saveSummary() {
    setSavingSummary(true);
    try {
      await patchMeeting(
        { summary: summaryDraft.trim() || null },
        "Summary updated"
      );
      setEditingSummary(false);
    } finally {
      setSavingSummary(false);
    }
  }

  async function addDecision(e: React.FormEvent) {
    e.preventDefault();
    if (!meetingId || savingDecision) return;
    if (!newDecisionTitle.trim()) {
      toast.error("Decision needs a title");
      return;
    }
    setSavingDecision(true);
    try {
      await api.createDecision(meetingId, {
        title: newDecisionTitle.trim(),
        impact: newDecisionImpact,
      });
      toast.success("Decision added");
      setNewDecisionTitle("");
      setNewDecisionImpact("medium");
      setAddingDecision(false);
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add decision");
    } finally {
      setSavingDecision(false);
    }
  }

  async function updateDecision(id: string, patch: Parameters<typeof api.updateDecision>[1]) {
    try {
      const updated = await api.updateDecision(id, patch);
      setMeeting((prev) =>
        prev
          ? {
              ...prev,
              decisions: prev.decisions.map((d) => (d.id === id ? updated : d)),
            }
          : prev
      );
      toast.success("Decision updated");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not update decision");
      throw err;
    }
  }

  async function deleteDecision(id: string) {
    if (!confirm("Delete this decision?")) return;
    try {
      await api.deleteDecision(id);
      setMeeting((prev) =>
        prev ? { ...prev, decisions: prev.decisions.filter((d) => d.id !== id) } : prev
      );
      toast.success("Decision deleted");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not delete decision");
    }
  }

  async function setAssignee(taskId: string, assigneeId: string | null) {
    try {
      const updated = await api.updateTask(taskId, { assignee_id: assigneeId });
      setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
      toast.success(assigneeId ? "Task assigned" : "Task unassigned");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not assign task");
    }
  }

  async function toggleTaskDone(task: Task) {
    const next = task.status === "done" ? "todo" : "done";
    try {
      const updated = await api.updateTask(task.id, { status: next });
      setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not update task");
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !meeting) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/dashboard/meetings">
            <ArrowLeft className="h-4 w-4" /> Back to meetings
          </Link>
        </Button>
        <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          <AlertTriangle className="h-4 w-4" />
          {error ?? "Meeting not found"}
        </div>
      </div>
    );
  }

  const meta = MEETING_STATUS_META[meeting.status];
  const segments = meeting.transcript?.segments ?? [];
  const filteredSegments = search.trim()
    ? segments.filter((s) =>
        s.text.toLowerCase().includes(search.trim().toLowerCase())
      )
    : segments;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-4">
        <Button variant="ghost" size="sm" asChild className="-ml-2">
          <Link href="/dashboard/meetings">
            <ArrowLeft className="h-4 w-4" /> Back to meetings
          </Link>
        </Button>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              {editingTitle ? (
                <div className="flex items-center gap-2">
                  <Input
                    value={titleDraft}
                    onChange={(e) => setTitleDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void saveTitle();
                      if (e.key === "Escape") setEditingTitle(false);
                    }}
                    className="h-9 w-72 text-lg font-semibold"
                    autoFocus
                  />
                  <Button size="sm" onClick={() => void saveTitle()}>
                    <Save className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditingTitle(false)}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ) : (
                <button
                  type="button"
                  className="group flex items-center gap-2 text-left"
                  title="Rename meeting"
                  onClick={() => {
                    setTitleDraft(meeting.title);
                    setEditingTitle(true);
                  }}
                >
                  <h2 className="text-2xl font-bold tracking-tight">
                    {meeting.title}
                  </h2>
                  <Pencil className="h-4 w-4 text-muted-foreground/50 opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
              )}
              <Badge
                variant={meta.variant}
                className={meta.pulse ? "animate-pulse" : undefined}
              >
                {meta.label}
              </Badge>
              {meeting.archived && <Badge variant="outline">archived</Badge>}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                {meeting.audio_duration_seconds
                  ? formatMinutes(meeting.audio_duration_seconds)
                  : relativeTime(meeting.created_at)}
              </span>
              {meeting.meeting_date && (
                <span>{formatDate(meeting.meeting_date)}</span>
              )}
              {meeting.participants && meeting.participants.length > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Users className="h-3.5 w-3.5" />
                  {meeting.participants.join(", ")}
                </span>
              )}
              {meeting.language && (
                <span className="uppercase">{meeting.language}</span>
              )}
              {meeting.transcript?.engine && (
                <span>via {meeting.transcript.engine.replace("_", " ")}</span>
              )}
            </div>
          </div>

          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() =>
                void patchMeeting(
                  { archived: !meeting.archived },
                  meeting.archived ? "Restored to history" : "Moved to archive"
                )
              }
            >
              {meeting.archived ? (
                <ArchiveRestore className="h-4 w-4" />
              ) : (
                <Archive className="h-4 w-4" />
              )}
              {meeting.archived ? "Restore" : "Archive"}
            </Button>
            <Button
              variant="outline"
              onClick={reprocess}
              disabled={reprocessing || isMeetingBusy(meeting.status)}
            >
              {reprocessing || isMeetingBusy(meeting.status) ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Re-analyse
            </Button>
          </div>
        </div>

        {meeting.status === "failed" && meeting.error_message && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-medium">Processing failed</p>
              <p className="text-muted-foreground">{meeting.error_message}</p>
            </div>
          </div>
        )}
      </div>

      {/* Audio player */}
      {meeting.audio_file_name && (
        <Card>
          <CardContent className="flex items-center gap-4 py-4">
            <PlayCircle className="h-5 w-5 shrink-0 text-accent" />
            <audio
              controls
              preload="none"
              className="h-9 w-full"
              src={api.audioUrl(meeting.id)}
            />
          </CardContent>
        </Card>
      )}

      {isMeetingBusy(meeting.status) && (
        <div className="flex items-center gap-3 rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-sm text-sky-200">
          <Loader2 className="h-4 w-4 animate-spin" />
          {meeting.status === "transcribing"
            ? "Transcribing audio…"
            : meeting.status === "summarizing"
              ? "Extracting decisions and action items…"
              : "Processing…"}{" "}
          This page updates automatically.
        </div>
      )}

      {/* Split view */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Transcript */}
        <Card className="flex max-h-[calc(100vh-22rem)] flex-col">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
            <div>
              <CardTitle className="text-base">Transcript</CardTitle>
              <CardDescription>
                {segments.length} segments
                {meeting.transcript?.language
                  ? ` · ${meeting.transcript.language}`
                  : ""}
              </CardDescription>
            </div>
          </CardHeader>
          {segments.length > 0 && (
            <div className="px-6 pb-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search transcript…"
                  className="pl-9"
                />
              </div>
            </div>
          )}
          <CardContent className="min-h-0 flex-1 overflow-y-auto">
            {segments.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center py-12 text-center text-sm text-muted-foreground">
                <FileText className="mb-2 h-8 w-8" />
                {isMeetingBusy(meeting.status)
                  ? "Transcript will appear here when ready."
                  : "No transcript available yet."}
              </div>
            ) : filteredSegments.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No segments match “{search}”.
              </p>
            ) : (
              <ul className="space-y-3">
                {filteredSegments.map((s) => (
                  <li key={s.id} className="flex gap-3 text-sm">
                    <span className="w-12 shrink-0 pt-0.5 font-mono text-xs text-muted-foreground">
                      {formatMinutes(s.start_time).replace(" ", "")}
                    </span>
                    <div className="min-w-0">
                      {s.speaker && (
                        <span className="mr-2 font-medium text-accent">
                          {s.speaker}
                        </span>
                      )}
                      <span>{s.text}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Insights */}
        <Card className="flex max-h-[calc(100vh-22rem)] flex-col">
          <CardHeader className="pb-3">
            <div className="flex gap-1 rounded-lg border bg-muted/30 p-1">
              {(
                [
                  { id: "summary", label: "Summary", icon: Sparkles },
                  {
                    id: "decisions",
                    label: `Decisions (${meeting.decisions.length})`,
                    icon: Gavel,
                  },
                  {
                    id: "tasks",
                    label: `Actions (${tasks.length})`,
                    icon: ListChecks,
                  },
                ] as const
              ).map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    tab === t.id
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <t.icon className="h-3.5 w-3.5" />
                  {t.label}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 space-y-6 overflow-y-auto">
            {tab === "summary" && (
              <>
                <div>
                  <div className="mb-2 flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-accent" />
                    <span className="flex-1 text-sm font-medium">Summary</span>
                    {!editingSummary && (
                      <button
                        type="button"
                        aria-label="Edit summary"
                        title="Edit summary"
                        onClick={() => {
                          setSummaryDraft(meeting.summary ?? "");
                          setEditingSummary(true);
                        }}
                        className="rounded p-1 text-muted-foreground/60 transition-colors hover:bg-accent/20 hover:text-foreground"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                  {editingSummary ? (
                    <div className="space-y-2">
                      <Textarea
                        value={summaryDraft}
                        onChange={(e) => setSummaryDraft(e.target.value)}
                        rows={6}
                        placeholder="Write a summary…"
                      />
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingSummary(false)}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => void saveSummary()}
                          disabled={savingSummary}
                        >
                          {savingSummary ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Save className="h-3.5 w-3.5" />
                          )}
                          Save
                        </Button>
                      </div>
                    </div>
                  ) : meeting.summary ? (
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {meeting.summary}
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground">No summary yet.</p>
                  )}
                </div>

                <EditableList
                  icon={FileText}
                  title="Key points"
                  items={meeting.key_points ?? []}
                  placeholder="One key point per line"
                  onSave={async (items) => {
                    await patchMeeting({ key_points: items }, "Key points updated");
                  }}
                />
                <EditableList
                  icon={ArrowRight}
                  title="Next steps"
                  items={meeting.next_steps ?? []}
                  placeholder="One next step per line"
                  onSave={async (items) => {
                    await patchMeeting({ next_steps: items }, "Next steps updated");
                  }}
                />
                <EditableList
                  icon={AlertTriangle}
                  title="Risks"
                  items={meeting.risks ?? []}
                  tone="warning"
                  placeholder="One risk per line"
                  onSave={async (items) => {
                    await patchMeeting({ risks: items }, "Risks updated");
                  }}
                />
                <EditableList
                  icon={HelpCircle}
                  title="Open questions"
                  items={meeting.unanswered_questions ?? []}
                  tone="muted"
                  placeholder="One question per line"
                  onSave={async (items) => {
                    await patchMeeting(
                      { unanswered_questions: items },
                      "Questions updated"
                    );
                  }}
                />
              </>
            )}

            {tab === "decisions" && (
              <div className="space-y-3">
                {meeting.decisions.length === 0 && !addingDecision && (
                  <p className="text-sm text-muted-foreground">
                    No decisions extracted. Add the ones the AI missed.
                  </p>
                )}
                <ul className="space-y-3">
                  {meeting.decisions.map((d) => (
                    <DecisionItem
                      key={d.id}
                      decision={d}
                      onUpdate={(patch) => updateDecision(d.id, patch)}
                      onDelete={() => deleteDecision(d.id)}
                    />
                  ))}
                </ul>

                {addingDecision ? (
                  <form
                    onSubmit={addDecision}
                    className="space-y-2 rounded-lg border border-primary/40 bg-muted/20 p-3"
                  >
                    <Input
                      value={newDecisionTitle}
                      onChange={(e) => setNewDecisionTitle(e.target.value)}
                      placeholder="Decision title"
                      autoFocus
                    />
                    <div className="flex items-center gap-2">
                      <select
                        value={newDecisionImpact}
                        onChange={(e) => setNewDecisionImpact(e.target.value)}
                        className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {IMPACTS.map((i) => (
                          <option key={i} value={i}>
                            {i} impact
                          </option>
                        ))}
                      </select>
                      <div className="flex-1" />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setAddingDecision(false)}
                      >
                        Cancel
                      </Button>
                      <Button type="submit" size="sm" disabled={savingDecision}>
                        {savingDecision && (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        )}
                        Add
                      </Button>
                    </div>
                  </form>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setAddingDecision(true)}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add decision
                  </Button>
                )}
              </div>
            )}

            {tab === "tasks" &&
              (tasks.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No action items extracted.
                </p>
              ) : (
                <ul className="space-y-2">
                  {tasks.map((t) => {
                    const pm = TASK_PRIORITY_META[t.priority];
                    const assignee = t.assignee_id ? byId[t.assignee_id] : undefined;
                    return (
                      <li
                        key={t.id}
                        className="flex items-start gap-3 rounded-lg border bg-muted/20 p-3"
                      >
                        <button
                          type="button"
                          title={t.status === "done" ? "Mark as to-do" : "Mark as done"}
                          onClick={() => void toggleTaskDone(t)}
                          className="mt-0.5 shrink-0"
                        >
                          {t.status === "done" ? (
                            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                          ) : (
                            <span
                              className={cn(
                                "block h-2 w-2 translate-y-1 rounded-full",
                                pm.dot
                              )}
                            />
                          )}
                        </button>
                        <div className="min-w-0 flex-1">
                          <p
                            className={cn(
                              "text-sm",
                              t.status === "done" &&
                                "text-muted-foreground line-through"
                            )}
                          >
                            {t.title}
                          </p>
                          {t.description && (
                            <p className="mt-0.5 text-xs text-muted-foreground">
                              {t.description}
                            </p>
                          )}
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <Badge variant={pm.variant}>{pm.label}</Badge>
                            {t.due_date && <span>Due {formatDate(t.due_date)}</span>}
                            {t.estimated_hours && <span>~{t.estimated_hours}h</span>}
                          </div>
                        </div>
                        <label className="flex shrink-0 items-center gap-2">
                          <MemberAvatar member={assignee} size="sm" />
                          <select
                            aria-label="Assign task"
                            value={t.assignee_id ?? ""}
                            onChange={(e) =>
                              void setAssignee(t.id, e.target.value || null)
                            }
                            className="h-8 max-w-[9rem] rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <option value="">Unassigned</option>
                            {members.map((m) => (
                              <option key={m.user_id} value={m.user_id}>
                                {m.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              ))}
          </CardContent>
        </Card>
      </div>

      <div className="flex justify-end">
        <Button variant="outline" asChild>
          <Link href="/dashboard/tasks">
            Open task board <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      </div>
    </div>
  );
}
