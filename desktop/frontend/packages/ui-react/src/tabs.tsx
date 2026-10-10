import * as React from "react";

interface TabsContextValue {
  value?: string;
  setValue: (v: string) => void;
}
const TabsContext = React.createContext<TabsContextValue | null>(null);

export interface TabsProps {
  value?: string;
  defaultValue?: string;
  onValueChange?: (v: string) => void;
  className?: string;
  children: React.ReactNode;
}

// Tabs：兼容 ui-web（Radix）复合 API；内部以 React 状态管理激活项，
// 视觉由 nm-tabs 的 CSS 类承载（不强制使用 web component 标签，
// 但语义与样式属于 @notemeld/ui 体系）。
export function Tabs({ value, defaultValue, onValueChange, className, children }: TabsProps) {
  const [internal, setInternal] = React.useState(defaultValue);
  const current = value ?? internal;
  const setValue = React.useCallback(
    (v: string) => {
      if (value === undefined) setInternal(v);
      onValueChange?.(v);
    },
    [value, onValueChange],
  );
  return (
    <TabsContext.Provider value={{ value: current, setValue }}>
      <div className={"nm-tabs flex flex-col gap-2 " + (className ?? "")}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={"nm-tabs__list inline-flex h-9 items-center rounded-lg p-[3px] " + (className ?? "")}>
      {children}
    </div>
  );
}

export function TabsTrigger({
  value,
  className,
  children,
  disabled,
}: {
  value: string;
  className?: string;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  const ctx = React.useContext(TabsContext)!;
  const active = ctx.value === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      disabled={disabled}
      data-state={active ? "active" : "inactive"}
      className={
        "nm-tabs__tab inline-flex h-8 items-center justify-center rounded-md px-3 text-sm font-medium transition-colors disabled:opacity-50 " +
        (active ? " is-active shadow-sm" : "") +
        (className ? " " + className : "")
      }
      onClick={() => ctx.setValue(value)}
    >
      {children}
    </button>
  );
}

export function TabsContent({
  value,
  className,
  children,
}: {
  value: string;
  className?: string;
  children: React.ReactNode;
}) {
  const ctx = React.useContext(TabsContext)!;
  if (ctx.value !== value) return null;
  return (
    <div role="tabpanel" className={"flex-1 " + (className ?? "")}>
      {children}
    </div>
  );
}
