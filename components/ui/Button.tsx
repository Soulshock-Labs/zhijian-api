import { type ReactNode, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "link";
type Size = "sm" | "md" | "lg";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  children: ReactNode;
}

const base =
  "inline-flex items-center justify-center gap-2 font-medium leading-none whitespace-nowrap select-none " +
  "transition-colors rounded-pill border border-transparent disabled:opacity-45 disabled:pointer-events-none";

const sizes: Record<Size, string> = {
  sm: "h-[var(--h-btn-sm)] px-4 text-meta",
  md: "h-[var(--h-btn-md)] px-5 text-body-sm",
  lg: "h-[var(--h-btn-lg)] px-6 text-body",
};

const variants: Record<Variant, string> = {
  primary:   "bg-brand text-white shadow-sm hover:bg-brand-hover active:bg-brand-press",
  secondary: "bg-paper-hi text-ink border-rule hover:bg-paper-sunk",
  ghost:     "bg-transparent text-ink hover:bg-paper-sunk",
  danger:    "bg-danger text-white hover:brightness-95",
  link:      "bg-transparent text-brand underline underline-offset-4 px-0 h-auto",
};

export function Button({
  variant = "secondary", size = "md", fullWidth, className = "", children, ...rest
}: Props) {
  return (
    <button
      className={`${base} ${sizes[size]} ${variants[variant]} ${fullWidth ? "w-full" : ""} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
