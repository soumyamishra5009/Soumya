import { z } from "zod";

export enum TaskStatus {
  TODO = "todo",
  IN_PROGRESS = "in_progress",
  REVIEW = "review",
  DONE = "done",
  BLOCKED = "blocked",
  CANCELLED = "cancelled",
}

export enum TaskPriority {
  LOW = "low",
  MEDIUM = "medium",
  HIGH = "high",
  URGENT = "urgent",
}

export const TaskSchema = z.object({
  id: z.string().uuid().optional(),
  title: z.string().min(1, "Title is required"),
  description: z.string().optional(),
  status: z.nativeEnum(TaskStatus).default(TaskStatus.TODO),
  priority: z.nativeEnum(TaskPriority).default(TaskPriority.MEDIUM),
  assignee_id: z.string().uuid().optional(),
  reporter_id: z.string().uuid().optional(),
  workspace_id: z.string().uuid().optional(),
  meeting_id: z.string().uuid().optional(),
  project_id: z.string().uuid().optional(),
  due_date: z.coerce.date().optional(),
  start_date: z.coerce.date().optional(),
  completed_at: z.coerce.date().optional(),
  estimated_hours: z.number().positive().optional(),
  actual_hours: z.number().positive().optional(),
  tags: z.array(z.string()).default([]),
  metadata: z.record(z.any()).optional(),
});

export type Task = z.infer<typeof TaskSchema>;
