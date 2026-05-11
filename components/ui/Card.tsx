import { type ReactNode, type HTMLAttributes } from "react";

type Variant = "base" | "flat" | "raised" | "outline" | "accent" | "inset";

interface Props extends HTMLAttributes<HTMLDivElement> {
  variant?: Variant;
  hover?: boolean;
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

const variants: Record<Variant, string> = {
  base:    "bg-paper-hi border border-rule-card shadow-sm",
  flat:    "bg-paper-hi border border-rule-card",
  raised:  "bg-paper-hi border border-rule-card shadow-md",
  outline: "bg-transparent border border-rule-card",
  accent:  "bg-brand-tint border border-[color-mix(in_oklch,var(--color-brand),transparent_75%)]",
  inset:   "bg-paper-sunk shadow-[inset_0_1px_2px_rgba(60,40,20,0.06)]",
};

const sizes = {
  sm: "p-4 rounded-sm",
  md: "p-5 rounded-md",
  lg: "p-7 rounded-lg",
};

export function Card({
  variant = "base", size = "md", hover = false, className = "", children, ...rest
}: Props) {
  return (
    <div
      className={[
        variants[variant], sizes[size],
        hover ? "cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md" : "",
        className,
      ].join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardEyebrow({ children }: { children: ReactNode }) {
  return <div className="eyebrow mb-2">{children}</div>;
}
export function CardTitle({ children }: { children: ReactNode }) {
  return <h4 className="text-h4 font-semibold text-ink tracking-tight">{children}</h4>;
}
export function CardBody({ children }: { children: ReactNode }) {
  return <p className="text-body-sm text-ink-2 mt-2">{children}</p>;
}
export function CardFooter({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center justify-between mt-5 pt-4 border-t border-dashed border-rule-soft text-meta text-ink-3">
      {children}
    </div>
  );
}
