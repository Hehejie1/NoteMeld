import * as React from "react";

// Label：web component 体系内直接渲染原生 label（语义与样式由 token 提供）。
export type LabelProps = React.LabelHTMLAttributes<HTMLLabelElement>;

export const Label = React.forwardRef<HTMLLabelElement, LabelProps>(function Label(
  props,
  ref,
) {
  return <label ref={ref} {...props} />;
});
