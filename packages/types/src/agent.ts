import { z } from "zod";

export enum AgentRunStatus {
  PENDING = "pending",
  PLANNING = "planning",
  AWAITING_APPROVAL = "awaiting_approval",
  EXECUTING = "executing",
  TESTING = "testing",
  COMPLETED = "completed",
  FAILED = "failed",
  CANCELLED = "cancelled",
}

export enum AgentTool {
  READ_FILE = "read_file",
  WRITE_FILE = "write_file",
  EDIT_FILE = "edit_file",
  LIST_FILES = "list_files",
  SEARCH_CODE = "search_code",
  RUN_TESTS = "run_tests",
  RUN_COMMAND = "run_command",
  CREATE_TASK = "create_task",
  CREATE_PR = "create_pr",
  EXPLAIN_CODE = "explain_code",
}

export const AgentPlanStepSchema = z.object({
  step_number: z.number().int().positive(),
  description: z.string(),
  tool: z.nativeEnum(AgentTool).optional(),
  files_involved: z.array(z.string()).default([]),
  status: z.enum(["pending", "in_progress", "completed", "failed", "skipped"]).default("pending"),
  output: z.string().optional(),
});

export const CodeChangeSchema = z.object({
  file_path: z.string(),
  change_type: z.enum(["create", "modify", "delete"]),
  diff: z.string(),
  explanation: z.string().optional(),
  approved: z.boolean().default(false),
});

export type AgentPlanStep = z.infer<typeof AgentPlanStepSchema>;
export type CodeChange = z.infer<typeof CodeChangeSchema>;
