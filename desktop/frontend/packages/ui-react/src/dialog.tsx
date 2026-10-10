import * as React from "react";
import { createComponent } from "./create-component.js";

interface DialogCtx {
  open: boolean;
  setOpen: (v: boolean) => void;
}
const DialogContext = React.createContext<DialogCtx | null>(null);

export interface DialogProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (v: boolean) => void;
  children: React.ReactNode;
}

// Dialog：兼容 ui-web（Radix）复合 API，内部驱动 nm-modal web component。
export function Dialog({ open, defaultOpen, onOpenChange, children }: DialogProps) {
  const [internal, setInternal] = React.useState(defaultOpen ?? false);
  const current = open ?? internal;
  const setOpen = React.useCallback(
    (v: boolean) => {
      if (open === undefined) setInternal(v);
      onOpenChange?.(v);
    },
    [open, onOpenChange],
  );
  return (
    <DialogContext.Provider value={{ open: current, setOpen }}>
      {children}
    </DialogContext.Provider>
  );
}

// 触发器：包裹 children，点击打开。
export function DialogTrigger({
  children,
  asChild,
}: {
  children: React.ReactElement<any>;
  asChild?: boolean;
}) {
  const ctx = React.useContext(DialogContext)!;
  void asChild;
  return React.cloneElement(children, {
    onClick: (e: React.MouseEvent) => {
      children.props.onClick?.(e);
      ctx.setOpen(true);
    },
  });
}

export function DialogClose({ children }: { children: React.ReactElement<any> }) {
  const ctx = React.useContext(DialogContext)!;
  return React.cloneElement(children, {
    onClick: (e: React.MouseEvent) => {
      children.props.onClick?.(e);
      ctx.setOpen(false);
    },
  });
}

const ModalEl = createComponent({
  tag: "nm-modal",
  events: { onNmClose: "nm:close" },
});

// 内容：把 title/children/footer 投影到 nm-modal。
export function DialogContent({
  children,
  className,
  showCloseButton = true,
  ...rest
}: React.HTMLAttributes<HTMLElement> & { showCloseButton?: boolean }) {
  const ctx = React.useContext(DialogContext)!;
  const handleClose = React.useCallback(() => ctx.setOpen(false), [ctx]);

  // 拆分 header/footer（业务中用 <DialogHeader> 等），其余作为 body。
  return React.createElement(
    ModalEl,
    {
      ...rest,
      class: className,
      open: ctx.open,
      onNmClose: handleClose,
      "data-show-close": showCloseButton,
    },
    children,
  );
}

export function DialogHeader(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="dialog-header" {...props} />;
}
export function DialogFooter(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div slot="footer" data-slot="dialog-footer" {...props} />;
}
export function DialogTitle(props: React.HTMLAttributes<HTMLElement>) {
  return <div slot="title" data-slot="dialog-title" {...props} />;
}
export function DialogDescription(props: React.HTMLAttributes<HTMLElement>) {
  return <div data-slot="dialog-description" {...props} />;
}
export function DialogOverlay() {
  return null;
}
export function DialogPortal({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
