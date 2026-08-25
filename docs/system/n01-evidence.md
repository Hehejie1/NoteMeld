# N01 evidence

状态：`Pending external SDK artifact metadata`

| Goal | 命令/证据 | 结果 | 失败或阻塞 |
| --- | --- | --- | --- |
| SDK artifact intake | S08 handoff；`PYTHONPATH=backend pytest -q backend/tests/agent_host/test_runtime_loader.py` | 固定 SDK `0.1.0` / schema `1` / ABI `1` / Note wire `note-agent-v1` / source commit、manifest hash、native/binding/version fail-closed tests通过；Android/Harmony 按授权 `waived/skipped` | 当前已安装 wheel metadata 没有 source commit/manifest SHA-256，loader 按设计拒绝；需 SDK 交付带 provenance metadata 的固定 wheel |
| URL capability baseline | `python3 scripts/generate_url_capability_baseline.py`; `PYTHONPATH=backend pytest -q backend/tests/test_n01_url_capability_baseline.py` | 自动从 downloader registry、URL validator、采集/网页链路和现有回归测试生成 `backend/tests/fixtures/n01-url-capability-baseline.json`；覆盖 7 个 registry platform | `tiktok` 只有 registry entry，URL validator 未提供独立 pattern，记录为 `registry-only`，不自行补能力 |
| Note authority / DTO seam | `PYTHONPATH=backend pytest -q backend/tests/agent_host/test_note_contract.py` | `note_documents.task_id` → opaque NoteId；authority/projection boundary 与 SDK DTO/adapter ports 已冻结 | 具体 SDK operation/store adapter 属 N02 |

固定 handoff identity：source commit `f926bd7674c98b27895734c0df18e0c0241cb132`；SDK/schema/ABI `0.1.0 / 1 / 1`；Note wire `note-agent-v1`。N01 不绑定 SDK checkout、当前 HEAD 或开发快照。
