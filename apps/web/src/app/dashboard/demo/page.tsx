"use client";

import { useState } from "react";
import { Wand2, Sparkles, CheckCircle2, Loader2, FileAudio, KanbanSquare, Code2, GitPullRequest } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/services/api";

export default function DemoPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const seedDemo = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.post("/demo/seed");
      setResult(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Failed to seed demo data");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Wand2 className="h-6 w-6 text-primary" />
          Demo Mode
        </h2>
        <p className="text-muted-foreground">One-click seed to load sample meeting, tasks, and demo workspace for smooth demos</p>
      </div>

      <Card className="border-primary/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Load Demo Workspace
          </CardTitle>
          <CardDescription>
            Creates a demo workspace with a sprint planning meeting, AI-generated decisions, action items, and Kanban tasks
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="flex items-center gap-2 text-sm">
              <FileAudio className="h-4 w-4 text-primary" />
              <span>Sample Meeting</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <KanbanSquare className="h-4 w-4 text-primary" />
              <span>Auto Tasks</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Code2 className="h-4 w-4 text-primary" />
              <span>Ready for Dev Studio</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <GitPullRequest className="h-4 w-4 text-primary" />
              <span>Meeting → Code Flow</span>
            </div>
          </div>

          <Button onClick={seedDemo} disabled={loading} size="lg" className="w-full md:w-auto">
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Seeding Demo Data...
              </>
            ) : (
              <>
                <Wand2 className="mr-2 h-4 w-4" />
                Load Demo Workspace
              </>
            )}
          </Button>

          {result && (
            <Card className="bg-emerald-500/10 border-emerald-500/50">
              <CardContent className="flex items-start gap-3 pt-6">
                <CheckCircle2 className="h-5 w-5 text-emerald-500 mt-0.5" />
                <div className="space-y-1">
                  <p className="font-medium text-emerald-500">{result.message}</p>
                  <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
                    <Badge variant="outline">Meeting: {result.meeting_id?.slice(0, 8)}...</Badge>
                    <Badge variant="outline">Tasks: {result.tasks_created}</Badge>
                    <Badge variant="outline">Workspace: {result.workspace_id?.slice(0, 8)}...</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {error && (
            <Card className="bg-red-500/10 border-red-500/50">
              <CardContent className="pt-6 text-red-500">
                <p className="text-sm">{error}</p>
              </CardContent>
            </Card>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Demo Flow Guide</CardTitle>
          <CardDescription>Follow this for a smooth 5-7 min demo</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-2 text-sm">
            <li className="flex gap-2"><span className="font-semibold text-primary">1.</span> Go to <strong>Meetings</strong> - see the seeded demo meeting with transcript, summary, decisions & actions</li>
            <li className="flex gap-2"><span className="font-semibold text-primary">2.</span> Go to <strong>Task Board</strong> - drag & drop tasks, see assignees and priorities</li>
            <li className="flex gap-2"><span className="font-semibold text-primary">3.</span> Go to <strong>Dev Studio</strong> → Create sample project, open calculator.py, ask AI to fix divide by zero bug, review diff & approve</li>
            <li className="flex gap-2"><span className="font-semibold text-primary">4.</span> Go to <strong>Meeting → Code</strong> - select demo meeting, Generate plan → Create proposals → Review & approve</li>
            <li className="flex gap-2"><span className="font-semibold text-primary">5.</span> Go to <strong>Ship it</strong> flow - connect local sandbox repo, create draft, open & merge (real git ops)</li>
            <li className="flex gap-2"><span className="font-semibold text-primary">6.</span> Go to <strong>Project Memory</strong> - search "divide by zero" or "calculator" to see RAG results</li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
