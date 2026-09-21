# Change Spec：NoteMeld 目录职责收敛

更新时间：2026-09-02

## 当前现状

- 正式桌面源码位于 `desktop/backend/`、`desktop/frontend/` 和 `desktop/src-tauri/`。
- 根目录 `backend/`、`frontend/` 是迁移遗留副本；部分 Windows 启动脚本、测试和探针仍引用旧路径。
- 打包实现位于 `scripts/desktop/packaging/`；原型位于 `docs/architecture/prototypes/`；加密互操作 fixture 位于 `tests/fixtures/`。
- 桌面源码默认把运行数据和日志写入根目录 `vector_db/`、`logs/`，与代码目录职责混杂。

## 本次目标

- 所有桌面启动、测试、打包调用统一指向 `desktop/` 和 `scripts/desktop/`。
- 代码调用的互操作 fixture 放入 `tests/fixtures/`；目录协议说明留在 `docs/system/`。
- 桌面运行数据和日志分别放在 `desktop/data/`、`desktop/logs/`；云端数据使用 `cloud/data/` 或 `NOTEMELD_CLOUD_DATA_DIR` 持久卷。
- 原型移动到 `docs/architecture/prototypes/`，根目录不再保留 `prototypes/`、`packaging/`、`contracts/`。
- 引用确认后移除根目录遗留 `backend/`、`frontend/`。

## 不做

- 不修改 API、SQLite 表、Agent 状态机或业务语义。
- 不删除已有桌面数据；现有 `vector_db/` 和 `logs/` 迁移到新的桌面空间。
- 不把独立 `notemeld-applications` 仓库源码复制回本仓库。

## 测试与验收

- `desktop/backend` 可完成 compileall 和契约测试。
- `desktop/frontend` 可完成 contracts 和 build。
- 打包脚本、requirements、Windows/macOS 启动入口不再引用根 `backend/`、`frontend/`、`packaging/`、`contracts/`。
- `.gitignore` 忽略 `desktop/data/`、`desktop/logs/`、`cloud/data/`、`cloud/logs/`。
- 根目录只保留各端源码、文档、脚本、测试和配置，不保留运行数据、打包日志或设计原型。

## 回滚

- 代码路径迁移通过 Git rename 回滚。
- 运行数据迁移前后保持目录内容不变；如需回滚，将 `desktop/data/`、`desktop/logs/` 内容移回旧根目录。
