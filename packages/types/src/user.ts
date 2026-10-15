import { z } from "zod";

export enum UserRole {
  ADMIN = "admin",
  USER = "user",
}

export const UserSchema = z.object({
  id: z.string().uuid().optional(),
  email: z.string().email(),
  name: z.string().min(1),
  image: z.string().url().optional(),
  role: z.nativeEnum(UserRole).default(UserRole.USER),
  is_active: z.boolean().default(true),
  email_verified: z.boolean().default(false),
});

export type User = z.infer<typeof UserSchema>;
