import * as React from "react";
import { toast as nmToast } from "@notemeld/ui";

// Toaster：nm-toast-stack 在首次调用 toast() 时自动创建并挂到 body，无需真实 DOM。
export function Toaster(_: React.HTMLAttributes<HTMLElement>) {
  return null;
}

// 兼容简单调用：toast.success/error/message。
export const toast = {
  success: (title: string, body?: string) => nmToast({ title, body, tone: "success" }),
  error: (title: string, body?: string) => nmToast({ title, body, tone: "danger" }),
  warning: (title: string, body?: string) => nmToast({ title, body, tone: "warning" }),
  message: (title: string, body?: string) => nmToast({ title, body }),
};
