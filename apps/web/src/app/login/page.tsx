"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Loader2,
  Sparkles,
  AudioLines,
  KanbanSquare,
  ShieldCheck,
  FlaskConical,
  Brain,
} from "lucide-react";
import { toast } from "sonner";

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
import { api, tokenStore } from "@/lib/api";

const FEATURES = [
  {
    icon: AudioLines,
    title: "Meeting Intelligence",
    text: "Upload audio → transcript, summary, decisions & action items.",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
  },
  {
    icon: KanbanSquare,
    title: "Action Tracker",
    text: "Every decision becomes a tracked task on a live board.",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
  },
  {
    icon: ShieldCheck,
    title: "Human-in-the-loop",
    text: "Nothing ships without your approval.",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
  },
  {
    icon: FlaskConical,
    title: "Verify",
    text: "Sandboxed test runs before you ship.",
    color: "text-cyan-400",
    bg: "bg-cyan-500/10",
  },
  {
    icon: Brain,
    title: "Project Memory",
    text: "Semantic search across everything your workspace knows.",
    color: "text-fuchsia-400",
    bg: "bg-fuchsia-500/10",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = React.useState<"login" | "register">("login");
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (tokenStore.get()) router.replace("/dashboard");
  }, [router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;

    if (mode === "register" && password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }

    setBusy(true);
    try {
      const res =
        mode === "login"
          ? await api.login(email.trim(), password)
          : await api.register(email.trim(), password, name.trim());
      tokenStore.set(res.access_token);
      toast.success(mode === "login" ? "Welcome back!" : "Account created!");
      router.replace("/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative grid min-h-screen lg:grid-cols-2">
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0 bg-glow" aria-hidden />

      {/* Left: brand / pitch */}
      <div className="relative hidden flex-col justify-between overflow-hidden border-r bg-card/40 p-10 lg:flex animate-fade-in-left">
        <div
          className="pointer-events-none absolute -left-24 top-1/3 h-96 w-96 rounded-full bg-primary/20 blur-3xl animate-float"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute bottom-1/4 -right-20 h-64 w-64 rounded-full bg-accent/10 blur-3xl animate-float"
          style={{ animationDelay: "1.5s" }}
          aria-hidden
        />

        <Link href="/" className="relative z-10 flex items-center gap-2 animate-fade-in-down">
          <Sparkles className="h-6 w-6 text-primary" />
          <span className="text-xl font-semibold gradient-text">
            Cognix
          </span>
        </Link>

        <div className="relative z-10 space-y-8">
          <div className="space-y-3 animate-fade-in-up stagger-2">
            <h1 className="text-4xl font-bold leading-tight">
              From conversation
              <br />
              to shipped code.
            </h1>
            <p className="max-w-md text-muted-foreground">
              The pipeline that turns your meetings into decisions, tasks and
              verified code — with you in control at every step.
            </p>
          </div>

          <ul className="space-y-4">
            {FEATURES.map((f, i) => (
              <li
                key={f.title}
                className={`flex items-start gap-3 animate-fade-in-up stagger-${Math.min(i + 2, 8)}`}
              >
                <div className={`mt-0.5 rounded-lg border bg-background/60 p-2 ${f.bg}`}>
                  <f.icon className={`h-4 w-4 ${f.color}`} />
                </div>
                <div>
                  <p className="text-sm font-medium">{f.title}</p>
                  <p className="text-sm text-muted-foreground">{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 text-xs text-muted-foreground animate-fade-in-up stagger-6">
          Meeting → Decision → Task → Code → Verify → Ship → Remember
        </p>
      </div>

      {/* Right: form */}
      <div className="relative flex items-center justify-center p-6">
        <Card className="w-full max-w-md animate-scale-in-up">
          <CardHeader>
            <CardTitle className="text-2xl">
              {mode === "login" ? "Sign in" : "Create your account"}
            </CardTitle>
            <CardDescription>
              {mode === "login"
                ? "Continue to your Cognix workspace."
                : "Set up your workspace in seconds — no credit card."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4">
              {mode === "register" && (
                <div className="space-y-2 animate-fade-in-down">
                  <Label htmlFor="name">Full name</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Parth Gupta"
                    required
                    autoComplete="name"
                  />
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  autoComplete="email"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === "register" ? "At least 8 characters" : "••••••••"}
                  required
                  minLength={mode === "register" ? 8 : undefined}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                />
              </div>

              <Button type="submit" className="w-full" disabled={busy}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                {mode === "login" ? "Sign in" : "Create account"}
              </Button>
            </form>

            <div className="mt-6 text-center text-sm text-muted-foreground">
              {mode === "login" ? (
                <>
                  New here?{" "}
                  <button
                    type="button"
                    className="font-medium text-primary hover:underline"
                    onClick={() => setMode("register")}
                  >
                    Create an account
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    className="font-medium text-primary hover:underline"
                    onClick={() => setMode("login")}
                  >
                    Sign in
                  </button>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
