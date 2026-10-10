import * as React from "react";
import { createComponent } from "./create-component.js";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  onValueChange?: (value: string) => void;
}

const Wrapped = createComponent({
  tag: "nm-textarea",
  events: { onNmChange: "nm:change", onNmInput: "nm:input" },
});

export const Textarea = React.forwardRef<HTMLElement, TextareaProps>(function Textarea(
  { onChange, onValueChange, ...props },
  ref,
) {
  const handleChange = React.useCallback(
    (e: Event) => {
      const value =
        ((e.target as HTMLElement).querySelector("textarea") as HTMLTextAreaElement | null)?.value ??
        "";
      // 兼容桌面 ui-web（Radix 风格）的 onChange：cloud-web 下合成等价的 target.value
      onChange?.({
        target: { value },
        currentTarget: { value },
      } as unknown as React.ChangeEvent<HTMLTextAreaElement>);
      onValueChange?.(value);
    },
    [onChange, onValueChange],
  );
  // nm:input / nm:change 双监听，保证输入即时回调
  return React.createElement(Wrapped, {
    ...props,
    ref,
    onNmInput: handleChange,
    onNmChange: handleChange,
  });
});
