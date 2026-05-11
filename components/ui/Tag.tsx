import { type ReactNode } from "react";
import type { Tone } from "@/lib/workbench-data";

interface Props {
  tone?: Tone;
  variant?: "soft" | "solid" | "outline";
  dot?: boolean;
  children: ReactNode;
}

const soft: Record<Tone, string> = {
  neutral: "bg-paper-sunk   text-ink-2",
  brand:   "bg-brand-tint   text-brand",
  success: "bg-success-tint text-success-ink",
  info:    "bg-info-tint    text-info-ink",
  warn:    "bg-warn-tint    text-warn-ink",
  danger:  "bg-danger-tint  text-danger-ink",
};
const solid: Record<Tone, string> = {
  neutral: "bg-ink-3 text-white",
  brand:   "bg-brand text-white",
  success: "bg-success text-white",
  info:    "bg-info text-white",
  warn:    "bg-warn text-white",
  danger:  "bg-danger text-white",
};

export function Tag({ tone = "neutral", variant = "soft", dot, children }: Props) {
  const cls =
    variant === "solid"  ? solid[tone]
  : variant === "outline"? `bg-transparent border border-current ${soft[tone].split(" ").pop()}`
  :                        soft[tone];
  return (
    <span
      className={`inline-flex items-center gap-1 h-6 px-3 rounded-pill text-micro font-medium tracking-wider leading-none whitespace-nowrap ${cls}`}
    >
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />}
      {children}
    </span>
  );
}
