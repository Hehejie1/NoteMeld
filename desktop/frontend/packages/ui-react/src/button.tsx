import * as React from "react";
import { createComponent } from "./create-component.js";

// nm-button：variant 取值与 ui-web 不同，这里做映射以兼容现有业务代码。
type UIVariant = "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
type UISize = "default" | "sm" | "lg" | "icon";

const variantMap: Record<UIVariant, string> = {
  default: "primary",
  destructive: "danger",
  outline: "secondary",
  secondary: "secondary",
  ghost: "ghost",
  link: "link",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: UIVariant;
  size?: UISize;
  asChild?: boolean;
}

const Wrapped = createComponent({
  tag: "nm-button",
  events: { onNmPress: "nm:press" },
  // nm-button renderNow 会抹掉非 slot 子节点（如图标切换），必须包投影单元。
  wrapSlotChildren: true,
});

export const buttonVariants = (opts?: { variant?: UIVariant; size?: UISize }) =>
  [
    "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors",
    opts?.variant ? `nm-variant-${opts.variant}` : "",
    opts?.size ? `nm-size-${opts.size}` : "",
  ].join(" ");

export const Button = React.forwardRef<HTMLElement, ButtonProps>(function Button(
  { variant = "default", size = "default", type = "button", ...props },
  ref,
) {
  return React.createElement(Wrapped, {
    ...props,
    ref,
    variant: variantMap[variant],
    size: size === "default" ? "md" : size === "icon" ? "md" : size,
    type,
  });
});
