import * as React from "react";
import { createComponent } from "./create-component.js";

const PopoverEl = createComponent({
  tag: "nm-popover",
  events: { onNmClose: "nm:close" },
});

interface Ctx {
  open: boolean;
  setOpen: (v: boolean) => void;
}
const PopoverContext = React.createContext<Ctx | null>(null);

export function Popover({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  return (
    <PopoverContext.Provider value={{ open, setOpen }}>
      {children}
    </PopoverContext.Provider>
  );
}

export function PopoverTrigger({ children }: { children: React.ReactElement<any> }) {
  const ctx = React.useContext(PopoverContext)!;
  return React.cloneElement(children, {
    onClick: (e: React.MouseEvent) => {
      children.props.onClick?.(e);
      ctx.setOpen(!ctx.open);
    },
  });
}

export function PopoverAnchor({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function PopoverContent({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ctx = React.useContext(PopoverContext)!;
  return React.createElement(
    PopoverEl,
    {
      class: className,
      open: ctx.open,
      onNmClose: () => ctx.setOpen(false),
    },
    children,
  );
}
