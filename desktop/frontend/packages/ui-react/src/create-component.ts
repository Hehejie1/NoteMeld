import * as React from "react";
import { defineAll } from "@notemeld/ui";

// 幂等注册：模块加载时确保所有 nm-* 自定义元素已注册（浏览器环境）。
let registered: Promise<void> | null = null;
if (typeof customElements !== "undefined") {
  registered = Promise.resolve(defineAll());
}
export function whenRegistered(): Promise<void> {
  return registered ?? Promise.resolve();
}

export interface WebComponentOptions {
  // 自定义元素标签名，如 "nm-button"
  tag: string;
  // 以 property（而非 attribute）设置的属性名集合（对象/数组等复杂值）
  properties?: string[];
  // 自定义事件映射：React prop 名 -> 监听的自定义事件名（nm:xxx）
  events?: Record<string, string>;
  // 是否把 children 渲染到默认 slot（默认 true）
  defaultSlot?: boolean;
  // 把 children 包进稳定的 <span slot="default">：nm-* 的 renderNow 会物理重排
  // light DOM 子节点，直接传入的 React 子树会被 innerHTML 重置抹掉并在后续
  // reconciliation 触发 removeChild NotFoundError。包装后整棵子树作为单元被
  // 投影，内部引用保持有效（用于 Button/Badge 等内容型组件）。
  wrapSlotChildren?: boolean;
}

function isEmpty(v: unknown): boolean {
  return v === undefined || v === null;
}

// 通用 Web Components -> React 包装器。
// React 19 已能透传基础 props/事件到自定义元素；这里统一处理
// 复杂 property、nm: 自定义事件、class 透传与 ref。
export function createComponent(
  options: WebComponentOptions,
): React.ForwardRefExoticComponent<
  Record<string, unknown> & React.RefAttributes<HTMLElement>
> {
  const { tag, properties = [], events = {}, defaultSlot = true, wrapSlotChildren = false } = options;

  const Comp = React.forwardRef<HTMLElement, Record<string, unknown>>(
    function Comp(props, ref) {
      const innerRef = React.useRef<HTMLElement | null>(null);
      const { children, className, ...rest } = props as {
        children?: React.ReactNode;
        className?: string;
        [key: string]: unknown;
      };

      const setRef = React.useCallback(
        (node: HTMLElement | null) => {
          innerRef.current = node;
          if (typeof ref === "function") ref(node);
          else if (ref)
            (ref as React.MutableRefObject<HTMLElement | null>).current = node;
        },
        [ref],
      );

      // 复杂 property 同步（每次渲染后）。
      React.useLayoutEffect(() => {
        const el = innerRef.current;
        if (!el) return;
        for (const key of properties) {
          if (key in rest) {
            (el as unknown as Record<string, unknown>)[key] = (
              rest as Record<string, unknown>
            )[key];
          }
        }
      });

      // 自定义事件（nm:xxx）显式监听。
      React.useLayoutEffect(() => {
        const el = innerRef.current;
        if (!el) return;
        const cleanups: Array<() => void> = [];
        for (const [propName, eventName] of Object.entries(events)) {
          const handler = (rest as Record<string, unknown>)[propName];
          if (typeof handler === "function") {
            const listener = (e: Event) =>
              (handler as (ev: Event) => void)(e);
            el.addEventListener(eventName, listener);
            cleanups.push(() => el.removeEventListener(eventName, listener));
          }
        }
        return () => cleanups.forEach(fn => fn());
      });

      // 过滤掉以 property / 自定义事件方式处理的 props，其余作为 attribute。
      const handled = new Set<string>([
        ...properties,
        ...Object.keys(events),
      ]);
      const attrProps: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(rest)) {
        if (handled.has(key) || isEmpty(value)) continue;
        attrProps[key] = value;
      }

      // 包装 span 始终渲染（即使 children 为空）：保证 React 侧永不增删该节点，
      // 只在其内部做增删，避免 span 被 nm-* 投影移动后 React 仍按宿主子节点删除。
      const content =
        defaultSlot && wrapSlotChildren
          ? React.createElement(
              "span",
              { slot: "default", "data-nm-react-slot": "", style: { display: "contents" } },
              children ?? null,
            )
          : defaultSlot
            ? children
            : null;

      return React.createElement(
        tag,
        { ...attrProps, class: className as string, ref: setRef },
        content,
      );
    },
  );

  Comp.displayName = tag;
  return Comp;
}
