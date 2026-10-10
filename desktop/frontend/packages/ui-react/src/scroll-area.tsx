import * as React from "react";

export interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  orientation?: "vertical" | "horizontal" | "both";
}

// ScrollArea：直接渲染 overflow 容器（cloud-web 中视觉可接受，避免引入额外依赖）。
export const ScrollArea = React.forwardRef<HTMLDivElement, ScrollAreaProps>(
  function ScrollArea({ className, children, ...props }, ref) {
    return (
      <div
        ref={ref}
        className={"overflow-auto " + (className ?? "")}
        {...props}
      >
        {children}
      </div>
    );
  },
);

export function ScrollBar(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="scroll-bar" {...props} />;
}
