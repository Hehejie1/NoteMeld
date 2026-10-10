import * as React from "react";

type FeedbackProps = {
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
};
type FeedbackSectionProps = FeedbackProps &
  Omit<React.HTMLAttributes<HTMLElement>, "title">;

// 空/错/离线/加载状态：与 ui-web 行为一致的纯展示组件（样式来自 token/全局）。
export function Feedback({
  title,
  description,
  action,
  className,
  role = "status",
  ...props
}: FeedbackSectionProps) {
  return (
    <section
      role={role}
      className={
        "flex min-h-32 flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center " +
        (className ?? "")
      }
      {...props}
    >
      {title ? <h2 className="text-sm font-semibold">{title}</h2> : null}
      {description ? (
        <p className="max-w-prose text-sm opacity-70">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </section>
  );
}

export function EmptyState(props: FeedbackSectionProps) {
  return <Feedback {...props} role="status" />;
}
export function ErrorState(props: FeedbackSectionProps) {
  return <Feedback {...props} role="alert" />;
}
export function OfflineState(props: FeedbackSectionProps) {
  return <Feedback {...props} role="status" />;
}
export function LoadingState({
  title = "Loading",
  ...props
}: FeedbackSectionProps) {
  return <Feedback title={title} {...props} aria-live="polite" />;
}
