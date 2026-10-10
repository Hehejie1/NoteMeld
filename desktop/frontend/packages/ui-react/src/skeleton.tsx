import * as React from "react";
import { createComponent } from "./create-component.js";

const Wrapped = createComponent({ tag: "nm-skeleton" });

export interface SkeletonProps extends React.HTMLAttributes<HTMLElement> {
  variant?: "text" | "circle" | "rect";
}

export const Skeleton = React.forwardRef<HTMLElement, SkeletonProps>(
  function Skeleton({ variant = "rect", ...props }, ref) {
    return React.createElement(Wrapped, { ...props, ref, kind: variant });
  },
);
