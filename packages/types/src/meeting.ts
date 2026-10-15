import { z } from "zod";

export const ActionItemSchema = z.object({
  title: z.string().min(1, "Action item title is required"),
  description: z.string().optional(),
  assignee: z.string().optional(),
  priority: z.enum(["low", "medium", "high", "urgent"]).default("medium"),
  due_date: z.string().datetime().optional(),
  estimated_hours: z.number().positive().optional(),
});

export const DecisionSchema = z.object({
  title: z.string().min(1),
  description: z.string().optional(),
  impact: z.enum(["low", "medium", "high"]).default("medium"),
  rationale: z.string().optional(),
});

export const MeetingSummarySchema = z.object({
  summary: z.string().min(1),
  key_points: z.array(z.string()),
  decisions: z.array(DecisionSchema),
  action_items: z.array(ActionItemSchema),
  risks: z.array(z.string()),
  unanswered_questions: z.array(z.string()),
  next_steps: z.array(z.string()),
  attendees: z.array(z.string()).optional(),
  meeting_type: z.string().optional(),
});

export type ActionItem = z.infer<typeof ActionItemSchema>;
export type Decision = z.infer<typeof DecisionSchema>;
export type MeetingSummary = z.infer<typeof MeetingSummarySchema>;

export enum MeetingStatus {
  UPLOADING = "uploading",
  TRANSCRIBING = "transcribing",
  SUMMARIZING = "summarizing",
  PROCESSING = "processing",
  COMPLETED = "completed",
  FAILED = "failed",
}
