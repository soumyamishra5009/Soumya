"use client";

import * as React from "react";
import Link from "next/link";
import {
  AudioLines,
  KanbanSquare,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Loader2,
  Upload,
  ListChecks,
  FileText,
} from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { useMembers } from "@/components/members-provider";
import { MemberAvatar } from "@/components/member-avatar";
import { api, ApiError } from "@/lib/api";
import type { Meeting, Task } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  MEETING_STATUS_META,
  TASK_PRIORITY_META,
  formatMinutes,
  isMeetingBusy,
  relativeTime,
  taskDueMeta,
} from "@/lib/format";

function StatCard({
  title,
  value,
  hint,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  hint: string;
  icon: React.ElementType;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { workspace } = useAuth();
  const { byId } = useMembers();
  const [meetings, setMeetings] = React.useState<Meeting[]>([]);
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!workspace) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [m, t] = await Promise.all([
          api.listMeetings(workspace.id),
          api.listTasks(workspace.id),
        ]);
        if (!cancelled) {
          setMeetings(m);
          setTasks(t);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Failed to load dashboard"
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspace]);

  const completedMeetings = meetings.filter((m) => m.status === "completed").length;
  const processing = meetings.filter((m) => isMeetingBusy(m.status)).length;
  const activeTasks = tasks.filter(
    (t) => t.status === "in_progress" || t.status === "review"
  ).length;
  const doneTasks = tasks.filter((t) => t.status === "done").length;
  const overdueTasks = tasks.filter(
    (t) => taskDueMeta(t.due_date, t.status)?.overdue
  ).length;

  const recentMeetings = meetings.slice(0, 4);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Overview</h2>
          <p className="text-muted-foreground">
            Your meeting → decision → task pipeline at a glance.
          </p>
        </div>
        <Button asChild>
          <Link href="/dashboard/meetings">
            <Upload className="h-4 w-4" />
            Upload a meeting
          </Link>
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive-foreground">
          <AlertTriangle className="h-4 w-4" />
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Meetings"
          value={meetings.length}
          hint={`${completedMeetings} analysed${processing ? ` · ${processing} processing` : ""}`}
          icon={AudioLines}
        />
        <StatCard
          title="Active Tasks"
          value={activeTasks}
          hint="In progress or in review"
          icon={KanbanSquare}
        />
        <StatCard
          title="Completed"
          value={doneTasks}
          hint={`of ${tasks.length} total tasks`}
          icon={CheckCircle2}
        />
        <StatCard
          title="Overdue"
          value={overdueTasks}
          hint={overdueTasks ? "Needs attention" : "All on track"}
          icon={AlertTriangle}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Recent meetings</CardTitle>
              <CardDescription>Latest uploads and their status</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/dashboard/meetings">
                View all <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {recentMeetings.length === 0 ? (
              <div className="rounded-lg border border-dashed p-8 text-center">
                <AudioLines className="mx-auto h-8 w-8 text-muted-foreground" />
                <p className="mt-3 text-sm font-medium">No meetings yet</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Upload a recording to get a summary, decisions and tasks.
                </p>
                <Button className="mt-4" size="sm" asChild>
                  <Link href="/dashboard/meetings">Upload now</Link>
                </Button>
              </div>
            ) : (
              <ul className="divide-y">
                {recentMeetings.map((m) => {
                  const meta = MEETING_STATUS_META[m.status];
                  return (
                    <li key={m.id}>
                      <Link
                        href={`/dashboard/meetings/${m.id}`}
                        className="flex items-center justify-between gap-4 py-3 transition-colors hover:bg-accent/5"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{m.title}</p>
                          <p className="text-xs text-muted-foreground">
                            {relativeTime(m.created_at)}
                            {m.audio_duration_seconds
                              ? ` · ${formatMinutes(m.audio_duration_seconds)}`
                              : ""}
                            {m.participants?.length
                              ? ` · ${m.participants.length} participants`
                              : ""}
                          </p>
                        </div>
                        <Badge
                          variant={meta.variant}
                          className={meta.pulse ? "animate-pulse" : undefined}
                        >
                          {meta.label}
                        </Badge>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Next up</CardTitle>
              <CardDescription>Highest priority open tasks</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/dashboard/tasks">
                Board <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {tasks.filter((t) => t.status !== "done").length === 0 ? (
              <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                <ListChecks className="mx-auto mb-2 h-6 w-6" />
                Nothing pending. Nice work!
              </div>
            ) : (
              <ul className="space-y-3">
                {tasks
                  .filter((t) => t.status !== "done")
                  .slice(0, 5)
                  .map((t) => {
                    const due = taskDueMeta(t.due_date, t.status);
                    return (
                      <li key={t.id} className="flex items-start gap-2 text-sm">
                        <span
                          className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${TASK_PRIORITY_META[t.priority].dot}`}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate">{t.title}</p>
                          {due && (
                            <p
                              className={
                                due.overdue
                                  ? "text-xs text-rose-400"
                                  : "text-xs text-muted-foreground"
                              }
                            >
                              {due.overdue ? "Overdue · " : "Due "}
                              {due.label}
                            </p>
                          )}
                        </div>
                        <MemberAvatar
                          member={t.assignee_id ? byId[t.assignee_id] : undefined}
                          size="xs"
                          className="mt-0.5"
                        />
                      </li>
                    );
                  })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">How it works</CardTitle>
          <CardDescription>
            Phases 1 &amp; 2 are live: audio in, structured outcomes out —
            editable by your team.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          {[
            {
              icon: Upload,
              title: "1. Upload",
              text: "Drop an audio or video recording of your meeting.",
            },
            {
              icon: FileText,
              title: "2. Analyse",
              text: "Whisper transcribes; the LLM extracts decisions and action items.",
            },
            {
              icon: KanbanSquare,
              title: "3. Execute",
              text: "Action items land on the task board, linked back to the meeting.",
            },
          ].map((step) => (
            <div key={step.title} className="rounded-lg border bg-muted/30 p-4">
              <step.icon className="h-5 w-5 text-accent" />
              <p className="mt-3 text-sm font-medium">{step.title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{step.text}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
