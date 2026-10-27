"use client";

import { useEffect, useState } from "react";
import { Activity, CheckCircle2, XCircle, AlertCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/services/api";

interface SystemStatus {
  llm: {
    provider_order: string;
    gemini: { configured: boolean; model: string };
    openrouter: { configured: boolean; model: string };
    ollama: { configured: boolean; base_url: string; model: string };
  };
  stt: {
    engine: string;
    whisper_model: string | null;
    whisper_available: boolean;
    gemini_configured: boolean;
  };
  env: {
    database_url_scheme: string;
    executor: string;
    devstudio_backend: string;
  };
  tools: { ffmpeg: boolean; git: boolean };
}

export default function StatusPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/system/status");
      setStatus(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Failed to fetch status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const StatusIcon = ({ ok }: { ok: boolean }) =>
    ok ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <XCircle className="h-4 w-4 text-red-500" />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Provider & System Status</h2>
          <p className="text-muted-foreground">Check LLM providers, STT engine, and system tools at a glance</p>
        </div>
        <Button onClick={fetchStatus} disabled={loading} variant="outline" size="sm">
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="border-red-500/50">
          <CardContent className="flex items-center gap-2 pt-6 text-red-500">
            <AlertCircle className="h-4 w-4" />
            <p className="text-sm">{error}</p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              LLM Providers
            </CardTitle>
            <CardDescription>Order: {status?.llm.provider_order || "..."}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <StatusIcon ok={!!status?.llm.gemini.configured} />
                <span className="text-sm font-medium">Google Gemini</span>
              </div>
              <Badge variant={status?.llm.gemini.configured ? "default" : "secondary"}>
                {status?.llm.gemini.configured ? status?.llm.gemini.model : "Not configured"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <StatusIcon ok={!!status?.llm.openrouter.configured} />
                <span className="text-sm font-medium">OpenRouter</span>
              </div>
              <Badge variant={status?.llm.openrouter.configured ? "default" : "secondary"}>
                {status?.llm.openrouter.configured ? status?.llm.openrouter.model : "Not configured"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <StatusIcon ok={!!status?.llm.ollama.configured} />
                <span className="text-sm font-medium">Ollama (Local)</span>
              </div>
              <Badge variant={status?.llm.ollama.configured ? "default" : "secondary"}>
                {status?.llm.ollama.configured ? status?.llm.ollama.model : "Not running"}
              </Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Speech-to-Text</CardTitle>
            <CardDescription>Transcription engine configuration</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Engine</span>
              <Badge>{status?.stt.engine || "..."}</Badge>
            </div>
            {status?.stt.engine === "whisper_local" && (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Whisper Model</span>
                  <Badge variant="outline">{status?.stt.whisper_model}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <StatusIcon ok={!!status?.stt.whisper_available} />
                    <span className="text-sm font-medium">faster-whisper</span>
                  </div>
                  <Badge variant={status?.stt.whisper_available ? "default" : "secondary"}>
                    {status?.stt.whisper_available ? "Installed" : "Not installed"}
                  </Badge>
                </div>
              </>
            )}
            {status?.stt.engine === "gemini" && (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <StatusIcon ok={!!status?.stt.gemini_configured} />
                  <span className="text-sm font-medium">Gemini STT</span>
                </div>
                <Badge variant={status?.stt.gemini_configured ? "default" : "secondary"}>
                  {status?.stt.gemini_configured ? "Ready" : "Needs API key"}
                </Badge>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Environment</CardTitle>
            <CardDescription>Runtime configuration</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Database</span>
              <Badge variant="outline">{status?.env.database_url_scheme}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Code Executor</span>
              <Badge variant="outline">{status?.env.executor}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">DevStudio Backend</span>
              <Badge variant="outline">{status?.env.devstudio_backend}</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>System Tools</CardTitle>
            <CardDescription>External dependencies</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <StatusIcon ok={!!status?.tools.git} />
                <span className="text-sm font-medium">Git</span>
              </div>
              <Badge variant={status?.tools.git ? "default" : "secondary"}>
                {status?.tools.git ? "Available" : "Not found"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <StatusIcon ok={!!status?.tools.ffmpeg} />
                <span className="text-sm font-medium">FFmpeg</span>
              </div>
              <Badge variant={status?.tools.ffmpeg ? "default" : "secondary"}>
                {status?.tools.ffmpeg ? "Available" : "Not found (optional)"}
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
