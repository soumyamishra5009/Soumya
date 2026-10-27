import { z } from "zod";

/**
 * Shared frontend environment schema.
 * Only NEXT_PUBLIC_* vars are exposed to the browser.
 */
export const clientEnvSchema = z.object({
  NEXT_PUBLIC_APP_NAME: z.string().default("Cognix"),
  NEXT_PUBLIC_APP_URL: z.string().url().default("http://localhost:3000"),
  NEXT_PUBLIC_API_URL: z.string().url().default("http://localhost:8000"),
});

export type ClientEnv = z.infer<typeof clientEnvSchema>;

export function validateClientEnv(env: Record<string, string | undefined>): ClientEnv {
  const parsed = clientEnvSchema.safeParse(env);
  if (!parsed.success) {
    console.error("❌ Invalid client environment variables:", parsed.error.flatten().fieldErrors);
    throw new Error("Invalid client environment variables");
  }
  return parsed.data;
}

/** App-wide constants */
export const APP = {
  name: "Cognix",
  tagline: "Meetings → Decisions → Tasks → Code → Verification",
  version: "0.1.0",
} as const;
