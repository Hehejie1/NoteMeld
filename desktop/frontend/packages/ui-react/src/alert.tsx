import * as React from "react";
import { createComponent } from "./create-component.js";

const Wrapped = createComponent({ tag: "nm-alert" });

type AlertVariant = "default" | "destructive" | "success" | "warning";
const toneMap: Record<AlertVariant, string> = {
  default: "info",
  destructive: "danger",
  success: "success",
  warning: "warning",
};

export function alertVariants(opts?: { variant?: AlertVariant }) {
  return `nm-alert-variant-${opts?.variant ?? "default"}`;
}

export interface AlertProps extends React.HTMLAttributes<HTMLElement> {
  variant?: AlertVariant;
}

export const Alert = React.forwardRef<HTMLElement, AlertProps>(function Alert(
  { variant = "default", ...props },
  ref,
) {
  return React.createElement(Wrapped, {
    ...props,
    ref,
    tone: toneMap[variant],
  });
});

export function AlertTitle(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="alert-title" {...props} />;
}
export function AlertDescription(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="alert-description" {...props} />;
}
