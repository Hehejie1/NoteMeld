import * as React from "react";

// Resizable：cloud-web 中以简单 flex 容器承接，保证布局与内容可用。
export function ResizablePanelGroup({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={"flex " + (className ?? "")} {...props}>
      {children}
    </div>
  );
}
export function ResizablePanel({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={"flex-1 min-w-0 " + (className ?? "")} {...props}>
      {children}
    </div>
  );
}
export function ResizableHandle(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="resizable-handle" {...props} />;
}
