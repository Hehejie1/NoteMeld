import * as React from "react";
import { createComponent } from "./create-component.js";

// nm-badge 与 nm-button 同样会重排子节点，children 需要包装投影单元。
const Wrapped = createComponent({ tag: "nm-badge", wrapSlotChildren: true });

type BadgeVariant = "default" | "secondary" | "destructive" | "outline";
const toneMap: Record<BadgeVariant, string> = {
  default: "info",
  secondary: "neutral",
  destructive: "danger",
  outline: "neutral",
};

export interface BadgeProps extends React.HTMLAttributes<HTMLElement> {
  variant?: BadgeVariant;
}

export function badgeVariants(opts?: { variant?: BadgeVariant }) {
  return `nm-badge-variant-${opts?.variant ?? "default"}`;
}

export const Badge = React.forwardRef<HTMLElement, BadgeProps>(function Badge(
  { variant = "default", ...props },
  ref,
) {
  return React.createElement(Wrapped, {
    ...props,
    ref,
    tone: toneMap[variant],
  });
});
