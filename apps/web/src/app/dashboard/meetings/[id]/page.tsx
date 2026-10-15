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
  Upload,
  CheckCircle2,
  Sparkles,
  Clock,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type { MeetingWithDetails, Task } from "@/lib/types";
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

function Section({
  icon: Icon,
  title,
  items,
  tone = "default",
}: {
  icon: React.ElementType;
  title: string;
  items: string[];
  tone?: "default" | "warning" | "muted";
}) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <p className="mb-2 flex items-center gap-2 text-sm font-medium">
        <Icon
          className={cn(
            "h-4 w-4",
            tone === "warning" ? "text-amber-400" : "text-accent"
          )}
        />
        {title}
      </p>
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
    </div>
  );
}

export default function MeetingRoomPage() {
  const params = useParams<{ id: string }>();
  const meetingId = params?.id;

  const [meeting, setMeeting] = React.useState<MeetingWithDetails | null>(null);
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<Tab>("summary");
  const [search, setSearch] = React.useState("");
  const [reprocessing, setReprocessing] = React.useState(false);

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
              <h2 className="text-2xl font-bold tracking-tight">
                {meeting.title}
              </h2>
              <Badge
                variant={meta.variant}
                className={meta.pulse ? "animate-pulse" : undefined}
              >
                {meta.label}
              </Badge>
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
                {meeting.summary ? (
                  <p className="text-sm leading-relaxed">{meeting.summary}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No summary yet.
                  </p>
                )}
                <Section
                  icon={FileText}
                  title="Key points"
                  items={meeting.key_points ?? []}
                />
                <Section
                  icon={ArrowRight}
                  title="Next steps"
                  items={meeting.next_steps ?? []}
                />
                <Section
                  icon={AlertTriangle}
                  title="Risks"
                  items={meeting.risks ?? []}
                  tone="warning"
                />
                <Section
                  icon={HelpCircle}
                  title="Open questions"
                  items={meeting.unanswered_questions ?? []}
                  tone="muted"
                />
              </>
            )}

            {tab === "decisions" &&
              (meeting.decisions.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No decisions extracted.
                </p>
              ) : (
                <ul className="space-y-3">
                  {meeting.decisions.map((d) => (
                    <li
                      key={d.id}
                      className="rounded-lg border bg-muted/20 p-3"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium">{d.title}</p>
                        <Badge
                          variant={
                            d.impact === "high"
                              ? "warning"
                              : d.impact === "low"
                                ? "outline"
                                : "secondary"
                          }
                        >
                          {d.impact} impact
                        </Badge>
                      </div>
                      {d.description && (
                        <p className="mt-1 text-sm text-muted-foreground">
                          {d.description}
                        </p>
                      )}
                      {d.rationale && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Why: {d.rationale}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              ))}

            {tab === "tasks" &&
              (tasks.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No action items extracted.
                </p>
              ) : (
                <ul className="space-y-2">
                  {tasks.map((t) => {
                    const pm = TASK_PRIORITY_META[t.priority];
                    return (
                      <li
                        key={t.id}
                        className="flex items-start gap-3 rounded-lg border bg-muted/20 p-3"
                      >
                        {t.status === "done" ? (
                          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                        ) : (
                          <span
                            className={cn(
                              "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                              pm.dot
                            )}
                          />
                        )}
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
                            {t.estimated_hours && (
                              <span>~{t.estimated_hours}h</span>
                            )}
                          </div>
                        </div>
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
