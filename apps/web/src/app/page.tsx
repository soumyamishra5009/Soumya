import { Button } from "@/components/ui/button";
import { ArrowRight, Bot, FileText, Kanban, Code2 } from "lucide-react";
import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col">
      {/* Hero Section */}
      <section className="flex flex-1 flex-col items-center justify-center px-6 py-24 text-center">
        <div className="max-w-6xl space-y-8">
          <div className="space-y-4">
            <div className="inline-flex items-center rounded-full border bg-muted px-4 py-1.5 text-sm shadow-sm backdrop-blur">
              <span className="mr-2 inline-block h-2 w-2 rounded-full bg-accent"></span>
              Meetings → Decisions → Tasks → Code → Verification
            </div>
            <h1 className="text-4xl font-bold tracking-tight sm:text-6xl md:text-7xl">
              SyncForge <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">AI</span>
            </h1>
            <p className="mx-auto max-w-3xl text-lg text-muted-foreground sm:text-xl">
              Turn your meetings into actionable work. Extract decisions, create trackable tasks, and implement them with an AI coding agent — all in one unified workspace.
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-4">
            <Button size="lg" className="group" asChild>
              <Link href="/login">
                Get Started
                <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <Link href="/dashboard">
                Open Dashboard
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>

          {/* Features Preview */}
          <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <div className="flex flex-col items-center space-y-3 rounded-xl border bg-card/50 p-6 shadow-sm backdrop-blur transition-colors hover:border-primary/50">
              <div className="rounded-full bg-primary/10 p-3">
                <FileText className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-semibold">AI Meeting Intelligence</h3>
              <p className="text-sm text-muted-foreground">
                Transcribe, summarize & extract decisions + action items
              </p>
            </div>

            <div className="flex flex-col items-center space-y-3 rounded-xl border bg-card/50 p-6 shadow-sm backdrop-blur transition-colors hover:border-primary/50">
              <div className="rounded-full bg-primary/10 p-3">
                <Kanban className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-semibold">Smart Action Tracker</h3>
              <p className="text-sm text-muted-foreground">
                Kanban with meeting-linked tasks & overdue alerts
              </p>
            </div>

            <div className="flex flex-col items-center space-y-3 rounded-xl border bg-card/50 p-6 shadow-sm backdrop-blur transition-colors hover:border-primary/50">
              <div className="rounded-full bg-primary/10 p-3">
                <Bot className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-semibold">Meeting-to-Code Agent</h3>
              <p className="text-sm text-muted-foreground">
                Decisions → Technical specs → Code changes with approval
              </p>
            </div>

            <div className="flex flex-col items-center space-y-3 rounded-xl border bg-card/50 p-6 shadow-sm backdrop-blur transition-colors hover:border-primary/50">
              <div className="rounded-full bg-primary/10 p-3">
                <Code2 className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-semibold">AI Dev Studio</h3>
              <p className="text-sm text-muted-foreground">
                Monaco editor + context-aware AI + GitHub PR proposals
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t px-6 py-8">
        <div className="mx-auto max-w-6xl flex flex-col items-center justify-between gap-4 sm:flex-row">
          <p className="text-sm text-muted-foreground">
            © {new Date().getFullYear()} SyncForge AI. Built for hackathons & engineering teams.
          </p>
          <div className="flex gap-6 text-sm text-muted-foreground">
            <Link href="/dashboard" className="hover:text-foreground transition-colors">
              Dashboard
            </Link>
            <Link href="http://localhost:8000/docs" className="hover:text-foreground transition-colors" target="_blank">
              API
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
