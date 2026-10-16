"use client";

import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Member } from "@/lib/types";

const SIZE_CLASS = {
  xs: "h-5 w-5 text-[9px]",
  sm: "h-6 w-6 text-[10px]",
  md: "h-8 w-8 text-xs",
  lg: "h-10 w-10 text-sm",
} as const;

// Stable, pleasant colour per user so avatars stay recognisable across pages.
function colorFor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) % 360;
  }
  return `hsl(${hash} 65% 32%)`;
}

export function MemberAvatar({
  member,
  size = "sm",
  className,
  title,
}: {
  member?: Member | null;
  size?: keyof typeof SIZE_CLASS;
  className?: string;
  title?: string;
}) {
  if (!member) {
    return (
      <span
        title={title ?? "Unassigned"}
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-full border border-dashed border-muted-foreground/40 text-muted-foreground",
          SIZE_CLASS[size],
          className
        )}
      >
        ?
      </span>
    );
  }

  return (
    <span
      title={title ?? `${member.name} (${member.email})`}
      style={member.image ? undefined : { backgroundColor: colorFor(member.user_id) }}
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold text-white ring-1 ring-black/10",
        SIZE_CLASS[size],
        className
      )}
    >
      {member.image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={member.image} alt={member.name} className="h-full w-full object-cover" />
      ) : (
        initials(member.name)
      )}
    </span>
  );
}

export function AvatarStack({
  members,
  max = 5,
  size = "sm",
}: {
  members: Member[];
  max?: number;
  size?: keyof typeof SIZE_CLASS;
}) {
  const shown = members.slice(0, max);
  const extra = members.length - shown.length;
  return (
    <div className="flex items-center -space-x-2">
      {shown.map((m) => (
        <MemberAvatar key={m.user_id} member={m} size={size} className="ring-2 ring-background" />
      ))}
      {extra > 0 && (
        <span
          className={cn(
            "inline-flex items-center justify-center rounded-full bg-muted font-semibold text-muted-foreground ring-2 ring-background",
            SIZE_CLASS[size]
          )}
        >
          +{extra}
        </span>
      )}
    </div>
  );
}
