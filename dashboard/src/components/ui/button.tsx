import type { ButtonHTMLAttributes, Ref } from "react";
import { cn } from "@/lib/cn";

type ButtonVariant = "primary" | "secondary" | "ghost" | "amber" | "rose";
type ButtonSize = "md" | "sm" | "icon";

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-emerald text-[#03130c] hover:bg-emerald/90",
  secondary: "border border-line-strong bg-panel-2 text-ink hover:bg-panel-3",
  ghost: "text-muted hover:bg-white/[0.05] hover:text-ink",
  amber: "border border-amber/30 bg-amber/10 text-amber hover:bg-amber/15",
  rose: "border border-rose/30 bg-rose/10 text-rose hover:bg-rose/15",
};

const sizeClasses: Record<ButtonSize, string> = {
  md: "h-11 px-4 text-sm",
  sm: "h-9 px-3 text-[13px]",
  icon: "h-11 w-11",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  ref?: Ref<HTMLButtonElement>;
}

export function Button({
  variant = "secondary",
  size = "md",
  className,
  type = "button",
  ref,
  ...props
}: ButtonProps) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex select-none items-center justify-center gap-2 rounded-xl font-medium transition duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  );
}
