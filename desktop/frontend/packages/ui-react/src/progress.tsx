import * as React from "react";
import { createComponent } from "./create-component.js";

const Wrapped = createComponent({ tag: "nm-progress" });

export interface ProgressProps extends React.HTMLAttributes<HTMLElement> {
  value?: number | null;
}

export function Progress({ value = 0, ...props }: ProgressProps) {
  const normalized = Math.min(100, Math.max(0, Number.isFinite(value) ? Number(value) : 0));
  return React.createElement(Wrapped, {
    ...props,
    value: normalized,
    role: "progressbar",
    "aria-valuemin": 0,
    "aria-valuemax": 100,
    "aria-valuenow": normalized,
  });
}
