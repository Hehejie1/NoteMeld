import * as React from "react";
import { createComponent } from "./create-component.js";

const Wrapped = createComponent({
  tag: "nm-checkbox",
  events: { onNmChange: "nm:change" },
});

export interface CheckboxProps {
  checked?: boolean;
  disabled?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  className?: string;
  id?: string;
  // 允许 data-* / aria-* / name 等属性透传到 nm-checkbox
  [key: string]: unknown;
}

export function Checkbox({
  checked,
  disabled,
  onCheckedChange,
  className,
  id,
  ...rest
}: CheckboxProps) {
  const handle = React.useCallback(
    (e: Event) => {
      const v = (e as CustomEvent<{ checked?: boolean }>).detail?.checked;
      onCheckedChange?.(Boolean(v));
    },
    [onCheckedChange],
  );
  return React.createElement(Wrapped, {
    ...rest,
    id,
    class: className,
    checked,
    disabled,
    onNmChange: handle,
  });
}
