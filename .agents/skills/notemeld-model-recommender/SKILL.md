---
name: "notemeld-model-recommender"
description: "当用户需要为 NoteMeld 选择、推荐或评估本地运行的 LLM 模型时触发。根据用户设备信息（可自动检测或用户传入）和公开排行榜数据，综合 NoteMeld 系统评测指标，同时推荐适合视频总结的多模态模型和适合 Agent 对话的纯文本推理模型，各推荐 5 个。"
---

# NoteMeld 本地模型推荐

## 核心规则

### ⚠️ 硬性限制（必须遵守，违反即为错误）

**以下规则优先于任何排行榜数据或模型评分。**

#### 规则 1: 按设备架构限制最大参数规模

根据 CPU 架构、是否有独立 GPU，严格控制推荐的模型参数上限。超出以下范围的模型 **绝对不能推荐**：

| 设备类型 | 最大多模态模型参数 | 最大纯文本模型参数 | 判断依据 |
|----------|-------------------|-------------------|----------|
| **Intel Mac 无独立 GPU** (x86_64 + GPU VRAM ≤ 2GB) | 8B | 8B | CPU 推理无 GPU 加速，超过 8B 速度 <5 tok/s 不可用 |
| **Intel Mac 有独立 GPU** (x86_64 + GPU VRAM > 2GB) | 14B | 32B | 可用独立 GPU 推理 |
| **Apple Silicon M 系列** (arm64) | 32B | 72B | 统一内存架构 + ANE 加速 |
| **Windows/Linux 有 NVIDIA GPU** (CUDA, VRAM ≥ 8GB) | 32B | 70B | GPU 推理速度快 |
| **Windows/Linux 无 GPU** | 7B | 14B | CPU 推理 |
| **内存 ≤ 8GB 的设备** | 4B | 4B | 内存太小，大模型跑不了 |

**判断方法**：
- `has_apple_silicon == true` → Apple Silicon
- `platform == "Darwin" && has_apple_silicon == false && gpu_vram_gb <= 2` → Intel Mac 无独立 GPU（最严格限制）
- `gpu_vram_gb > 2` → 有独立 GPU
- `ram_gb <= 8` → 低内存设备

#### 规则 2: Intel Mac 无独立 GPU 必须加 CPU 推理速度惩罚

对 **Intel Mac 无独立 GPU**，打分时速度权重必须从 15% 提升到 **35%**，因为 CPU 推理速度是用户体验的瓶颈。

参数规模对应的 CPU 推理速度预估（Intel 6 核无 GPU）：
- ≤4B: 15-20 tok/s → 正常可用
- 7B-8B: 5-8 tok/s → 可用但偏慢
- 14B+: 1-3 tok/s → 不可用（打字速度都不如）
- 27B+: <1 tok/s → 绝对禁止推荐

#### 规则 3: 必须标注 CPU/GPU 推理实际速度

每个推荐必须标注：
- 预估推理速度（tok/s）
- 推理方式（CPU / GPU / Apple ANE）
- 如果速度 <5 tok/s，必须标红/标⚠️，并说明"速度较慢，日常使用可能不舒适"

#### 规则 4: 已安装模型优先 + 诚实标注

- 用户已安装的模型（`ollama_models` 列表中的），优先展示，标注 ✅已装
- 数据库中没有的新模型，Agent 联网搜索后可以加入推荐，但必须说明是搜索结果，且必须遵守规则 1 的参数限制
- 禁止编造模型性能数据，所有数据必须有来源

---

### 基本规则

NoteMeld 有两个核心场景，**两类模型都必须推荐**：

- **场景 A: Workflow 视频总结** → 需要多模态模型（multimodal），能理解视频截图/图片内容、OCR、场景描述
- **场景 B: Agent 对话** → 需要纯文本推理模型（text_only），处理文本检索和生成

不要让用户选择类型，直接同时输出两类推荐，各 5 个。

## 执行流程

### 步骤 1: 获取设备信息

- **用户传了设备信息**（如 `--device-json '{"ram_gb":32}'`）→ 直接使用
- **用户没传** → 执行内部脚本自动检测：

```bash
python3 scripts/model_recommender.py --detect-device
```

脚本内嵌采集 CPU 核心数、内存、GPU、Apple Silicon 检测、Ollama 状态，支持 macOS/Linux/Windows。

**拿到设备信息后，先按上面的硬性规则 1 判断属于哪类设备，确定最大参数上限。后续所有推荐都不能超过这个上限。**

### 步骤 2: 联网搜索最新公开排行榜

Agent 需要搜索以下数据源，获取最新的模型评测数据（幻觉率、MMLU、HumanEval 等）：

**必须搜索的数据源：**

1. **Vectara HHEM 幻觉率排行榜**
   - URL: https://huggingface.co/spaces/vectara/leaderboard
   - 获取: 各模型的 Hallucination Rate（越低越好）
   - 更新频率: 持续更新

2. **HuggingFace Open LLM Leaderboard**
   - URL: https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard
   - 获取: MMLU、ARC、HellaSwag、Winogrande、GSM8K 等综合能力分数
   - 更新频率: 月度

3. **Ollama 官方模型库**
   - URL: https://ollama.com/library
   - 获取: 可用模型列表、参数规模、量化版本
   - 更新频率: 持续

**可选补充数据源：**

4. **LLMCheck 本地 LLM 索引** — https://llmcheck.net — 本地运行性能对比
5. **Artificial Analysis** — https://artificialanalysis.ai — 速度/成本/质量综合对比

搜索时关注：
- 模型是否在 Ollama 上可用（用户通过 Ollama 运行）
- 最新版本信息（模型更新换代很快，优先用最新数据）
- 中文相关评测（NoteMeld 核心是中文场景）
- **参数规模是否超过该设备的硬性上限（规则 1），超过则直接跳过**

### 步骤 3: 读取本地测试结果

读取 `tests/reports/` 目录下已有的评测报告，作为本地测试参考：

- `tests/reports/evaluation_report.json` — Workflow 评测结果（ROUGE、幻觉率）
- `tests/reports/retrieval_eval_*.md` — Agent 检索评测结果（Recall@k、MRR）

如果本地没有测试结果，跳过此步骤，仅依赖公开数据。

### 步骤 4: 综合 NoteMeld 系统指标打分排名

#### 通用权重调整规则

| 设备类型 | 速度权重 | 幻觉率权重 | 综合能力权重 | 原因 |
|----------|---------|-----------|-------------|------|
| Intel Mac 无独立 GPU | **35%** | 35% | 30% | CPU 推理，速度是体验瓶颈 |
| Apple Silicon M1/M2 | 20% | 35% | 45% | ANE 加速快，优先看质量 |
| 有独立 NVIDIA GPU | 20% | 35% | 45% | GPU 推理快，优先看质量 |
| 低内存设备 (≤8GB) | **30%** | 30% | 40% | 内存限制参数，速度和质量平衡 |

#### 场景 A: 多模态模型排名指标（视频总结）

| 指标 | 含义 | 基准权重 | Intel Mac 无 GPU 时 |
|------|------|---------|-------------------|
| 幻觉率 | 生成内容中未基于原文的比例（越低越好） | 35% | 35% |
| 模板遵循度 | 笔记段落完整性、`*Screenshot-[mm:ss]` 格式、时间戳准确性 | 25% | 20% |
| 章节召回率 | 模板要求的所有章节是否都出现 | 15% | 10% |
| 引用正确率 | `*Content-[mm:ss]` 和 `*Screenshot-[mm:ss]` 时间点准确性 | 15% | 10% |
| **推理速度** | tok/s，<5 tok/s 必须打⚠️ | 10% | **25%** |

#### 场景 B: 纯文本模型排名指标（Agent 对话）

| 指标 | 含义 | 基准权重 | Intel Mac 无 GPU 时 |
|------|------|---------|-------------------|
| Recall@10 | 前 10 条检索结果中包含正确答案的比例 | 30% | 25% |
| Recall@5 | 前 5 条中包含正确答案的比例 | 20% | 15% |
| MRR | 正确答案排名倒数均值（越靠前越好） | 25% | 15% |
| 引用准确率 (Top-1) | 第一条结果就是正确答案的比例 | 25% | 10% |
| **推理速度** | tok/s，<5 tok/s 必须打⚠️ | - | **35%** |

### 步骤 5: 输出推荐结果

**多模态模型 Top 5**（视频总结用）+ **纯文本模型 Top 5**（Agent 对话用）

每个推荐必须包含：
- 模型名称、参数规模、模型类型标注（🖼️ 多模态 / 📝 纯文本）
- ✅已装 或 ⬇️未装 状态
- 预估推理速度（含推理方式标注：CPU / GPU / ANE）
- 速度 <5 tok/s 时加 ⚠️ 警告："CPU 推理较慢，日常使用可能不舒适"
- 综合评分及各维度得分
- 下载命令: `ollama pull <model>`
- 测试命令: `python3 tests/workflow/evaluate_model.py --model "<model>"`

**先过滤掉超过硬性参数上限的模型，再排名。**

## 执行命令

```bash
# 自动检测设备 + 推荐两类模型各 5 个（默认行为，已内置所有硬性规则）
python3 scripts/model_recommender.py

# 用户传入设备信息
python3 scripts/model_recommender.py --device-json '{"ram_gb":32,"has_apple_silicon":true}'

# 仅检测设备信息（不推荐）
python3 scripts/model_recommender.py --detect-device

# JSON 格式输出
python3 scripts/model_recommender.py --format json
```

## 注意事项

- 模型数据库数据会过时，Agent 执行时应优先使用联网搜索的最新公开数据
- 公开排行榜的幻觉率（Vectara HHEM）是英文场景的，中文幻觉率可能不同，需结合本地测试结果综合判断
- **Intel Mac 无独立 GPU 是最受限的设备，必须严格遵守参数上限（多模态≤8B，纯文本≤8B）**
- 首次使用建议从较小模型开始（3B-4B）快速验证，再逐步尝试更大模型
- 用户可以同时安装一个多模态模型（Workflow）和一个纯文本模型（Agent）以获得完整体验
- 如果推荐了速度 <5 tok/s 的模型，必须给出替代方案（小一个级别的更快模型）

## 本地测试

推荐模型后，用户可运行 NoteMeld 评测套件验证实际性能：

```bash
# Workflow 评测（多模态模型）
python3 tests/workflow/evaluate_model.py --model "<model-name>"

# Agent 检索评测（纯文本模型）
python3 tests/agent/evaluate_retrieval.py
```

评测结果输出到 `tests/reports/` 目录，可作为后续推荐的本地数据参考。
