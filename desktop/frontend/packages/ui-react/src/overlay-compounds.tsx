import * as React from "react";
import { createComponent } from "./create-component.js";

function makeOverlayCompound(tag: string) {
  const El = createComponent({ tag, events: { onNmClose: "nm:close" } });

  interface Ctx {
    open: boolean;
    setOpen: (v: boolean) => void;
  }
  const Context = React.createContext<Ctx | null>(null);

  function Root({ children }: { children: React.ReactNode }) {
    const [open, setOpen] = React.useState(false);
    return <Context.Provider value={{ open, setOpen }}>{children}</Context.Provider>;
  }
  function Trigger({ children }: { children: React.ReactElement<any> }) {
    const ctx = React.useContext(Context)!;
    return React.cloneElement(children, {
      onClick: (e: React.MouseEvent) => {
        children.props.onClick?.(e);
        ctx.setOpen(true);
      },
    });
  }
  function Close({ children }: { children: React.ReactElement<any> }) {
    const ctx = React.useContext(Context)!;
    return React.cloneElement(children, {
      onClick: (e: React.MouseEvent) => {
        children.props.onClick?.(e);
        ctx.setOpen(false);
      },
    });
  }
  function Content({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) {
    const ctx = React.useContext(Context)!;
    return React.createElement(
      El,
      { class: className, open: ctx.open, onNmClose: () => ctx.setOpen(false) },
      children,
    );
  }
  return { Root, Trigger, Close, Content, Context };
}

const sheet = makeOverlayCompound("nm-sheet");
export const Sheet = sheet.Root;
export const SheetTrigger = sheet.Trigger;
export const SheetClose = sheet.Close;
export const SheetContent = sheet.Content;
export function SheetHeader(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="sheet-header" {...props} />;
}
export function SheetTitle(props: React.HTMLAttributes<HTMLElement>) {
  return <span slot="title" {...props} />;
}
export function SheetDescription(props: React.HTMLAttributes<HTMLElement>) {
  return <div data-slot="sheet-description" {...props} />;
}
export function SheetFooter(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div slot="footer" {...props} />;
}

const drawer = makeOverlayCompound("nm-drawer");
export const Drawer = drawer.Root;
export const DrawerTrigger = drawer.Trigger;
export const DrawerClose = drawer.Close;
export const DrawerContent = drawer.Content;
export function DrawerHeader(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="drawer-header" {...props} />;
}
export function DrawerTitle(props: React.HTMLAttributes<HTMLElement>) {
  return <span slot="title" {...props} />;
}
export function DrawerDescription(props: React.HTMLAttributes<HTMLElement>) {
  return <div data-slot="drawer-description" {...props} />;
}
export function DrawerFooter(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div slot="footer" {...props} />;
}
