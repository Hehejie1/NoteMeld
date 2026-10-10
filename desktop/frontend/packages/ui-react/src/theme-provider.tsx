import * as React from "react";
import { ThemeProvider as NextThemesProvider, type ThemeProviderProps } from "next-themes";

// ThemeProvider：沿用 next-themes（class 策略），并额外把主题同步到
// @notemeld/ui Web Components 识别的 documentElement[data-theme]，
// 保证 nm-* 组件明暗 token 生效。
export function ThemeProvider({ children, ...props }: ThemeProviderProps) {
  return (
    <NextThemesProvider {...props}>
      <ThemeSync />
      {children}
    </NextThemesProvider>
  );
}

function ThemeSync() {
  React.useEffect(() => {
    const sync = () => {
      const root = document.documentElement;
      const dark = root.classList.contains("dark");
      root.setAttribute("data-theme", dark ? "dark" : "light");
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);
  return null;
}
