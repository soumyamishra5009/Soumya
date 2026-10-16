"use client";

import * as React from "react";

import { useAuth } from "@/components/auth-provider";
import { api } from "@/lib/api";
import type { Member } from "@/lib/types";

interface MembersContextValue {
  members: Member[];
  /** user_id -> Member, for resolving task assignees on any page. */
  byId: Record<string, Member>;
  loading: boolean;
  refresh: () => Promise<void>;
}

const MembersContext = React.createContext<MembersContextValue | null>(null);

export function MembersProvider({ children }: { children: React.ReactNode }) {
  const { workspace } = useAuth();
  const [members, setMembers] = React.useState<Member[]>([]);
  const [loading, setLoading] = React.useState(false);

  const refresh = React.useCallback(async () => {
    if (!workspace) {
      setMembers([]);
      return;
    }
    setLoading(true);
    try {
      setMembers(await api.listMembers(workspace.id));
    } catch {
      // A non-fatal failure: pages can still render without assignee labels.
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const byId = React.useMemo(() => {
    const map: Record<string, Member> = {};
    for (const m of members) map[m.user_id] = m;
    return map;
  }, [members]);

  const value = React.useMemo<MembersContextValue>(
    () => ({ members, byId, loading, refresh }),
    [members, byId, loading, refresh]
  );

  return <MembersContext.Provider value={value}>{children}</MembersContext.Provider>;
}

export function useMembers(): MembersContextValue {
  const ctx = React.useContext(MembersContext);
  if (!ctx) throw new Error("useMembers must be used inside <MembersProvider>");
  return ctx;
}
