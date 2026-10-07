/* ============================================================================
   NoteMeld · galaxy layer behavior
   纯 CSS 已覆盖 hover/focus/checked 的视觉；本脚本只补 CSS 做不到的行为契约：
     · Switch / Checkbox：把原生 checked 同步到 aria-checked，并暴露程序化切换；
     · 阻止 label 包裹下的重复触发；键盘交互由原生 input 天然支持（Space）。
   设计原则：无依赖、可被多次初始化（idempotent）、不改变 DOM 语义。
   ============================================================================ */
(() => {
  "use strict";

  const FLAG = "nmGalaxyReady";

  /* 为一个 switch/checkbox 输入绑定 aria 同步。 */
  const bindTogglable = input => {
    if (input.dataset[FLAG]) return;
    input.dataset[FLAG] = "1";
    const sync = () => {
      input.setAttribute("aria-checked", String(input.checked));
    };
    input.addEventListener("change", sync);
    sync();
  };

  const init = root => {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(".nm-switch-input, .nm-checkbox-input").forEach(bindTogglable);
  };

  /* 首屏初始化。 */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => init(document), { once: true });
  } else {
    init(document);
  }

  /* 暴露给业务代码：动态插入组件后调用。 */
  window.NmGalaxy = { init };
})();
