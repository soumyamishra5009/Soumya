"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AudioLines,
  Loader2,
  Plus,
  Upload,
  X,
  FileAudio,
  Users,
  Clock,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { api, ApiError } from "@/lib/api";
import type { Meeting } from "@/lib/types";
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  MEETING_STATUS_META,
  formatMinutes,
  isMeetingBusy,
  relativeTime,
} from "@/lib/format";

const ACCEPT =
  ".mp3,.wav,.m4a,.flac,.ogg,.opus,.webm,.mp4,.aac,.mov,.mkv,audio/*,video/*";

export default function MeetingsPage() {
  const { workspace } = useAuth();
  const router = useRouter();

  const [meetings, setMeetings] = React.useState<Meeting[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);

  // form state
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [participants, setParticipants] = React.useState("");
  const [meetingDate, setMeetingDate] = React.useState("");
  const [consent, setConsent] = React.useState(false);
  const [file, setFile] = React.useState<File | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [dragging, setDragging] = React.useState(false);

  const load = React.useCallback(async () => {
    if (!workspace) return;
    setLoading(true);
    setError(null);
    try {
      setMeetings(await api.listMeetings(workspace.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load meetings");
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  React.useEffect(() => {
    void load();
  }, [load]);

  // Keep polling while any meeting is processing
  React.useEffect(() => {
    const anyBusy = meetings.some((m) => isMeetingBusy(m.status));
    if (!anyBusy) return;
    const t = setTimeout(() => void load(), 3000);
    return () => clearTimeout(t);
  }, [meetings, load]);

  function resetForm() {
    setTitle("");
    setDescription("");
    setParticipants("");
    setMeetingDate("");
    setConsent(false);
    setFile(null);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!workspace || submitting) return;
    if (!title.trim()) {
      toast.error("Give the meeting a title");
      return;
    }
    if (!file) {
      toast.error("Attach an audio or video recording");
      return;
    }
    if (!consent) {
      toast.error("Please confirm participant consent");
      return;
    }

    setSubmitting(true);
    try {
      const meeting = await api.createMeeting({
        workspace_id: workspace.id,
        title: title.trim(),
        description: description.trim() || null,
        meeting_date: meetingDate ? new Date(meetingDate).toISOString() : null,
        participants: participants
          .split(",")
          .map((p) => p.trim())
          .filter(Boolean),
        consent_confirmed: true,
      });

      await api.uploadAudio(meeting.id, file);
      await api.processMeeting(meeting.id);

      toast.success("Uploaded — transcription started");
      resetForm();
      setCreating(false);
      router.push(`/dashboard/meetings/${meeting.id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Meetings</h2>
          <p className="text-muted-foreground">
            Upload recordings and turn them into decisions and tasks.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="icon" aria-label="Refresh" onClick={() => void load()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => setCreating((v) => !v)}>
            {creating ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {creating ? "Cancel" : "New meeting"}
          </Button>
        </div>
      </div>

      {creating && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">New meeting</CardTitle>
            <CardDescription>
              We transcribe the audio, then extract a summary, decisions and
              action items.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="m-title">Title *</Label>
                  <Input
                    id="m-title"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Sprint planning — week 42"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="m-date">Meeting date</Label>
                  <Input
                    id="m-date"
                    type="datetime-local"
                    value={meetingDate}
                    onChange={(e) => setMeetingDate(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="m-participants">Participants</Label>
                <Input
                  id="m-participants"
                  value={participants}
                  onChange={(e) => setParticipants(e.target.value)}
                  placeholder="Parth, Saumya, Rahul (comma separated)"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="m-desc">Notes / agenda</Label>
                <Textarea
                  id="m-desc"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional context to help the AI."
                  rows={2}
                />
              </div>

              {/* Drop zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  const f = e.dataTransfer.files?.[0];
                  if (f) setFile(f);
                }}
                className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                  dragging ? "border-primary bg-primary/5" : "border-input"
                }`}
              >
                {file ? (
                  <div className="flex items-center gap-3">
                    <FileAudio className="h-6 w-6 text-accent" />
                    <div className="text-left">
                      <p className="text-sm font-medium">{file.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {(file.size / (1024 * 1024)).toFixed(1)} MB
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label="Remove file"
                      onClick={() => setFile(null)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ) : (
                  <>
                    <Upload className="h-6 w-6 text-muted-foreground" />
                    <p className="mt-2 text-sm">
                      Drag & drop audio/video, or{" "}
                      <label className="cursor-pointer font-medium text-primary hover:underline">
                        browse
                        <input
                          type="file"
                          accept={ACCEPT}
                          className="hidden"
                          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                        />
                      </label>
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      mp3, wav, m4a, flac, ogg, webm, mp4 — up to 100 MB
                    </p>
                  </>
                )}
              </div>

              <label className="flex items-start gap-3 rounded-lg border bg-muted/30 p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                <span className="text-muted-foreground">
                  I confirm all participants consented to being recorded and
                  analysed. Required before processing.
                </span>
              </label>

              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    resetForm();
                    setCreating(false);
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4" />
                  )}
                  {submitting ? "Uploading…" : "Upload & analyse"}
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
      ) : meetings.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <AudioLines className="h-10 w-10 text-muted-foreground" />
            <p className="mt-4 font-medium">No meetings yet</p>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              Upload your first recording to see the full pipeline in action.
            </p>
            <Button className="mt-4" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" />
              New meeting
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {meetings.map((m) => {
            const meta = MEETING_STATUS_META[m.status];
            return (
              <Link key={m.id} href={`/dashboard/meetings/${m.id}`}>
                <Card className="h-full transition-colors hover:border-primary/50">
                  <CardHeader className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle className="line-clamp-2 text-base">
                        {m.title}
                      </CardTitle>
                      <Badge
                        variant={meta.variant}
                        className={meta.pulse ? "animate-pulse shrink-0" : "shrink-0"}
                      >
                        {meta.label}
                      </Badge>
                    </div>
                    {m.description && (
                      <CardDescription className="line-clamp-2">
                        {m.description}
                      </CardDescription>
                    )}
                  </CardHeader>
                  <CardContent className="space-y-3 text-xs text-muted-foreground">
                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                      <span className="inline-flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        {m.audio_duration_seconds
                          ? formatMinutes(m.audio_duration_seconds)
                          : relativeTime(m.created_at)}
                      </span>
                      {m.participants && m.participants.length > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <Users className="h-3.5 w-3.5" />
                          {m.participants.length}
                        </span>
                      )}
                      {m.language && (
                        <span className="uppercase">{m.language}</span>
                      )}
                    </div>
                    {m.summary && (
                      <p className="line-clamp-2 text-muted-foreground">
                        {m.summary}
                      </p>
                    )}
                    {m.error_message && (
                      <p className="line-clamp-2 text-rose-400">
                        {m.error_message}
                      </p>
                    )}
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
