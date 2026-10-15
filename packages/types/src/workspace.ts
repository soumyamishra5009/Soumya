import { z } from "zod";

export enum WorkspaceRole {
  OWNER = "owner",
  ADMIN = "admin",
  MEMBER = "member",
  VIEWER = "viewer",
}

export const WorkspaceSchema = z.object({
  id: z.string().uuid().optional(),
  name: z.string().min(1, "Workspace name is required"),
  description: z.string().optional(),
  slug: z.string().optional(),
  is_active: z.boolean().default(true),
  settings: z.record(z.any()).optional(),
});

export type Workspace = z.infer<typeof WorkspaceSchema>;
