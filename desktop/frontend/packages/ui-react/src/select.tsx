import * as React from "react";
import { createComponent } from "./create-component.js";
import type { NmSelectOption } from "./select-types.js";

export type { NmSelectOption } from "./select-types.js";

interface SelectContextValue {
  value?: string;
  onValueChange?: (v: string) => void;
}
const SelectContext = React.createContext<SelectContextValue>({});

// 标记组件：用于在 children 中声明选项（实际由 Select 收集，不渲染）。
export function SelectItem(_: { value: string; children: React.ReactNode }) {
  return null;
}

export interface SelectProps {
  value?: string;
  defaultValue?: string;
  onValueChange?: (v: string) => void;
  children: React.ReactNode;
  disabled?: boolean;
}

// ReactNode -> 纯文本
function toText(node: React.ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(toText).join("");
  if (React.isValidElement(node)) return toText((node.props as { children?: React.ReactNode }).children);
  return "";
}

export function Select({ value, defaultValue, onValueChange, children, disabled }: SelectProps) {
  const [internal, setInternal] = React.useState(defaultValue);
  const current = value ?? internal;
  const change = React.useCallback(
    (v: string) => {
      if (value === undefined) setInternal(v);
      onValueChange?.(v);
    },
    [value, onValueChange],
  );

  // 选项可能出现在 SelectContent 内：递归收集整棵子树。
  const options = React.useMemo(() => collectAllItems(children), [children]);

  const handle = React.useCallback(
    (e: Event) => {
      const v = (e as CustomEvent<{ value?: string }>).detail?.value;
      if (typeof v === "string") change(v);
    },
    [change],
  );

  return (
    <SelectContext.Provider value={{ value: current, onValueChange: change }}>
      {React.createElement(
        createComponent({
          tag: "nm-select",
          properties: ["options"],
          events: { onNmChange: "nm:change" },
        }),
        {
          value: current,
          options,
          disabled,
          placeholder: "",
          onNmChange: handle,
        },
        // children 中可能含 trigger/value 占位，实际选项已走 options property。
        null,
      )}
    </SelectContext.Provider>
  );
}

function collectAllItems(node: React.ReactNode): NmSelectOption[] {
  const out: NmSelectOption[] = [];
  const walk = (n: React.ReactNode) => {
    React.Children.forEach(n, child => {
      if (!React.isValidElement(child)) return;
      if (child.type === SelectItem) {
        const p = child.props as { value: string; children: React.ReactNode };
        out.push({ value: p.value, label: toText(p.children) });
      } else {
        walk((child.props as { children?: React.ReactNode }).children);
      }
    });
  };
  walk(node);
  return out;
}

export function SelectTrigger({
  className,
  children,
  size = "default",
}: {
  className?: string;
  children?: React.ReactNode;
  size?: "sm" | "default";
}) {
  // nm-select 自带触发区；此组件仅用于兼容写法（不单独渲染）。
  void size;
  return <span hidden data-select-trigger className={className}>{children}</span>;
}
export function SelectValue({ placeholder }: { placeholder?: string }) {
  void placeholder;
  return null;
}
export function SelectContent({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
export function SelectGroup({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
export function SelectLabel({ children }: { children: React.ReactNode }) {
  return null;
}
export function SelectSeparator() {
  return null;
}
export function SelectScrollUpButton() {
  return null;
}
export function SelectScrollDownButton() {
  return null;
}
