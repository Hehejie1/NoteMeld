import * as React from "react";
import { createComponent } from "./create-component.js";

// nm-card 支持 header/media/actions/footer + 默认 body。
const Wrapped = createComponent({ tag: "nm-card" });

export interface CardProps extends React.HTMLAttributes<HTMLElement> {
  title?: string;
}

export function Card({ title, children, ...props }: CardProps) {
  return React.createElement(
    Wrapped,
    props,
    title
      ? [
          <span key="extra" slot="extra" />,
          <div key="body">{children}</div>,
        ]
      : children,
  );
}

export function CardHeader(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-header" {...props} />;
}
export function CardTitle(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-title" {...props} />;
}
export function CardDescription(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-description" {...props} />;
}
export function CardAction(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-action" {...props} />;
}
export function CardContent(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-content" {...props} />;
}
export function CardFooter(props: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-footer" {...props} />;
}
