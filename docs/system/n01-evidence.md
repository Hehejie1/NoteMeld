# N01 evidence

状态：`Implemented`（desktop artifact pinned；Android/iOS/Harmony runtime 按授权跳过）

| Goal | 命令/证据 | 结果 | 失败或阻塞 |
| --- | --- | --- | --- |
| SDK artifact intake | S08 handoff；`PYTHONPATH=backend pytest -q backend/tests/agent_host/test_runtime_loader.py`; fixed wheel unpack + `AgentSdkRuntime.load()` | 通过：desktop bundle `dist-native/x86_64-apple-darwin`；manifest `0bbe30e7f2e6b0e232f51dc79a6fc6615a0e3756690a79ae99d3f7a6ebf52a80`；wheel `ea9f807298c22e63cb81ab6683ae97fd72470bfce52ee193bf540ca11f99e964`；native `f6b58118f4734b19c795e5e4866eb4e5e19093c4ba4bf43e68c69293bba66cf8`；version/schema/ABI/native/binding/hash fail-closed；Android/iOS/Harmony runtime按授权跳过 | 共享 `.venv` 旧 wheel 不具备固定 native hash，按设计拒绝；启动器必须使用 pinned wheel |
| URL capability baseline | `python3 scripts/generate_url_capability_baseline.py`; `PYTHONPATH=backend pytest -q backend/tests/test_n01_url_capability_baseline.py` | 自动从 downloader registry、URL validator、采集/网页链路和现有回归测试生成 `backend/tests/fixtures/n01-url-capability-baseline.json`；覆盖 7 个 registry platform | `tiktok` 只有 registry entry，URL validator 未提供独立 pattern，记录为 `registry-only`，不自行补能力 |
| Note authority / DTO seam | `PYTHONPATH=backend pytest -q backend/tests/agent_host/test_note_contract.py` | `note_documents.task_id` → opaque NoteId；authority/projection boundary 与 SDK DTO/adapter ports 已冻结 | 具体 SDK operation/store adapter 属 N02 |

固定 handoff identity：source commit `f926bd7674c98b27895734c0df18e0c0241cb132`；SDK/schema/ABI `0.1.0 / 1 / 1`；Note wire `note-agent-v1`。N01 不绑定 SDK checkout、当前 HEAD 或开发快照；只接受上述 pinned desktop wheel/native bundle。
