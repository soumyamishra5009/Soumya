"use client";

import * as React from "react";
import { Loader2, UserPlus, Users, Trash2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { useMembers } from "@/components/members-provider";
import { MemberAvatar } from "@/components/member-avatar";
import { api, ApiError } from "@/lib/api";
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
import { relativeTime } from "@/lib/format";

export default function TeamPage() {
  const { user, workspace } = useAuth();
  const { members, loading, refresh } = useMembers();

  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("member");
  const [adding, setAdding] = React.useState(false);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const me = members.find((m) => m.user_id === user?.id);
  const canManage = Boolean(me && (me.is_owner || me.role === "owner" || me.role === "admin"));

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!workspace || adding) return;
    const target = email.trim().toLowerCase();
    if (!target) {
      toast.error("Enter their email");
      return;
    }
    setAdding(true);
    try {
      await api.addMember(workspace.id, target, role);
      toast.success("Member added");
      setEmail("");
      setRole("member");
      await refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add member");
    } finally {
      setAdding(false);
    }
  }

  async function onRemove(userId: string, name: string) {
    if (!workspace) return;
    if (!confirm(`Remove ${name} from ${workspace.name}?`)) return;
    setBusyId(userId);
    try {
      await api.removeMember(workspace.id, userId);
      toast.success("Member removed");
      await refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not remove member");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="animate-fade-in-up">
        <h2 className="text-3xl font-bold tracking-tight">Team</h2>
        <p className="text-muted-foreground">
          Members of {workspace?.name ?? "this workspace"} can be assigned tasks
          and see every meeting.
        </p>
      </div>

      {canManage && (
        <Card className="card-hover animate-fade-in-up stagger-2">
          <CardHeader>
            <CardTitle className="text-base">Add a member</CardTitle>
            <CardDescription>
              They need a SyncForge account already — ask them to sign up, then
              add them here by email.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onAdd} className="flex flex-wrap items-end gap-3">
              <div className="min-w-[16rem] flex-1 space-y-2">
                <Label htmlFor="member-email">Email</Label>
                <Input
                  id="member-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="teammate@example.com"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="member-role">Role</Label>
                <select
                  id="member-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
              <Button type="submit" disabled={adding}>
                {adding ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <UserPlus className="h-4 w-4" />
                )}
                Add member
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Card className="card-hover animate-fade-in-up stagger-3">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            {members.length} {members.length === 1 ? "member" : "members"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading && members.length === 0 ? (
            <div className="flex h-24 items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : members.length === 0 ? (
            <div className="flex flex-col items-center py-10 text-center text-sm text-muted-foreground">
              <Users className="mb-2 h-8 w-8" />
              No members yet.
            </div>
          ) : (
            <ul className="divide-y">
              {members.map((m) => (
                <li key={m.user_id} className="flex items-center gap-3 py-3">
                  <MemberAvatar member={m} size="lg" />
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 text-sm font-medium">
                      {m.name}
                      {m.user_id === user?.id && (
                        <span className="text-xs text-muted-foreground">(you)</span>
                      )}
                      {m.is_owner && (
                        <ShieldCheck className="h-3.5 w-3.5 text-amber-400" />
                      )}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {m.email}
                    </p>
                  </div>
                  <Badge variant={m.is_owner ? "warning" : "secondary"}>
                    {m.is_owner ? "owner" : m.role}
                  </Badge>
                  <span className="hidden text-xs text-muted-foreground sm:block">
                    joined {relativeTime(m.invited_at)}
                  </span>
                  {canManage && !m.is_owner && (
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove ${m.name}`}
                      disabled={busyId === m.user_id}
                      onClick={() => void onRemove(m.user_id, m.name)}
                    >
                      {busyId === m.user_id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4 text-rose-400" />
                      )}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
