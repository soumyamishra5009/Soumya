"use client";

import * as React from "react";
import {
  Brain,
  Database,
  FileText,
  FolderTree,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { api, ApiError } from "@/lib/api";
import type {
  MemoryHit,
  MemoryIndexResult,
  MemorySearchResult,
  MemoryStats,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

function errMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

const SOURCE_VARIANT: Record<string, "default" | "secondary" | "success" | "warning" | "info" | "outline"> = {
  meeting: "info",
  decision: "success",
  task: "warning",
  file: "secondary",
  note: "outline",
};

export default function MemoryPage() {
  const { workspace } = useAuth();
  const workspaceId = workspace?.id ?? "";

  const [stats, setStats] = React.useState<MemoryStats | null>(null);
  const [query, setQuery] = React.useState("");
  const [result, setResult] = React.useState<MemorySearchResult | null>(null);
  const [indexing, setIndexing] = React.useState(false);
  const [searching, setSearching] = React.useState(false);
  const [includeCode, setIncludeCode] = React.useState(true);
  const [force, setForce] = React.useState(false);
  const [clearing, setClearing] = React.useState(false);

  const loadStats = React.useCallback(async () => {
    if (!workspaceId) return;
    try {
      setStats(await api.memoryStats(workspaceId));
    } catch {
      /* non-fatal */
    }
  }, [workspaceId]);

  React.useEffect(() => {
    void loadStats();
  }, [loadStats]);

  const doIndex = async () => {
    if (!workspaceId) return;
    setIndexing(true);
    try {
      const res: MemoryIndexResult = await api.indexMemory(workspaceId, {
        include_code: includeCode,
        force,
      });
      toast.success(res.message);
      await loadStats();
    } catch (err) {
      toast.error(errMessage(err, "Could not index the workspace"));
    } finally {
      setIndexing(false);
    }
  };

  const doSearch = async () => {
    if (!workspaceId || !query.trim()) return;
    setSearching(true);
    try {
      const res = await api.searchMemory(workspaceId, { query: query.trim() });
      setResult(res);
    } catch (err) {
      toast.error(errMessage(err, "Search failed"));
    } finally {
      setSearching(false);
    }
  };

  const doClear = async () => {
    if (!workspaceId) return;
    setClearing(true);
    try {
      const res = await api.clearMemory(workspaceId);
      toast.success(res.message);
      await loadStats();
      setResult(null);
    } catch (err) {
      toast.error(errMessage(err, "Could not clear memory"));
    } finally {
      setClearing(false);
    }
  };

  const totalChunks = stats?.chunks ?? 0;

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Brain className="h-6 w-6 text-primary" />
            Project Memory
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Everything the workspace knows — meetings, decisions, tasks and code —
            indexed and searchable in one place.
          </p>
        </div>
        <Badge variant="outline">Phase 5</Badge>
      </div>

      {/* stats */}
      <div className="grid gap-3 sm:grid-cols-4">
        <StatCard icon={<Database className="h-4 w-4" />} label="Chunks" value={String(totalChunks)} />
        <StatCard
          icon={<Layers className="h-4 w-4" />}
          label="Sources"
          value={String(Object.keys(stats?.by_type ?? {}).length)}
        />
        <StatCard
          icon={<Zap className="h-4 w-4" />}
          label="Embedder"
          value={stats?.embed_sources?.[0] ?? "—"}
        />
        <StatCard
          icon={<FolderTree className="h-4 w-4" />}
          label="Dimensions"
          value={stats?.dims?.join(", ") || "—"}
        />
      </div>

      {/* index controls */}
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={doIndex} disabled={indexing}>
          {indexing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {totalChunks ? "Re-index" : "Index workspace"}
        </Button>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={includeCode}
            onChange={(e) => setIncludeCode(e.target.checked)}
          />
          Include code files
        </label>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={force}
            onChange={(e) => setForce(e.target.checked)}
          />
          Force re-embed
        </label>
        <div className="ml-auto">
          <Button variant="outline" size="sm" onClick={doClear} disabled={clearing || !totalChunks}>
            <Trash2 className="h-3.5 w-3.5" />
            Clear
          </Button>
        </div>
      </div>

      {/* search */}
      <div className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doSearch()}
          placeholder="Search across meetings, decisions, tasks and code…"
        />
        <Button onClick={doSearch} disabled={searching || !query.trim()}>
          {searching ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
          Search
        </Button>
      </div>

      {/* results */}
      {result && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Sparkles className="h-4 w-4" />
            {result.count} result(s) for &ldquo;{result.query}&rdquo;
            {result.source === "fallback" && (
              <Badge variant="outline" className="ml-1">offline embeddings</Badge>
            )}
            {result.message && <span className="ml-2 text-xs">{result.message}</span>}
          </div>

          {result.results.map((hit) => (
            <div
              key={hit.chunk_id}
              className="rounded-lg border bg-background p-3 space-y-1.5"
            >
              <div className="flex items-center gap-2">
                <Badge variant={SOURCE_VARIANT[hit.source_type] ?? "outline"}>
                  {hit.source_type}
                </Badge>
                <span className="text-sm font-medium">{hit.title}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {(hit.score * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm text-muted-foreground line-clamp-2">
                {hit.snippet}
              </p>
              {typeof hit.meta?.path === "string" && (
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <FileText className="h-3 w-3" />
                  <code>{hit.meta.path}</code>
                </p>
              )}
            </div>
          ))}

          {result.results.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No results. Try different wording or index the workspace first.
            </p>
          )}
        </div>
      )}

      {!result && totalChunks === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          No memory yet. Click <strong>Index workspace</strong> to build the index
          from your meetings, decisions, tasks and sandbox code.
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold capitalize">{value}</div>
    </div>
  );
}
