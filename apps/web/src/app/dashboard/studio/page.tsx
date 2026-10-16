"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { loader } from "@monaco-editor/react";
import {
  ArrowLeft,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  File as FileIcon,
  FilePlus2,
  FolderPlus,
  Folder,
  FolderOpen,
  Loader2,
  MessageSquare,
  Play,
  RefreshCw,
  Save,
  ScanLine,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { api, ApiError } from "@/lib/api";
import type {
  ChatSuggestion,
  CodeProposal,
  LintFinding,
  Meeting,
  StudioFile,
  StudioFileNode,
  StudioTree,
  Task,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

// Serve Monaco from our own bundle instead of a CDN, so the studio works
// offline. The assets are produced by `scripts/copy-monaco.mjs`.
if (typeof window !== "undefined") {
  loader.config({ paths: { vs: "/monaco/vs" } });
}

const MonacoEditor = dynamic(
  () => import("@monaco-editor/react").then((m) => m.default),
  { ssr: false, loading: () => <EditorLoading /> }
);
const MonacoDiff = dynamic(
  () => import("@monaco-editor/react").then((m) => m.DiffEditor),
  { ssr: false, loading: () => <EditorLoading /> }
);

const EDITOR_OPTIONS = {
  minimap: { enabled: false },
  fontSize: 13,
  scrollBeyondLastLine: false,
  automaticLayout: true,
  tabSize: 4,
  renderWhitespace: "selection" as const,
  smoothScrolling: true,
  padding: { top: 12 },
};

interface OpenTab {
  path: string;
  language: string;
  content: string;
  saved: string;
  hash: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  source?: string;
  suggestions?: ChatSuggestion[];
}

const SEVERITY_STYLE: Record<string, string> = {
  high: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  medium: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  low: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  info: "border-muted-foreground/30 bg-muted/30 text-muted-foreground",
};

function EditorLoading() {
  return (
    <div className="flex h-full items-center justify-center">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
    </div>
  );
}

function tabKey(path: string) {
  return path.split("/").pop() ?? path;
}

export default function StudioPage() {
  const { workspace } = useAuth();

  const [tree, setTree] = React.useState<StudioTree | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [seeding, setSeeding] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState<Set<string>>(new Set());

  const [tabs, setTabs] = React.useState<OpenTab[]>([]);
  const [activePath, setActivePath] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);

  const [proposals, setProposals] = React.useState<CodeProposal[]>([]);
  const [reviewing, setReviewing] = React.useState<CodeProposal | null>(null);
  const [deciding, setDeciding] = React.useState(false);

  const [panel, setPanel] = React.useState<"chat" | "changes" | "review">("chat");
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = React.useState("");
  const [sending, setSending] = React.useState(false);

  const [instruction, setInstruction] = React.useState("");
  const [proposing, setProposing] = React.useState(false);

  const [findings, setFindings] = React.useState<LintFinding[] | null>(null);
  const [linting, setLinting] = React.useState(false);

  const [meetings, setMeetings] = React.useState<Meeting[]>([]);
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [linkMeeting, setLinkMeeting] = React.useState("");
  const [linkTask, setLinkTask] = React.useState("");

  const active = React.useMemo(
    () => tabs.find((t) => t.path === activePath) ?? null,
    [tabs, activePath]
  );
  const dirty = active ? active.content !== active.saved : false;

  // ---------------------------------------------------------------- loading

  const loadTree = React.useCallback(async () => {
    if (!workspace) return;
    try {
      setTree(await api.studioTree(workspace.id));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not load the file tree");
    }
  }, [workspace]);

  const loadProposals = React.useCallback(async () => {
    if (!workspace) return;
    try {
      setProposals(await api.studioProposals(workspace.id));
    } catch {
      /* non-fatal */
    }
  }, [workspace]);

  React.useEffect(() => {
    if (!workspace) return;
    setLoading(true);
    setTabs([]);
    setActivePath(null);
    setReviewing(null);
    setFindings(null);
    setMessages([]);
    void Promise.all([loadTree(), loadProposals()]).finally(() => setLoading(false));
  }, [workspace?.id, loadTree, loadProposals]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (!workspace) return;
    api
      .listMeetings(workspace.id)
      .then(setMeetings)
      .catch(() => setMeetings([]));
    api
      .listTasks(workspace.id)
      .then(setTasks)
      .catch(() => setTasks([]));
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // --------------------------------------------------------------- file ops

  async function openFile(path: string) {
    if (!workspace) return;
    const existing = tabs.find((t) => t.path === path);
    if (existing) {
      setActivePath(path);
      setReviewing(null);
      return;
    }
    try {
      const file: StudioFile = await api.studioFile(workspace.id, path);
      setTabs((prev) => [
        ...prev,
        {
          path: file.path,
          language: file.language,
          content: file.content,
          saved: file.content,
          hash: file.hash,
        },
      ]);
      setActivePath(file.path);
      setReviewing(null);
      setFindings(null);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not open the file");
    }
  }

  function closeTab(path: string) {
    setTabs((prev) => {
      const next = prev.filter((t) => t.path !== path);
      if (activePath === path) {
        setActivePath(next.length ? next[next.length - 1].path : null);
      }
      return next;
    });
  }

  function setContent(path: string, content: string) {
    setTabs((prev) => prev.map((t) => (t.path === path ? { ...t, content } : t)));
  }

  async function saveActive() {
    if (!workspace || !active || saving) return;
    setSaving(true);
    try {
      const file = await api.studioSaveFile(workspace.id, active.path, active.content);
      setTabs((prev) =>
        prev.map((t) =>
          t.path === active.path
            ? { ...t, content: file.content, saved: file.content, hash: file.hash }
            : t
        )
      );
      toast.success(`Saved ${active.path}`);
      void loadTree();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not save the file");
    } finally {
      setSaving(false);
    }
  }

  async function createEntry(kind: "file" | "dir") {
    if (!workspace) return;
    const name = window.prompt(
      kind === "file" ? "New file path (e.g. src/utils.ts)" : "New folder path"
    );
    if (!name || !name.trim()) return;
    const path = name.trim().replace(/^\/+/, "");
    try {
      await api.studioCreateEntry(workspace.id, { path, kind, content: "" });
      toast.success(`Created ${path}`);
      await loadTree();
      if (kind === "file") void openFile(path);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create it");
    }
  }

  async function removeEntry(path: string) {
    if (!workspace) return;
    if (!window.confirm(`Delete ${path}? This cannot be undone.`)) return;
    try {
      await api.studioDeleteEntry(workspace.id, path);
      setTabs((prev) => prev.filter((t) => t.path !== path));
      if (activePath === path) setActivePath(null);
      if (reviewing?.file_path === path) setReviewing(null);
      toast.success(`Deleted ${path}`);
      await loadTree();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not delete it");
    }
  }

  async function seedSample() {
    if (!workspace || seeding) return;
    setSeeding(true);
    try {
      const result = await api.studioSeed(workspace.id);
      toast.success(
        result.created.length
          ? `Added ${result.created.length} sample file(s)`
          : "Sample files already present"
      );
      await loadTree();
      if (result.created.includes("src/calculator.py")) {
        await openFile("src/calculator.py");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create the sample project");
    } finally {
      setSeeding(false);
    }
  }

  // ------------------------------------------------------------------ lint

  async function runLint() {
    if (!workspace || !active || linting) return;
    setLinting(true);
    setPanel("review");
    try {
      const result = await api.studioLint(workspace.id, active.path, active.content);
      setFindings(result.findings);
      if (!result.findings.length) toast.success("No issues found by the offline linter");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not review the file");
    } finally {
      setLinting(false);
    }
  }

  // ------------------------------------------------------------------ chat

  const chatContext = React.useCallback(() => {
    return {
      file_path: activePath,
      meeting_id: linkMeeting || null,
      task_id: linkTask || null,
    };
  }, [activePath, linkMeeting, linkTask]);

  async function sendChat(text?: string) {
    if (!workspace || sending) return;
    const message = (text ?? chatInput).trim();
    if (!message) return;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    if (!text) setChatInput("");
    setSending(true);
    try {
      const res = await api.studioChat(workspace.id, { message, ...chatContext(), history });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          source: res.source,
          suggestions: res.suggestions,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ ${err instanceof ApiError ? err.message : "The assistant is unavailable."}`,
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  // ------------------------------------------------------------- proposals

  async function proposeChange(text?: string) {
    if (!workspace || proposing) return;
    const ask = (text ?? instruction).trim();
    if (!ask) {
      toast.error("Describe the change you want");
      return;
    }
    if (!activePath) {
      toast.error("Open a file first");
      return;
    }
    setProposing(true);
    try {
      const proposal = await api.studioCreateProposal(workspace.id, {
        file_path: activePath,
        instruction: ask,
        meeting_id: linkMeeting || null,
        task_id: linkTask || null,
      });
      setProposals((prev) => [proposal, ...prev]);
      setReviewing(proposal);
      setInstruction("");
      toast.success("Proposal ready for review — nothing was written yet");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create the proposal");
    } finally {
      setProposing(false);
    }
  }

  async function decide(proposal: CodeProposal, approve: boolean) {
    if (!workspace || deciding) return;
    setDeciding(true);
    try {
      const result = approve
        ? await api.studioApproveProposal(workspace.id, proposal.id)
        : await api.studioRejectProposal(workspace.id, proposal.id);
      setProposals((prev) => prev.map((p) => (p.id === proposal.id ? result.proposal : p)));
      toast.success(result.message);
      if (approve) {
        await loadTree();
        const open = tabs.find((t) => t.path === proposal.file_path);
        if (!open) {
          await openFile(proposal.file_path);
        } else if (open.content === open.saved) {
          const file = await api.studioFile(workspace.id, proposal.file_path);
          setTabs((prev) =>
            prev.map((t) =>
              t.path === file.path
                ? { ...t, content: file.content, saved: file.content, hash: file.hash }
                : t
            )
          );
        } else {
          toast.warning("This file also has unsaved edits — your buffer was kept.");
        }
      }
      setReviewing(null);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not apply the decision");
    } finally {
      setDeciding(false);
    }
  }

  // Ctrl/Cmd+S saves the active file.
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void saveActive();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const pendingCount = proposals.filter((p) => p.status === "pending").length;

  function toggleDir(path: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  if (!workspace) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        Create a workspace to open the Dev Studio.
      </div>
    );
  }

  return (
    <div className="-m-6 flex h-[calc(100vh-4rem)] flex-col bg-background">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2">
        <div className="flex items-center gap-3">
          <div>
            <h2 className="text-sm font-semibold">Dev Studio</h2>
            <p className="text-xs text-muted-foreground">
              Meeting → Decision → Task → Code → Verification · every AI edit needs your approval
            </p>
          </div>
          {tree && !tree.empty && (
            <Badge variant="outline" className="hidden sm:inline-flex">
              {tree.count} file{tree.count === 1 ? "" : "s"}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void seedSample()} disabled={seeding}>
            {seeding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Sample project
          </Button>
          <Button variant="outline" size="sm" onClick={() => void createEntry("file")}>
            <FilePlus2 className="h-4 w-4" />
            New file
          </Button>
          <Button variant="outline" size="sm" onClick={() => void createEntry("dir")}>
            <FolderPlus className="h-4 w-4" />
            New folder
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Refresh"
            onClick={() => void loadTree()}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* File explorer */}
        <aside className="hidden w-64 flex-col border-r md:flex">
          <div className="border-b px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Explorer
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2 text-sm">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : !tree || tree.empty ? (
              <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                <p className="mb-2">This workspace has no files yet.</p>
                <Button size="sm" className="w-full" onClick={() => void seedSample()}>
                  <Sparkles className="h-4 w-4" />
                  Create sample project
                </Button>
              </div>
            ) : (
              <TreeBranch
                node={tree}
                depth={0}
                collapsed={collapsed}
                onToggle={toggleDir}
                activePath={activePath}
                onOpen={(p) => void openFile(p)}
                onDelete={(p) => void removeEntry(p)}
              />
            )}
          </div>
        </aside>

        {/* Editor / diff */}
        <section className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-1 overflow-x-auto border-b bg-card/30 px-2">
            {tabs.map((t) => (
              <button
                key={t.path}
                onClick={() => {
                  setActivePath(t.path);
                  setReviewing(null);
                }}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 rounded-t border-b-2 px-3 py-2 text-xs transition-colors",
                  t.path === activePath && !reviewing
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                <FileIcon className="h-3.5 w-3.5" />
                {tabKey(t.path)}
                {t.content !== t.saved && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
                <X
                  className="h-3.5 w-3.5 opacity-50 hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(t.path);
                  }}
                />
              </button>
            ))}
            {reviewing && (
              <span className="flex shrink-0 items-center gap-1.5 rounded-t border-b-2 border-amber-500 px-3 py-2 text-xs text-amber-300">
                <ShieldCheck className="h-3.5 w-3.5" />
                Reviewing change
              </span>
            )}
          </div>

          {reviewing ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-amber-500/5 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium">
                    Proposed change to <span className="text-primary">{reviewing.file_path}</span>
                  </p>
                  <p className="truncate text-[11px] text-muted-foreground">
                    {reviewing.rationale || "No rationale provided."}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px]">
                    +{reviewing.added_lines} −{reviewing.removed_lines}
                  </Badge>
                  <Badge
                    variant={reviewing.source === "llm" ? "default" : "outline"}
                    className="text-[10px]"
                  >
                    {reviewing.source === "llm" ? "AI generated" : "offline scaffold"}
                  </Badge>
                  <Button variant="ghost" size="sm" onClick={() => setReviewing(null)}>
                    <ArrowLeft className="h-4 w-4" />
                    Back
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={reviewing.status !== "pending" || deciding}
                    onClick={() => void decide(reviewing, false)}
                  >
                    <X className="h-4 w-4" />
                    Reject
                  </Button>
                  <Button
                    size="sm"
                    disabled={reviewing.status !== "pending" || deciding}
                    onClick={() => void decide(reviewing, true)}
                  >
                    {deciding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                    Approve &amp; write
                  </Button>
                </div>
              </div>
              <div className="min-h-0 flex-1">
                <MonacoDiff
                  original={reviewing.original_content ?? ""}
                  modified={reviewing.proposed_content}
                  language={reviewing.language ?? "plaintext"}
                  theme="vs-dark"
                  options={{ ...EDITOR_OPTIONS, readOnly: true, renderSideBySide: true }}
                />
              </div>
              <div className="border-t px-3 py-2 text-[11px] text-muted-foreground">
                Left: current file on disk · Right: proposed. Nothing is written until you approve.
              </div>
            </div>
          ) : active ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
                <span className="truncate text-xs text-muted-foreground">{active.path}</span>
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="sm" onClick={() => void runLint()} disabled={linting}>
                    {linting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanLine className="h-4 w-4" />}
                    Review
                  </Button>
                  <Button size="sm" onClick={() => void saveActive()} disabled={!dirty || saving}>
                    {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    Save
                  </Button>
                </div>
              </div>
              <div className="min-h-0 flex-1">
                <MonacoEditor
                  path={active.path}
                  language={active.language}
                  value={active.content}
                  theme="vs-dark"
                  options={EDITOR_OPTIONS}
                  onChange={(value) => setContent(active.path, value ?? "")}
                />
              </div>

              {/* Ask the AI to change this file */}
              <div className="flex items-center gap-2 border-t bg-card/30 px-3 py-2">
                <Bot className="h-4 w-4 shrink-0 text-primary" />
                <Input
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void proposeChange();
                  }}
                  placeholder="Ask the AI to change this file (e.g. fix the division-by-zero bug)…"
                  className="h-9"
                />
                <Button size="sm" onClick={() => void proposeChange()} disabled={proposing}>
                  {proposing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  Propose
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
              <ShieldCheck className="h-8 w-8 text-muted-foreground/50" />
              <div>
                <p className="text-sm font-medium">No file open</p>
                <p className="mt-1 max-w-md text-xs text-muted-foreground">
                  Pick a file from the explorer, or create the sample project to walk through the
                  full pipeline: a failing test, an AI-proposed fix, and human approval.
                </p>
              </div>
              <Button onClick={() => void seedSample()} disabled={seeding}>
                {seeding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Create sample project
              </Button>
            </div>
          )}

          {/* Status bar */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-t px-3 py-1 text-[11px] text-muted-foreground">
            <div className="flex items-center gap-3">
              <span>{active?.language ?? "—"}</span>
              {active && <span>{active.content.split("\n").length} lines</span>}
              {dirty && <span className="text-primary">unsaved changes</span>}
            </div>
            <div className="flex items-center gap-3">
              {findings && <span>{findings.length} finding(s)</span>}
              <span>Ctrl/⌘+S to save</span>
            </div>
          </div>
        </section>

        {/* Assistant panel */}
        <aside className="hidden w-96 flex-col border-l lg:flex">
          <div className="flex border-b">
            {(
              [
                ["chat", "Assistant", MessageSquare, 0],
                ["changes", "Changes", ShieldCheck, pendingCount],
                ["review", "Review", ScanLine, findings?.length ?? 0],
              ] as const
            ).map(([id, label, Icon, count]) => (
              <button
                key={id}
                onClick={() => setPanel(id)}
                className={cn(
                  "flex flex-1 items-center justify-center gap-1.5 px-2 py-2 text-xs font-medium transition-colors",
                  panel === id
                    ? "border-b-2 border-primary text-foreground"
                    : "border-b-2 border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
                {count > 0 && (
                  <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                    {count}
                  </Badge>
                )}
              </button>
            ))}
          </div>

          {panel === "chat" && (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
                <span className="text-[11px] text-muted-foreground">Context:</span>
                {activePath ? (
                  <Badge variant="secondary" className="text-[10px]">
                    {tabKey(activePath)}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px]">
                    no file
                  </Badge>
                )}
                <select
                  aria-label="Link meeting"
                  value={linkMeeting}
                  onChange={(e) => setLinkMeeting(e.target.value)}
                  className="h-7 max-w-[9rem] rounded border border-input bg-background px-1.5 text-[11px]"
                >
                  <option value="">no meeting</option>
                  {meetings.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.title}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Link task"
                  value={linkTask}
                  onChange={(e) => setLinkTask(e.target.value)}
                  className="h-7 max-w-[9rem] rounded border border-input bg-background px-1.5 text-[11px]"
                >
                  <option value="">no task</option>
                  {tasks.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.title}
                    </option>
                  ))}
                </select>
              </div>

              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
                {messages.length === 0 && (
                  <div className="space-y-2 rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
                    <p className="font-medium text-foreground">Ask about your code</p>
                    <p>Try one of these:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {[
                        "Explain this file",
                        "Review this file for bugs",
                        "List the TODO markers",
                        "What is in this project?",
                      ].map((q) => (
                        <button
                          key={q}
                          onClick={() => void sendChat(q)}
                          className="rounded-full border px-2 py-1 text-[11px] hover:bg-accent/10"
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={cn(
                      "rounded-lg border p-2.5 text-xs",
                      m.role === "user"
                        ? "ml-6 border-primary/30 bg-primary/10"
                        : "mr-2 bg-card/60"
                    )}
                  >
                    {m.source && (
                      <Badge
                        variant={m.source === "llm" ? "default" : "outline"}
                        className="mb-1.5 text-[10px]"
                      >
                        {m.source === "llm" ? "AI" : "offline"}
                      </Badge>
                    )}
                    <p className="whitespace-pre-wrap break-words">{m.content}</p>
                    {m.suggestions && m.suggestions.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {m.suggestions.map((s, j) => (
                          <button
                            key={j}
                            onClick={() => void proposeChange(s.instruction ?? s.label)}
                            className="rounded-full border border-primary/40 px-2 py-1 text-[11px] text-primary hover:bg-primary/10"
                          >
                            {s.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {sending && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Thinking…
                  </div>
                )}
              </div>

              <div className="flex items-end gap-2 border-t p-3">
                <Textarea
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void sendChat();
                    }
                  }}
                  rows={2}
                  placeholder="Ask about the code…"
                  className="min-h-[2.5rem] resize-none text-xs"
                />
                <Button size="icon" onClick={() => void sendChat()} disabled={sending}>
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}

          {panel === "changes" && (
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {proposals.length === 0 ? (
                <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
                  No change proposals yet. Open a file and ask the AI for a change — you approve
                  every edit before it is written.
                </p>
              ) : (
                <div className="space-y-2">
                  {proposals.map((p) => (
                    <div key={p.id} className="rounded-lg border bg-card/50 p-2.5 text-xs">
                      <div className="flex items-start justify-between gap-2">
                        <span className="truncate font-medium">{p.file_path}</span>
                        <Badge
                          variant={
                            p.status === "pending"
                              ? "default"
                              : p.status === "approved"
                                ? "secondary"
                                : "outline"
                          }
                          className="shrink-0 text-[10px]"
                        >
                          {p.status}
                        </Badge>
                      </div>
                      {p.rationale && (
                        <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">
                          {p.rationale}
                        </p>
                      )}
                      <div className="mt-2 flex items-center gap-2">
                        <Badge variant="outline" className="text-[10px]">
                          +{p.added_lines} −{p.removed_lines}
                        </Badge>
                        <Badge variant="outline" className="text-[10px]">
                          {p.source === "llm" ? "AI" : "offline"}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="ml-auto h-6 px-2 text-[11px]"
                          onClick={() => {
                            setReviewing(p);
                            if (p.status !== "pending") toast.info("This proposal was already decided");
                          }}
                        >
                          View diff
                        </Button>
                      </div>
                      {p.status === "pending" && (
                        <div className="mt-2 flex gap-1.5">
                          <Button
                            size="sm"
                            className="h-6 flex-1 px-2 text-[11px]"
                            disabled={deciding}
                            onClick={() => void decide(p, true)}
                          >
                            <Check className="h-3 w-3" />
                            Approve
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-6 flex-1 px-2 text-[11px]"
                            disabled={deciding}
                            onClick={() => void decide(p, false)}
                          >
                            <X className="h-3 w-3" />
                            Reject
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {panel === "review" && (
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {!active ? (
                <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
                  Open a file, then press Review for offline static analysis.
                </p>
              ) : findings === null ? (
                <Button size="sm" className="w-full" onClick={() => void runLint()} disabled={linting}>
                  {linting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanLine className="h-4 w-4" />}
                  Review {tabKey(active.path)}
                </Button>
              ) : findings.length === 0 ? (
                <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
                  No issues found. 🎉
                </p>
              ) : (
                <div className="space-y-2">
                  <p className="text-[11px] text-muted-foreground">
                    Deterministic analysis — works with no LLM. {findings.length} finding(s).
                  </p>
                  {findings.map((f, i) => (
                    <div
                      key={i}
                      className={cn("rounded-lg border p-2 text-xs", SEVERITY_STYLE[f.severity] ?? "")}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] font-semibold uppercase">{f.severity}</span>
                        <span className="text-[10px] opacity-70">line {f.line}</span>
                      </div>
                      <p className="mt-1">{f.message}</p>
                      {f.snippet && (
                        <pre className="mt-1 overflow-x-auto rounded bg-background/60 p-1.5 text-[10px] opacity-80">
                          {f.snippet}
                        </pre>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="mt-1 h-6 px-2 text-[11px]"
                        onClick={() => void proposeChange(f.message)}
                      >
                        <Bot className="h-3 w-3" />
                        Ask AI to fix
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// File tree
// ---------------------------------------------------------------------------

function TreeBranch({
  node,
  depth,
  collapsed,
  onToggle,
  activePath,
  onOpen,
  onDelete,
}: {
  node: StudioFileNode;
  depth: number;
  collapsed: Set<string>;
  onToggle: (path: string) => void;
  activePath: string | null;
  onOpen: (path: string) => void;
  onDelete: (path: string) => void;
}) {
  const children = node.children ?? [];
  const isRoot = !node.path;

  const rows = (
    <>
      {!isRoot &&
        (node.type === "dir" ? (
          <div
            className="group flex items-center gap-1 rounded px-1 py-1 hover:bg-accent/10"
            style={{ paddingLeft: depth * 12 }}
          >
            <button
              onClick={() => onToggle(node.path)}
              className="flex min-w-0 flex-1 items-center gap-1 text-left"
            >
              {collapsed.has(node.path) ? (
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              )}
              {collapsed.has(node.path) ? (
                <Folder className="h-3.5 w-3.5 shrink-0 text-primary/70" />
              ) : (
                <FolderOpen className="h-3.5 w-3.5 shrink-0 text-primary/70" />
              )}
              <span className="truncate">{node.name}</span>
            </button>
            <button
              aria-label={`Delete ${node.path}`}
              onClick={() => onDelete(node.path)}
              className="shrink-0 rounded p-0.5 text-muted-foreground/40 opacity-0 hover:text-rose-400 group-hover:opacity-100"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <div
            className={cn(
              "group flex items-center gap-1 rounded px-1 py-1",
              activePath === node.path ? "bg-primary/15 text-primary" : "hover:bg-accent/10"
            )}
            style={{ paddingLeft: depth * 12 }}
          >
            <button
              onClick={() => (node.editable ? onOpen(node.path) : undefined)}
              disabled={!node.editable}
              title={node.editable ? node.path : "Binary or unsupported file"}
              className="flex min-w-0 flex-1 items-center gap-1 text-left disabled:opacity-50"
            >
              <span className="w-3.5 shrink-0" />
              <FileIcon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate">{node.name}</span>
            </button>
            <button
              aria-label={`Delete ${node.path}`}
              onClick={() => onDelete(node.path)}
              className="shrink-0 rounded p-0.5 text-muted-foreground/40 opacity-0 hover:text-rose-400 group-hover:opacity-100"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
    </>
  );

  return (
    <>
      {rows}
      {node.type === "dir" && !collapsed.has(node.path) &&
        children.map((child) => (
          <TreeBranch
            key={child.path}
            node={child}
            depth={isRoot ? 0 : depth + 1}
            collapsed={collapsed}
            onToggle={onToggle}
            activePath={activePath}
            onOpen={onOpen}
            onDelete={onDelete}
          />
        ))}
    </>
  );
}
