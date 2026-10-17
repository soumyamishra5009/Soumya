import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  Bot,
  FileText,
  Kanban,
  Code2,
  GitPullRequest,
  FlaskConical,
  Brain,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

const FEATURES = [
  {
    icon: FileText,
    title: "AI Meeting Intelligence",
    text: "Transcribe, summarize & extract decisions + action items",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
  },
  {
    icon: Kanban,
    title: "Smart Action Tracker",
    text: "Kanban with meeting-linked tasks & overdue alerts",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
  },
  {
    icon: Bot,
    title: "Meeting-to-Code Agent",
    text: "Decisions → Technical specs → Code changes with approval",
    color: "text-violet-400",
    bg: "bg-violet-500/10",
  },
  {
    icon: Code2,
    title: "AI Dev Studio",
    text: "Monaco editor + context-aware AI + GitHub PR proposals",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
  },
  {
    icon: GitPullRequest,
    title: "Ship It",
    text: "Local git branches, commits & pull requests — human-gated",
    color: "text-rose-400",
    bg: "bg-rose-500/10",
  },
  {
    icon: FlaskConical,
    title: "Verify",
    text: "Sandboxed test runs — bundled offline runner, fail → fix → pass",
    color: "text-cyan-400",
    bg: "bg-cyan-500/10",
  },
  {
    icon: Brain,
    title: "Project Memory",
    text: "Workspace RAG — semantic search across meetings, tasks & code",
    color: "text-fuchsia-400",
    bg: "bg-fuchsia-500/10",
  },
  {
    icon: Sparkles,
    title: "Human-in-the-loop",
    text: "Nothing ships without your approval — every change is reviewable",
    color: "text-yellow-400",
    bg: "bg-yellow-500/10",
  },
];

const PIPELINE = [
  "Meeting",
  "Decision",
  "Task",
  "Code",
  "Verify",
  "Ship",
  "Remember",
];

export default function HomePage() {
  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden">
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0 bg-glow" aria-hidden />
      <div className="pointer-events-none absolute inset-0 bg-grid opacity-40" aria-hidden />
      <div
        className="pointer-events-none absolute -top-40 left-1/2 h-80 w-80 -translate-x-1/2 rounded-full bg-primary/20 blur-3xl animate-float"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute top-1/3 -right-20 h-64 w-64 rounded-full bg-accent/10 blur-3xl animate-float"
        style={{ animationDelay: "1s" }}
        aria-hidden
      />

      {/* Hero Section */}
      <section className="relative flex flex-1 flex-col items-center justify-center px-6 py-24 text-center">
        <div className="max-w-6xl space-y-8">
          <div className="space-y-4">
            <div className="inline-flex items-center rounded-full border bg-muted/80 px-4 py-1.5 text-sm shadow-sm backdrop-blur animate-fade-in-down">
              <span className="mr-2 inline-block h-2 w-2 rounded-full bg-accent animate-pulse" />
              {PIPELINE.join(" → ")}
            </div>
            <h1 className="text-4xl font-bold tracking-tight sm:text-6xl md:text-7xl animate-fade-in-up">
              SyncForge{" "}
              <span className="gradient-text animate-gradient">AI</span>
            </h1>
            <p className="mx-auto max-w-3xl text-lg text-muted-foreground sm:text-xl animate-fade-in-up stagger-2">
              Turn your meetings into actionable work. Extract decisions, create
              trackable tasks, and implement them with an AI coding agent — all in
              one unified workspace.
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-4 animate-fade-in-up stagger-3">
            <Button size="lg" className="group animate-pulse-glow" asChild>
              <Link href="/login">
                Get Started
                <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" className="card-hover" asChild>
              <Link href="/dashboard">
                Open Dashboard
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>

          {/* Pipeline visualization */}
          <div className="flex flex-wrap items-center justify-center gap-2 animate-fade-in-up stagger-4">
            {PIPELINE.map((step, i) => (
              <div key={step} className="flex items-center gap-2">
                <span className="rounded-full border bg-card/60 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur">
                  {step}
                </span>
                {i < PIPELINE.length - 1 && (
                  <ArrowRight className="h-3 w-3 text-muted-foreground/50" />
                )}
              </div>
            ))}
          </div>

          {/* Features Preview */}
          <div className="mt-16 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f, i) => (
              <div
                key={f.title}
                className={`flex flex-col items-center space-y-3 rounded-xl border bg-card/50 p-6 shadow-sm backdrop-blur card-hover animate-fade-in-up stagger-${Math.min(i + 1, 8)}`}
              >
                <div className={`rounded-full p-3 ${f.bg}`}>
                  <f.icon className={`h-6 w-6 ${f.color}`} />
                </div>
                <h3 className="font-semibold text-sm">{f.title}</h3>
                <p className="text-sm text-muted-foreground text-center">{f.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative border-t px-6 py-8">
        <div className="mx-auto max-w-6xl flex flex-col items-center justify-between gap-4 sm:flex-row">
          <p className="text-sm text-muted-foreground">
            © {new Date().getFullYear()} SyncForge AI. Built for hackathons &
            engineering teams.
          </p>
          <div className="flex gap-6 text-sm text-muted-foreground">
            <Link
              href="/dashboard"
              className="hover:text-foreground transition-colors"
            >
              Dashboard
            </Link>
            <Link
              href="http://localhost:8000/docs"
              className="hover:text-foreground transition-colors"
              target="_blank"
            >
              API
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
