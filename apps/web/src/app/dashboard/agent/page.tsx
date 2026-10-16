"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Check,
  Code2,
  FlaskConical,
  GitBranch,
  GitCommitVertical,
  GitMerge,
  GitPullRequest,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Rocket,
  Sparkles,
  Trash2,
  Terminal,
  TriangleAlert,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { api, ApiError } from "@/lib/api";
import type {
  CodePlan,
  CodeProposal,
  GitCommit,
  GitDiff,
  GitStatus,
  Meeting,
  PullRequest,
  RepoConnection,
  TestRun,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

function errMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

const PR_VARIANT: Record<
  PullRequest["status"],
  "default" | "secondary" | "success" | "warning" | "destructive" | "info" | "outline"
> = {
  draft: "outline",
  open: "info",
  merged: "success",
  closed: "secondary",
  failed: "destructive",
};

const RUN_VARIANT: Record<
  TestRun["status"],
  "default" | "secondary" | "success" | "warning" | "destructive" | "info" | "outline"
> = {
  passed: "success",
  failed: "destructive",
  error: "warning",
  timeout: "warning",
};

const KIND_VARIANT: Record<string, "info" | "warning" | "success" | "outline"> = {
  code: "info",
  test: "warning",
  docs: "outline",
  review: "success",
};

export default function AgentPage() {
  const { workspace } = useAuth();
  const workspaceId = workspace?.id ?? "";

  const [meetings, setMeetings] = React.useState<Meeting[]>([]);
  const [meetingId, setMeetingId] = React.useState("");
  const [focus, setFocus] = React.useState("");

  const [plan, setPlan] = React.useState<CodePlan | null>(null);
  const [busyPlan, setBusyPlan] = React.useState(false);
  const [busyApply, setBusyApply] = React.useState(false);
  const [applied, setApplied] = React.useState<CodeProposal[]>([]);

  const [repos, setRepos] = React.useState<RepoConnection[]>([]);
  const [repoInput, setRepoInput] = React.useState("");
  const [git, setGit] = React.useState<GitStatus | null>(null);
  const [diff, setDiff] = React.useState<GitDiff | null>(null);
  const [showDiff, setShowDiff] = React.useState(false);
  const [commits, setCommits] = React.useState<GitCommit[]>([]);
  const [prs, setPrs] = React.useState<PullRequest[]>([]);
  const [prTitle, setPrTitle] = React.useState("");
  const [prBody, setPrBody] = React.useState("");
  const [shipOnlyPlan, setShipOnlyPlan] = React.useState(true);
  const [busy, setBusy] = React.useState(false);

  const [runs, setRuns] = React.useState<TestRun[]>([]);
  const [latest, setLatest] = React.useState<TestRun | null>(null);
  const [runBusy, setRunBusy] = React.useState(false);
  const [runTarget, setRunTarget] = React.useState("");

  const loadShip = React.useCallback(async () => {
    if (!workspaceId) return;
    try {
      const [g, list, log] = await Promise.all([
        api.gitStatus(workspaceId),
        api.listPullRequests(workspaceId),
        api.gitLog(workspaceId, 10),
      ]);
      setGit(g);
      setPrs(list);
      setCommits(log);
    } catch (err) {
      toast.error(errMessage(err, "Could not load the ship state"));
    }
  }, [workspaceId]);

  const loadRuns = React.useCallback(async () => {
    if (!workspaceId) return;
    try {
      const list = await api.listTestRuns(workspaceId, undefined);
      setRuns(list);
      setLatest(list[0] ?? null);
    } catch {
      /* non-fatal */
    }
  }, [workspaceId]);

  const loadRepos = React.useCallback(async () => {
    if (!workspaceId) return;
    try {
      setRepos(await api.listRepos(workspaceId));
    } catch {
      /* non-fatal */
    }
  }, [workspaceId]);

  React.useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listMeetings(workspaceId, { archived: false });
        if (cancelled) return;
        setMeetings(list);
        if (list.length && !meetingId) setMeetingId(list[0].id);
      } catch {
        /* non-fatal */
      }
    })();
    void loadRepos();
    void loadShip();
    void loadRuns();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const generatePlan = async () => {
    if (!workspaceId) return;
    setBusyPlan(true);
    setApplied([]);
    try {
      const created = await api.agentPlan(workspaceId, {
        meeting_id: meetingId || null,
        focus: focus.trim() || null,
      });
      setPlan(created);
      if (!prTitle) setPrTitle(created.title);
      toast.success(
        created.source === "llm"
          ? "Plan generated"
          : "Offline plan generated (no LLM reachable)"
      );
    } catch (err) {
      toast.error(errMessage(err, "Could not generate a plan"));
    } finally {
      setBusyPlan(false);
    }
  };

  const applyPlan = async () => {
    if (!workspaceId || !plan) return;
    setBusyApply(true);
    try {
      const result = await api.applyPlan(workspaceId, plan.id);
      setPlan(result.plan);
      const pending = await api.studioProposals(workspaceId, "pending");
      setApplied(pending.filter((p) => result.proposal_ids.includes(p.id)));
      toast.success(result.message);
    } catch (err) {
      toast.error(errMessage(err, "Could not create change proposals"));
    } finally {
      setBusyApply(false);
    }
  };

  const decideProposal = async (proposal: CodeProposal, approve: boolean) => {
    if (!workspaceId) return;
    try {
      if (approve) {
        await api.studioApproveProposal(workspaceId, proposal.id);
        toast.success(`Applied ${proposal.file_path}`);
      } else {
        await api.studioRejectProposal(workspaceId, proposal.id);
        toast.message(`Rejected ${proposal.file_path}`);
      }
      setApplied((prev) =>
        prev.map((p) =>
          p.id === proposal.id
            ? { ...p, status: approve ? "approved" : "rejected" }
            : p
        )
      );
      await loadShip();
    } catch (err) {
      toast.error(errMessage(err, "Could not record the decision"));
    }
  };

  const runTests = async () => {
    if (!workspaceId) return;
    setRunBusy(true);
    try {
      const result = await api.runTests(workspaceId, {
        target: runTarget.trim() || undefined,
      });
      setLatest(result);
      setRuns((prev) => [result, ...prev]);
      if (result.status === "passed") {
        toast.success(result.summary);
      } else if (result.status === "failed") {
        toast.error(result.summary);
      } else {
        toast.message(result.summary);
      }
      await loadShip();
    } catch (err) {
      toast.error(errMessage(err, "Could not run the tests"));
    } finally {
      setRunBusy(false);
    }
  };

  const connectLocal = async () => {
    if (!workspaceId) return;
    setBusy(true);
    try {
      await api.connectRepo(workspaceId, { provider: "local" });
      toast.success("Local sandbox connected");
      await loadRepos();
      await loadShip();
    } catch (err) {
      toast.error(errMessage(err, "Could not connect the local sandbox"));
    } finally {
      setBusy(false);
    }
  };

  const connectGithub = async () => {
    if (!workspaceId || !repoInput.trim()) return;
    setBusy(true);
    try {
      await api.connectRepo(workspaceId, {
        provider: "github",
        repo_full_name: repoInput.trim(),
      });
      toast.success("GitHub repository connected");
      setRepoInput("");
      await loadRepos();
    } catch (err) {
      toast.error(errMessage(err, "Could not connect the repository"));
    } finally {
      setBusy(false);
    }
  };

  const checkRepo = async (repo: RepoConnection) => {
    if (!workspaceId) return;
    try {
      const result = await api.checkRepo(workspaceId, repo.id);
      if (result.ok) toast.success(result.message);
      else toast.warning(result.message);
    } catch (err) {
      toast.error(errMessage(err, "Could not check the repository"));
    }
  };

  const createPr = async () => {
    if (!workspaceId || !prTitle.trim()) {
      toast.error("Give the pull request a title");
      return;
    }
    setBusy(true);
    try {
      const github = repos.find((r) => r.provider === "github");
      const proposalIds =
        shipOnlyPlan && plan ? plan.proposal_ids.filter((id) => applied.some((p) => p.id === id && p.status === "approved")) : [];
      const pr = await api.createPullRequest(workspaceId, {
        title: prTitle.trim(),
        body: prBody.trim() || null,
        provider: github ? "github" : "local",
        repo_id: github ? github.id : null,
        base_branch: github ? github.default_branch : "main",
        meeting_id: plan?.meeting_id ?? (meetingId || null),
        proposal_ids: proposalIds,
      });
      toast.success("Draft pull request created — review the diff, then open it");
      setPrs((prev) => [pr, ...prev]);
      setPrBody("");
    } catch (err) {
      toast.error(errMessage(err, "Could not create the pull request"));
    } finally {
      setBusy(false);
    }
  };

  const act = async (pr: PullRequest, action: "open" | "merge" | "close") => {
    if (!workspaceId) return;
    try {
      const fn =
        action === "open"
          ? api.openPullRequest
          : action === "merge"
            ? api.mergePullRequest
            : api.closePullRequest;
      const result = await fn(workspaceId, pr.id);
      toast.success(result.message);
      setPrs((prev) => prev.map((p) => (p.id === pr.id ? result.proposal : p)));
      await loadShip();
    } catch (err) {
      toast.error(errMessage(err, `Could not ${action} the pull request`));
      await loadShip();
    }
  };

  const viewDiff = async () => {
    if (!workspaceId) return;
    if (showDiff) {
      setShowDiff(false);
      return;
    }
    try {
      setDiff(await api.gitDiff(workspaceId));
      setShowDiff(true);
    } catch (err) {
      toast.error(errMessage(err, "Could not load the diff"));
    }
  };

  const removeRepo = async (repo: RepoConnection) => {
    if (!workspaceId) return;
    try {
      await api.deleteRepo(workspaceId, repo.id);
      setRepos((prev) => prev.filter((r) => r.id !== repo.id));
      toast.message("Repository disconnected");
    } catch (err) {
      toast.error(errMessage(err, "Could not disconnect the repository"));
    }
  };

  if (!workspace) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto grid max-w-7xl gap-6 xl:grid-cols-2">
      {/* ---------------------------------------------------- Meeting → Code */}
      <div className="space-y-6">
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Bot className="h-5 w-5 text-primary" />
              Meeting → Code
            </CardTitle>
            <Badge variant="outline">agent</Badge>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Turn a meeting&apos;s decisions into requirements, subtasks and the files
              that need editing — then into reviewable change proposals.
            </p>

            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Meeting
                </label>
                <select
                  aria-label="Meeting"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={meetingId}
                  onChange={(e) => setMeetingId(e.target.value)}
                >
                  <option value="">Latest meeting (or none)</option>
                  {meetings.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.title}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-end">
                <Button onClick={generatePlan} disabled={busyPlan}>
                  {busyPlan ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  Generate plan
                </Button>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                Extra focus (optional)
              </label>
              <Input
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                placeholder="e.g. also make the API rate-limit aware"
              />
            </div>
          </CardContent>
        </Card>

        {plan && (
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="text-lg">{plan.title}</CardTitle>
                {plan.summary && (
                  <p className="mt-1 text-sm text-muted-foreground">{plan.summary}</p>
                )}
              </div>
              <Badge variant={plan.source === "llm" ? "success" : "warning"}>
                {plan.source === "llm" ? "AI plan" : "offline plan"}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-5">
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Requirements
                </h3>
                <ul className="space-y-1.5">
                  {plan.requirements.map((req, i) => (
                    <li key={i} className="flex gap-2 text-sm">
                      <span className="text-primary">•</span>
                      <span>{req}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Subtasks
                </h3>
                <ul className="space-y-2">
                  {plan.subtasks.map((task, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <Badge variant={KIND_VARIANT[task.kind] ?? "outline"}>
                        {task.kind}
                      </Badge>
                      <span className="flex-1">{task.title}</span>
                    </li>
                  ))}
                </ul>
              </section>

              {plan.affected_files.length > 0 && (
                <section>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Affected files
                  </h3>
                  <ul className="space-y-1.5">
                    {plan.affected_files.map((f) => (
                      <li key={f.path} className="flex items-center gap-2 text-sm">
                        <Code2 className="h-3.5 w-3.5 text-muted-foreground" />
                        <code className="flex-1 truncate">{f.path}</code>
                        <span
                          className="truncate text-xs text-muted-foreground"
                          title={f.reason}
                        >
                          {f.reason}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <div className="flex flex-wrap items-center gap-3 border-t pt-4">
                {plan.status === "draft" ? (
                  <Button onClick={applyPlan} disabled={busyApply}>
                    {busyApply ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <ArrowRight className="h-4 w-4" />
                    )}
                    Create change proposals
                  </Button>
                ) : (
                  <Badge variant="success">plan applied</Badge>
                )}
                <Link
                  href="/dashboard/studio"
                  className="text-sm text-primary underline-offset-4 hover:underline"
                >
                  Open Dev Studio →
                </Link>
              </div>

              {applied.length > 0 && (
                <div className="space-y-2 rounded-md border bg-muted/30 p-3">
                  <p className="text-xs text-muted-foreground">
                    Proposals are <strong>pending</strong> — approve each one to write it
                    to the sandbox. Nothing is applied automatically.
                  </p>
                  {applied.map((p) => (
                    <div
                      key={p.id}
                      className="flex items-center gap-3 rounded-md border bg-background p-2 text-sm"
                    >
                      <code className="flex-1 truncate">{p.file_path}</code>
                      <span className="font-mono text-xs text-emerald-400">
                        +{p.added_lines}
                      </span>
                      <span className="font-mono text-xs text-rose-400">
                        −{p.removed_lines}
                      </span>
                      {p.status === "pending" ? (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => decideProposal(p, false)}
                          >
                            <X className="h-3.5 w-3.5" />
                          </Button>
                          <Button size="sm" onClick={() => decideProposal(p, true)}>
                            <Check className="h-3.5 w-3.5" />
                            Approve
                          </Button>
                        </>
                      ) : (
                        <Badge variant={p.status === "approved" ? "success" : "secondary"}>
                          {p.status}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* ------------------------------------------------------------- Ship it */}
      <div className="space-y-6">
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Rocket className="h-5 w-5 text-primary" />
              Ship it
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={() => void loadShip()}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* repositories */}
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Repositories
              </h3>
              {repos.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No repository connected. The local sandbox works offline.
                </p>
              ) : (
                <ul className="space-y-2">
                  {repos.map((repo) => (
                    <li
                      key={repo.id}
                      className="flex items-center gap-2 rounded-md border p-2 text-sm"
                    >
                      <Badge variant={repo.provider === "github" ? "info" : "secondary"}>
                        {repo.provider}
                      </Badge>
                      <span className="flex-1 truncate">
                        {repo.repo_full_name || repo.name}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => void checkRepo(repo)}
                      >
                        Check
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Disconnect"
                        onClick={() => void removeRepo(repo)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={connectLocal}
                  disabled={busy || repos.some((r) => r.provider === "local")}
                >
                  <Plus className="h-4 w-4" />
                  Local sandbox
                </Button>
                <Input
                  className="h-9 max-w-[200px]"
                  placeholder="owner/repo"
                  value={repoInput}
                  onChange={(e) => setRepoInput(e.target.value)}
                />
                <Button size="sm" variant="outline" onClick={connectGithub} disabled={busy}>
                  Connect GitHub
                </Button>
              </div>
            </div>

            {/* git status */}
            <div className="space-y-2 border-t pt-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Working tree
                </h3>
                {git && (
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">
                      <GitBranch className="mr-1 h-3 w-3" />
                      {git.branch ?? "—"}
                    </Badge>
                    <Badge variant={git.clean ? "success" : "warning"}>
                      {git.clean ? "clean" : `${git.changed_files.length} changed`}
                    </Badge>
                  </div>
                )}
              </div>

              {!git?.initialized ? (
                <p className="text-sm text-muted-foreground">
                  The sandbox repository is created the first time you look here.
                </p>
              ) : git.changed_files.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No uncommitted changes. Approve a proposal, then create a pull request.
                </p>
              ) : (
                <ul className="space-y-1">
                  {git.changed_files.map((f) => (
                    <li key={f.path} className="flex items-center gap-2 text-sm">
                      <code className="flex-1 truncate">{f.path}</code>
                      <Badge variant="outline">{f.status}</Badge>
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" onClick={() => void viewDiff()}>
                  {showDiff ? "Hide diff" : "View diff"}
                </Button>
                {git && (
                  <span className="text-xs text-muted-foreground">
                    {git.commit_count} commit(s) · {git.branches.length} branch(es)
                  </span>
                )}
              </div>

              {showDiff && diff && (
                <pre className="max-h-72 overflow-auto rounded-md border bg-muted/40 p-3 text-xs leading-relaxed">
                  {diff.diff.trim() || "(no changes)"}
                </pre>
              )}
            </div>

            {/* new PR proposal */}
            <div className="space-y-2 border-t pt-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                New pull-request proposal
              </h3>
              <Input
                placeholder="Title, e.g. Guard divide-by-zero"
                value={prTitle}
                onChange={(e) => setPrTitle(e.target.value)}
              />
              <Textarea
                placeholder="Describe the change (optional)"
                rows={2}
                value={prBody}
                onChange={(e) => setPrBody(e.target.value)}
              />
              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={createPr} disabled={busy}>
                  <GitPullRequest className="h-4 w-4" />
                  Create draft
                </Button>
                {plan && applied.some((p) => p.status === "approved") && (
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={shipOnlyPlan}
                      onChange={(e) => setShipOnlyPlan(e.target.checked)}
                    />
                    only this plan&apos;s changes
                  </label>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* PR list */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Pull requests</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {prs.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing proposed yet.</p>
            ) : (
              prs.map((pr) => (
                <div key={pr.id} className="space-y-2 rounded-md border p-3">
                  <div className="flex items-start gap-2">
                    <Badge variant={PR_VARIANT[pr.status]}>{pr.status}</Badge>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{pr.title}</p>
                      <p className="truncate font-mono text-xs text-muted-foreground">
                        {pr.branch_name} → {pr.base_branch}
                      </p>
                    </div>
                    <span className="whitespace-nowrap text-xs text-muted-foreground">
                      {pr.file_count} file(s) · <span className="text-emerald-400">+{pr.added_lines}</span>{" "}
                      <span className="text-rose-400">−{pr.removed_lines}</span>
                    </span>
                  </div>

                  {pr.error && (
                    <p className="flex items-start gap-1.5 text-xs text-destructive">
                      <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      {pr.error}
                    </p>
                  )}

                  {pr.commit_sha && (
                    <p className="flex items-center gap-1 font-mono text-xs text-muted-foreground">
                      <GitCommitVertical className="h-3.5 w-3.5" />
                      {pr.commit_sha.slice(0, 8)}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center gap-2">
                    {(pr.status === "draft" || pr.status === "failed") && (
                      <Button size="sm" onClick={() => void act(pr, "open")}>
                        <Rocket className="h-3.5 w-3.5" />
                        Open
                      </Button>
                    )}
                    {pr.status === "open" && (
                      <Button size="sm" onClick={() => void act(pr, "merge")}>
                        <GitMerge className="h-3.5 w-3.5" />
                        Merge
                      </Button>
                    )}
                    {(pr.status === "draft" ||
                      pr.status === "open" ||
                      pr.status === "failed") && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void act(pr, "close")}
                      >
                        Close
                      </Button>
                    )}
                    {pr.external_url && (
                      <a
                        href={pr.external_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-primary underline-offset-4 hover:underline"
                      >
                        PR #{pr.external_number} ↗
                      </a>
                    )}
                  </div>

                  {pr.diff && (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-muted-foreground">
                        View snapshot diff
                      </summary>
                      <pre className="mt-2 max-h-56 overflow-auto rounded border bg-muted/40 p-2">
                        {pr.diff}
                      </pre>
                    </details>
                  )}
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* commits */}
        {commits.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Recent commits</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {commits.map((c) => (
                  <li key={c.sha} className="flex items-center gap-2 text-sm">
                    <code className="text-xs text-muted-foreground">
                      {c.sha.slice(0, 8)}
                    </code>
                    <span className={cn("flex-1 truncate")}>{c.message}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {c.author_name}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {/* verify: sandboxed test runs */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2 text-lg">
              <FlaskConical className="h-5 w-5 text-primary" />
              Verify — sandboxed tests
            </CardTitle>
            <Badge variant="outline">Phase 5</Badge>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Run the workspace&apos;s tests inside the Dev Studio sandbox before
              shipping. The runner is bundled and works fully offline; nothing
              leaves the sandbox.
            </p>

            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Target (optional)
                </label>
                <Input
                  value={runTarget}
                  onChange={(e) => setRunTarget(e.target.value)}
                  placeholder="e.g. tests/test_calculator.py"
                />
              </div>
              <div className="flex items-end">
                <Button onClick={runTests} disabled={runBusy}>
                  {runBusy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  Run tests
                </Button>
              </div>
            </div>

            {latest && (
              <div className="space-y-3 rounded-md border bg-muted/30 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={RUN_VARIANT[latest.status]}>
                    {latest.status}
                  </Badge>
                  <span className="text-sm font-medium">{latest.summary}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {latest.runner} · {latest.duration_ms} ms · {latest.passed}/
                    {latest.failed}/{latest.errors}
                  </span>
                </div>
                {latest.output && (
                  <details>
                    <summary className="flex cursor-pointer items-center gap-1 text-xs font-medium text-muted-foreground">
                      <Terminal className="h-3.5 w-3.5" />
                      Show output
                    </summary>
                    <pre className="mt-2 max-h-64 overflow-auto rounded border bg-background p-2 text-xs">
                      {latest.output}
                    </pre>
                  </details>
                )}
              </div>
            )}

            {runs.length > 0 && (
              <div className="space-y-1">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Recent runs
                </h3>
                <ul className="space-y-1">
                  {runs.slice(0, 5).map((r) => (
                    <li
                      key={r.id}
                      className="flex items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-muted/40"
                    >
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          r.status === "passed" && "bg-emerald-500",
                          r.status === "failed" && "bg-rose-500",
                          (r.status === "error" || r.status === "timeout") &&
                            "bg-amber-500"
                        )}
                      />
                      <span className="font-mono text-xs text-muted-foreground">
                        {new Date(r.created_at).toLocaleTimeString()}
                      </span>
                      <span className="flex-1 truncate text-xs text-muted-foreground">
                        {r.command}
                      </span>
                      <span className="text-xs">
                        {r.passed}✓ / {r.failed}✗
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
