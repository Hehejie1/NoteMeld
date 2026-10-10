import * as React from "react";
import { createComponent } from "./create-component.js";

// nm-switch：checked 为 boolean property；onCheckedChange 回调布尔值。
const Wrapped = createComponent({
  tag: "nm-switch",
  events: { onNmChange: "nm:change" },
});

export interface SwitchProps {
  checked?: boolean;
  defaultChecked?: boolean;
  disabled?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  className?: string;
}

export function Switch({ checked, disabled, onCheckedChange, className }: SwitchProps) {
  const handle = React.useCallback(
    (e: Event) => {
      const v = (e as CustomEvent<{ checked?: boolean }>).detail?.checked;
      onCheckedChange?.(Boolean(v));
    },
    [onCheckedChange],
  );
  return React.createElement(Wrapped, {
    class: className,
    checked,
    disabled,
    onNmChange: handle,
  });
}
