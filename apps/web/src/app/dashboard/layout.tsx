"use client";

import { ReactNode, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  AudioLines,
  KanbanSquare,
  Code2,
  Users,
  LogOut,
  Loader2,
  Sparkles,
  ChevronDown,
} from "lucide-react";

import { AuthProvider, useAuth } from "@/components/auth-provider";
import { MembersProvider } from "@/components/members-provider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { initials } from "@/lib/format";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard, ready: true },
  { href: "/dashboard/meetings", label: "Meetings", icon: AudioLines, ready: true },
  { href: "/dashboard/tasks", label: "Task Board", icon: KanbanSquare, ready: true },
  { href: "/dashboard/team", label: "Team", icon: Users, ready: true },
  { href: "/dashboard/studio", label: "Dev Studio", icon: Code2, ready: false },
];

function Shell({ children }: { children: ReactNode }) {
  const { user, workspace, workspaces, loading, setWorkspace, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-background">
      <aside className="hidden w-64 flex-col border-r bg-card/40 md:flex">
        <div className="flex h-16 items-center gap-2 border-b px-6">
          <Sparkles className="h-5 w-5 text-primary" />
          <Link
            href="/dashboard"
            className="text-lg font-semibold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent"
          >
            SyncForge AI
          </Link>
        </div>

        {/* Workspace switcher */}
        <div className="border-b p-3">
          <div className="relative">
            <select
              aria-label="Workspace"
              className="w-full appearance-none rounded-md border bg-background py-2 pl-3 pr-8 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={workspace?.id ?? ""}
              onChange={(e) => {
                const next = workspaces.find((w) => w.id === e.target.value);
                if (next) setWorkspace(next);
              }}
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          </div>
        </div>

        <nav className="flex-1 space-y-1 p-3">
          {NAV.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.ready ? item.href : "#"}
                aria-disabled={!item.ready}
                onClick={(e) => {
                  if (!item.ready) e.preventDefault();
                }}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:bg-accent/10 hover:text-foreground",
                  !item.ready && "cursor-not-allowed opacity-50"
                )}
              >
                <Icon className="h-4 w-4" />
                <span className="flex-1">{item.label}</span>
                {!item.ready && (
                  <Badge variant="outline" className="text-[10px]">
                    Soon
                  </Badge>
                )}
              </Link>
            );
          })}
        </nav>

        <div className="border-t p-3">
          <div className="flex items-center gap-3 rounded-md px-2 py-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/20 text-xs font-semibold text-primary">
              {initials(user.name)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{user.name}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Sign out"
              onClick={() => {
                signOut();
                router.replace("/login");
              }}
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b bg-card/50 px-6 backdrop-blur">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold">
              {NAV.find((n) =>
                n.href === "/dashboard" ? pathname === n.href : pathname.startsWith(n.href)
              )?.label ?? "Dashboard"}
            </h1>
            {workspace && (
              <Badge variant="outline" className="hidden sm:inline-flex">
                {workspace.name}
              </Badge>
            )}
          </div>
          <div className="md:hidden">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                signOut();
                router.replace("/login");
              }}
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto p-6">{children}</div>
      </main>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <MembersProvider>
        <Shell>{children}</Shell>
      </MembersProvider>
    </AuthProvider>
  );
}
