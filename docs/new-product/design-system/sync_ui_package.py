#!/usr/bin/env python3
"""把 @notemeld/ui 的产物同步到 new-product 供静态预览使用。

new-product 的预览服务器以 docs/new-product 为根，无法直接跨目录链接
packages/ 下的文件，因此本脚本把组件包的产物复制到
design-system/vendor/notemeld-ui/：

  - notemeld-ui.min.js  浏览器即用单文件（样式内联，自动注册全部组件）
  - tokens.css / components.css  仅需 CSS 时的等价样式

组件真源仍在 packages/notemeld-ui，本脚本只做单向镜像，请勿手改 vendor 副本。

用法（仓库根或本目录均可）：
    python3 docs/new-product/design-system/sync_ui_package.py
"""
from __future__ import annotations

import datetime as _dt
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
# docs/new-product/design-system -> 仓库根需要上溯 4 级
REPO_ROOT = HERE.parents[3]
PKG = REPO_ROOT / "packages" / "notemeld-ui"
PKG_SRC_CORE = PKG / "src" / "core"
PKG_DIST = PKG / "dist"
DEST = HERE / "vendor" / "notemeld-ui"

# (源, 目标文件名)
FILES = [
    (PKG_SRC_CORE / "tokens.css", "tokens.css"),
    (PKG_SRC_CORE / "components.css", "components.css"),
    (PKG_DIST / "notemeld-ui.min.js", "notemeld-ui.min.js"),
]


def main() -> None:
    missing = [str(src) for src, _ in FILES if not src.is_file()]
    if missing:
        raise SystemExit(
            "缺少组件包产物，请先在 packages/notemeld-ui 运行 pnpm build：\n  - "
            + "\n  - ".join(missing)
        )
    DEST.mkdir(parents=True, exist_ok=True)
    for src, name in FILES:
        (DEST / name).write_bytes(src.read_bytes())

    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    notice = (
        "/* 自动生成，请勿手改。\n"
        " * 来源：@notemeld/ui（packages/notemeld-ui）\n"
        f" * 同步时间：{stamp}\n"
        " * 重新生成：python docs/new-product/design-system/sync_ui_package.py\n"
        " */\n"
    )
    for src, name in FILES:
        if not name.endswith(".css"):
            continue
        path = DEST / name
        path.write_text(notice + path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"已同步 @notemeld/ui -> {DEST}")


if __name__ == "__main__":
    main()
