"use client";

import * as React from "react";

import { api, tokenStore, workspaceStore } from "@/lib/api";
import type { User, Workspace } from "@/lib/types";

interface AuthContextValue {
  user: User | null;
  workspace: Workspace | null;
  workspaces: Workspace[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  signIn: (token: string) => Promise<void>;
  signOut: () => void;
  setWorkspace: (workspace: Workspace) => void;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [workspaces, setWorkspaces] = React.useState<Workspace[]>([]);
  const [workspace, setWorkspaceState] = React.useState<Workspace | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const bootstrap = React.useCallback(async () => {
    if (!tokenStore.get()) {
      setUser(null);
      setWorkspaces([]);
      setWorkspaceState(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const me = await api.me();
      setUser(me);

      let list = await api.listWorkspaces();
      if (list.length === 0) {
        const first = me.name?.split(" ")[0] || "My";
        const created = await api.createWorkspace(`${first}'s Workspace`);
        list = [created];
      }
      setWorkspaces(list);

      const savedId = workspaceStore.get();
      const active = list.find((w) => w.id === savedId) ?? list[0];
      workspaceStore.set(active.id);
      setWorkspaceState(active);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load session";
      setError(message);
      // A 401 already cleared the token inside the client.
      if (!tokenStore.get()) {
        setUser(null);
        setWorkspaces([]);
        setWorkspaceState(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  const signIn = React.useCallback(
    async (token: string) => {
      tokenStore.set(token);
      workspaceStore.clear();
      await bootstrap();
    },
    [bootstrap]
  );

  const signOut = React.useCallback(() => {
    tokenStore.clear();
    workspaceStore.clear();
    setUser(null);
    setWorkspaces([]);
    setWorkspaceState(null);
  }, []);

  const setWorkspace = React.useCallback((next: Workspace) => {
    workspaceStore.set(next.id);
    setWorkspaceState(next);
  }, []);

  const value = React.useMemo<AuthContextValue>(
    () => ({
      user,
      workspace,
      workspaces,
      loading,
      error,
      refresh: bootstrap,
      signIn,
      signOut,
      setWorkspace,
    }),
    [user, workspace, workspaces, loading, error, bootstrap, signIn, signOut, setWorkspace]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}
