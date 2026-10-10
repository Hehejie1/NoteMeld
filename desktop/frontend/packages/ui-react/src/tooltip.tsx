import * as React from "react";
import { createComponent } from "./create-component.js";

const TooltipEl = createComponent({
  tag: "nm-tooltip",
});

// TooltipProvider：兼容 ui-web；nm-tooltip 自身管理显隐。
export function TooltipProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

interface TooltipProps {
  children: React.ReactNode;
}
// Tooltip：收集 Trigger/Content，渲染为 nm-tooltip。
export function Tooltip({ children }: TooltipProps) {
  let trigger: React.ReactNode = null;
  let content = "";
  React.Children.forEach(children, child => {
    if (!React.isValidElement(child)) return;
    if (child.type === TooltipTrigger) {
      trigger = (child.props as { children: React.ReactNode }).children;
    } else if (child.type === TooltipContent) {
      content = String((child.props as { children: React.ReactNode }).children ?? "");
    }
  });
  return React.createElement(TooltipEl, { content }, trigger);
}

export function TooltipTrigger({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
export function TooltipContent({ children }: { children: React.ReactNode; side?: string }) {
  return <>{children}</>;
}

