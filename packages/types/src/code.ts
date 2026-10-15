import { z } from "zod";

export enum ExecutionStatus {
  QUEUED = "queued",
  RUNNING = "running",
  SUCCESS = "success",
  FAILED = "failed",
  TIMEOUT = "timeout",
  COMPILE_ERROR = "compile_error",
  RUNTIME_ERROR = "runtime_error",
}

export const ExecutionResultSchema = z.object({
  id: z.string().optional(),
  language: z.string(),
  status: z.nativeEnum(ExecutionStatus),
  stdout: z.string().default(""),
  stderr: z.string().default(""),
  exit_code: z.number().int().optional(),
  execution_time_ms: z.number().optional(),
  memory_used_kb: z.number().optional(),
});

export const RepositorySchema = z.object({
  id: z.string().optional(),
  name: z.string(),
  full_name: z.string(),
  url: z.string().url(),
  default_branch: z.string().default("main"),
  language: z.string().optional(),
  private: z.boolean().default(false),
  provider: z.enum(["github", "gitlab", "bitbucket"]).default("github"),
});

export type ExecutionResult = z.infer<typeof ExecutionResultSchema>;
export type Repository = z.infer<typeof RepositorySchema>;
