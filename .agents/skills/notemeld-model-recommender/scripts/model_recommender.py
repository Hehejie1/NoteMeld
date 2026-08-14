#!/usr/bin/env python3
"""
NoteMeld 本地模型推荐 Skill — 内部执行脚本

由 .trae/skills/notemeld-model-recommender/SKILL.md 调用，不单独使用。
根据用户设备信息和公开排行榜数据，为用户推荐适合本地运行的模型。

用法（由 Skill 调用）:
    python3 .trae/skills/notemeld-model-recommender/model_recommender.py
    python3 .trae/skills/notemeld-model-recommender/model_recommender.py --device-json '{"ram_gb":32}'
    python3 .trae/skills/notemeld-model-recommender/model_recommender.py --detect-device
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ============================================================
# 内嵌设备信息采集
# ============================================================

def collect_device_info() -> dict:
    """
    采集当前设备硬件信息（内嵌版，无需外部依赖）
    
    Returns:
        包含设备信息的字典
    """
    info = {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_cores": 0,
        "ram_gb": 0,
        "gpu_model": "未检测到",
        "gpu_vram_gb": 0,
        "has_apple_silicon": False,
        "ollama_available": False,
        "ollama_models": [],
        "collected_at": datetime.now().isoformat(),
    }

    # 检测 Apple Silicon
    info["has_apple_silicon"] = platform.machine() == "arm64" and platform.system() == "Darwin"

    # 获取 CPU 核心数
    try:
        if info["platform"] == "Darwin":
            result = subprocess.run(["sysctl", "-n", "hw.physicalcpu"], capture_output=True, text=True, timeout=5)
            info["cpu_cores"] = int(result.stdout.strip()) if result.returncode == 0 else os.cpu_count() or 0
        elif info["platform"] == "Linux":
            result = subprocess.run(["nproc"], capture_output=True, text=True, timeout=5)
            info["cpu_cores"] = int(result.stdout.strip()) if result.returncode == 0 else os.cpu_count() or 0
        elif info["platform"] == "Windows":
            info["cpu_cores"] = os.cpu_count() or 0
        else:
            info["cpu_cores"] = os.cpu_count() or 0
    except Exception:
        info["cpu_cores"] = os.cpu_count() or 0

    # 获取内存
    try:
        if info["platform"] == "Darwin":
            result = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                ram_bytes = int(result.stdout.strip())
                info["ram_gb"] = round(ram_bytes / (1024 ** 3), 1)
        elif info["platform"] == "Linux":
            result = subprocess.run(["free", "-b"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("Mem:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            info["ram_gb"] = round(int(parts[1]) / (1024 ** 3), 1)
                        break
        elif info["platform"] == "Windows":
            result = subprocess.run(["wmic", "OS", "get", "TotalVisibleMemorySize"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                if len(lines) >= 2:
                    ram_kb = int(lines[1].strip())
                    info["ram_gb"] = round(ram_kb / (1024 ** 2), 1)
    except Exception:
        pass

    # 获取 GPU 信息
    try:
        if info["platform"] == "Darwin":
            # Apple Silicon 使用统一内存，没有独立 GPU VRAM
            if info["has_apple_silicon"]:
                info["gpu_model"] = f"Apple Silicon (统一内存架构)"
                info["gpu_vram_gb"] = 0  # 统一内存，不单独统计
            else:
                result = subprocess.run(["system_profiler", "SPDisplaysDataType"], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if "Chipset Model" in line or "Chipset" in line:
                            gpu_name = line.split(":")[-1].strip()
                            if gpu_name and gpu_name != "Unified":
                                info["gpu_model"] = gpu_name
                                break
        elif info["platform"] == "Linux":
            result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                if lines:
                    first_gpu = lines[0].split(",")
                    info["gpu_model"] = first_gpu[0].strip() if len(first_gpu) > 0 else "NVIDIA GPU"
                    if len(first_gpu) > 1:
                        info["gpu_vram_gb"] = round(float(first_gpu[1].strip()) / 1024, 1)
        elif info["platform"] == "Windows":
            result = subprocess.run(["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                for line in lines[1:]:
                    parts = [p.strip() for p in line.split("  ") if p.strip()]
                    if parts:
                        info["gpu_model"] = parts[0]
                        if len(parts) > 1 and parts[1].isdigit():
                            info["gpu_vram_gb"] = round(int(parts[1]) / (1024 ** 3), 1)
    except Exception:
        pass

    # 检测 Ollama
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            info["ollama_available"] = True
            models = []
            for line in result.stdout.strip().splitlines()[1:]:  # skip header
                if line.strip():
                    model_name = line.split()[0] if line.split() else ""
                    if model_name:
                        models.append(model_name)
            info["ollama_models"] = models
    except Exception:
        info["ollama_available"] = False

    return info


# ============================================================
# 公开模型数据库 (2026年7月更新)
# 数据来源: HuggingFace Open LLM Leaderboard, Vectara Hallucination Leaderboard, LLMCheck
# 注意: 此数据库会过时，Skill 执行时 Agent 应联网搜索最新数据补充
# ============================================================

MODEL_DATABASE = [
    # --- Tier 1: 8GB RAM 可运行 ---
    {
        "name": "qwen2.5:3b",
        "display_name": "Qwen 2.5 3B",
        "model_type": "text_only",
        "params": "3B",
        "min_ram_gb": 4,
        "recommended_ram_gb": 8,
        "license": "Apache 2.0",
        "context_window": "128K",
        "mmlu": 68.0,
        "humaneval": 67.0,
        "hallucination_rate": 5.8,
        "chinese_support": "excellent",
        "speed_tokens_per_sec": 80,
        "use_cases": ["summarization", "chat", "basic_coding", "knowledge_qa"],
        "strengths": ["中文理解强", "响应速度快", "资源占用低"],
        "weaknesses": ["推理能力有限", "长文本处理能力弱"],
        "recommended_for": "入门测试 / 纯文本笔记总结",
        "ollama_command": "ollama pull qwen2.5:3b",
        "tier": "tier_1",
        "updated": "2026-07",
    },
    {
        "name": "phi4-mini",
        "display_name": "Phi-4 Mini 3.8B",
        "model_type": "text_only",
        "params": "3.8B",
        "min_ram_gb": 3,
        "recommended_ram_gb": 8,
        "license": "MIT",
        "context_window": "128K",
        "mmlu": 68.5,
        "humaneval": 67.8,
        "hallucination_rate": 4.2,
        "chinese_support": "limited",
        "speed_tokens_per_sec": 140,
        "use_cases": ["stem", "reasoning", "edge_devices", "coding"],
        "strengths": ["推理能力强", "MIT 协议", "高速响应"],
        "weaknesses": ["中文支持有限"],
        "recommended_for": "STEM 任务 / 英文场景 / 代码辅助",
        "ollama_command": "ollama pull phi4-mini",
        "tier": "tier_1",
        "updated": "2026-07",
    },
    {
        "name": "gemma3:4b",
        "display_name": "Gemma 3 4B",
        "model_type": "multimodal",
        "params": "4B",
        "min_ram_gb": 3,
        "recommended_ram_gb": 8,
        "license": "Apache 2.0",
        "context_window": "128K",
        "mmlu": 72.0,
        "humaneval": 65.0,
        "hallucination_rate": 4.5,
        "chinese_support": "moderate",
        "speed_tokens_per_sec": 90,
        "use_cases": ["general", "summarization", "vision", "image_analysis"],
        "strengths": ["多模态支持", "开源友好", "支持图片理解"],
        "weaknesses": ["中文支持一般"],
        "recommended_for": "视频总结 / 图片分析 / 多模态入门",
        "ollama_command": "ollama pull gemma3:4b",
        "tier": "tier_1",
        "updated": "2026-07",
    },

    # --- Tier 2: 16GB RAM 可运行 ---
    {
        "name": "qwen3:8b",
        "display_name": "Qwen 3 8B",
        "model_type": "text_only",
        "params": "8B",
        "min_ram_gb": 5,
        "recommended_ram_gb": 16,
        "license": "Apache 2.0",
        "context_window": "128K",
        "mmlu": 73.0,
        "humaneval": 75.0,
        "hallucination_rate": 3.4,
        "chinese_support": "excellent",
        "speed_tokens_per_sec": 65,
        "use_cases": ["summarization", "chat", "knowledge_qa", "business", "agent_conversation"],
        "strengths": ["中文场景最佳", "幻觉率低", "综合能力均衡"],
        "weaknesses": ["推理能力一般"],
        "recommended_for": "中文笔记总结 / Agent 对话 / 知识库问答",
        "ollama_command": "ollama pull qwen3:8b",
        "tier": "tier_2",
        "updated": "2026-07",
    },
    {
        "name": "qwen2.5:7b",
        "display_name": "Qwen 2.5 7B",
        "model_type": "text_only",
        "params": "7B",
        "min_ram_gb": 5,
        "recommended_ram_gb": 16,
        "license": "Apache 2.0",
        "context_window": "128K",
        "mmlu": 74.2,
        "humaneval": 79.9,
        "hallucination_rate": 3.8,
        "chinese_support": "excellent",
        "speed_tokens_per_sec": 70,
        "use_cases": ["summarization", "coding", "chinese_nlp"],
        "strengths": ["代码能力强", "中文优化好"],
        "weaknesses": ["综合能力略逊于 Qwen3"],
        "recommended_for": "编程辅助 / 中文处理",
        "ollama_command": "ollama pull qwen2.5:7b",
        "tier": "tier_2",
        "updated": "2026-07",
    },
    {
        "name": "llama3.1:8b",
        "display_name": "Llama 3.1 8B",
        "model_type": "text_only",
        "params": "8B",
        "min_ram_gb": 6,
        "recommended_ram_gb": 16,
        "license": "Llama 3.1 Community",
        "context_window": "128K",
        "mmlu": 73.0,
        "humaneval": 72.6,
        "hallucination_rate": 4.8,
        "chinese_support": "limited",
        "speed_tokens_per_sec": 60,
        "use_cases": ["general", "privacy", "english", "chat"],
        "strengths": ["生态成熟", "社区支持好", "隐私友好"],
        "weaknesses": ["中文支持有限", "幻觉率较高"],
        "recommended_for": "英文场景 / 隐私敏感应用",
        "ollama_command": "ollama pull llama3.1:8b",
        "tier": "tier_2",
        "updated": "2026-07",
    },
    {
        "name": "deepseek-r1:14b",
        "display_name": "DeepSeek R1 14B",
        "model_type": "text_only",
        "params": "14B",
        "min_ram_gb": 10,
        "recommended_ram_gb": 16,
        "license": "MIT",
        "context_window": "128K",
        "mmlu": 76.0,
        "humaneval": 78.0,
        "hallucination_rate": 3.2,
        "chinese_support": "good",
        "speed_tokens_per_sec": 35,
        "use_cases": ["reasoning", "debugging", "math", "complex_tasks"],
        "strengths": ["推理能力强", "MIT 协议", "调试优秀"],
        "weaknesses": ["响应速度慢", "资源占用较高"],
        "recommended_for": "复杂推理 / 代码调试 / Agent 深度分析",
        "ollama_command": "ollama pull deepseek-r1:14b",
        "tier": "tier_2",
        "updated": "2026-07",
    },
    {
        "name": "qwen3-coder-next",
        "display_name": "Qwen3-Coder-Next (3B active)",
        "model_type": "text_only",
        "params": "80B (3B active MoE)",
        "min_ram_gb": 8,
        "recommended_ram_gb": 16,
        "license": "Apache 2.0",
        "context_window": "128K",
        "mmlu": 72.0,
        "humaneval": 85.0,
        "hallucination_rate": 3.5,
        "chinese_support": "good",
        "speed_tokens_per_sec": 55,
        "use_cases": ["coding_agent", "code_generation", "debugging"],
        "strengths": ["代码能力顶级", "MoE 高效架构", "Apache 协议"],
        "weaknesses": ["通用能力一般", "需 16GB+ 内存"],
        "recommended_for": "编程 Agent / 代码生成",
        "ollama_command": "ollama pull qwen3-coder-next",
        "tier": "tier_2",
        "updated": "2026-07",
    },

    # --- Tier 3: 32GB RAM 可运行 ---
    {
        "name": "qwen3:14b",
        "display_name": "Qwen 3 14B",
        "model_type": "text_only",
        "params": "14B",
        "min_ram_gb": 10,
        "recommended_ram_gb": 32,
        "license": "Apache 2.0",
        "context_window": "128K",
        "mmlu": 79.2,
        "humaneval": 82.0,
        "hallucination_rate": 2.2,
        "chinese_support": "excellent",
        "speed_tokens_per_sec": 45,
        "use_cases": ["summarization", "chat", "knowledge", "business", "complex_tasks", "agent_conversation"],
        "strengths": ["幻觉率极低", "中文顶级", "综合能力强"],
        "weaknesses": ["资源占用较高"],
        "recommended_for": "中文笔记总结 / 知识库核心模型 / Agent 对话",
        "ollama_command": "ollama pull qwen3:14b",
        "tier": "tier_3",
        "updated": "2026-07",
    },
    {
        "name": "llama3.3:70b",
        "display_name": "Llama 3.3 70B",
        "model_type": "text_only",
        "params": "70B",
        "min_ram_gb": 28,
        "recommended_ram_gb": 40,
        "license": "Llama 3.3 Community",
        "context_window": "128K",
        "mmlu": 86.0,
        "humaneval": 88.4,
        "hallucination_rate": 2.5,
        "chinese_support": "moderate",
        "speed_tokens_per_sec": 15,
        "use_cases": ["general", "reasoning", "coding", "complex_tasks"],
        "strengths": ["综合能力顶级", "生态成熟", "多语言支持"],
        "weaknesses": ["资源需求大", "中文支持一般"],
        "recommended_for": "复杂任务 / 多语言场景",
        "ollama_command": "ollama pull llama3.3:70b",
        "tier": "tier_3",
        "updated": "2026-07",
    },
    {
        "name": "qwen3:32b",
        "display_name": "Qwen 3 32B",
        "model_type": "text_only",
        "params": "32B",
        "min_ram_gb": 20,
        "recommended_ram_gb": 32,
        "license": "Apache 2.0",
        "context_window": "128K",
        "mmlu": 83.5,
        "humaneval": 84.0,
        "hallucination_rate": 2.5,
        "chinese_support": "excellent",
        "speed_tokens_per_sec": 25,
        "use_cases": ["summarization", "knowledge", "complex_tasks", "business", "agent_conversation"],
        "strengths": ["中文最佳 32B", "综合能力强", "幻觉率低"],
        "weaknesses": ["响应速度中等"],
        "recommended_for": "中文知识库 / 复杂总结 / Agent 对话核心",
        "ollama_command": "ollama pull qwen3:32b",
        "tier": "tier_3",
        "updated": "2026-07",
    },
    {
        "name": "mistral-small3.1",
        "display_name": "Mistral Small 3.1 24B",
        "model_type": "text_only",
        "params": "24B",
        "min_ram_gb": 16,
        "recommended_ram_gb": 32,
        "license": "Apache 2.0",
        "context_window": "128K",
        "mmlu": 81.2,
        "humaneval": 75.0,
        "hallucination_rate": 3.0,
        "chinese_support": "limited",
        "speed_tokens_per_sec": 30,
        "use_cases": ["commercial", "eu_privacy", "general"],
        "strengths": ["Apache 协议", "欧盟合规", "企业级"],
        "weaknesses": ["中文支持有限"],
        "recommended_for": "商业场景 / 欧盟合规",
        "ollama_command": "ollama pull mistral-small3.1",
        "tier": "tier_3",
        "updated": "2026-07",
    },
    {
        "name": "gemma4:27b",
        "display_name": "Gemma 4 27B",
        "model_type": "multimodal",
        "params": "27B",
        "min_ram_gb": 18,
        "recommended_ram_gb": 32,
        "license": "Gemma Terms",
        "context_window": "1M",
        "mmlu": 82.0,
        "humaneval": 78.0,
        "hallucination_rate": 2.8,
        "chinese_support": "moderate",
        "speed_tokens_per_sec": 28,
        "use_cases": ["general", "long_context", "vision", "image_analysis", "video_summarization"],
        "strengths": ["1M 长上下文", "多模态支持", "Google 出品"],
        "weaknesses": ["中文支持一般"],
        "recommended_for": "视频总结 / 多模态分析 / 长文档处理",
        "ollama_command": "ollama pull gemma4:27b",
        "tier": "tier_3",
        "updated": "2026-07",
    },

    # --- Tier 4: 48GB+ RAM 可运行 ---
    {
        "name": "qwen4-preview:32b",
        "display_name": "Qwen 4 Preview 32B-A3B",
        "model_type": "multimodal",
        "params": "32B (3B active MoE)",
        "min_ram_gb": 24,
        "recommended_ram_gb": 48,
        "license": "Apache 2.0",
        "context_window": "1M",
        "mmlu": 88.0,
        "humaneval": 92.0,
        "hallucination_rate": 1.8,
        "chinese_support": "excellent",
        "speed_tokens_per_sec": 58,
        "use_cases": ["advanced", "reasoning", "coding", "enterprise", "vision", "agent_conversation"],
        "strengths": ["Mac 最强模型", "混合推理模式", "高速响应", "多模态支持"],
        "weaknesses": ["需 24GB+ 内存"],
        "recommended_for": "高端 Mac / 视频总结+Agent 对话全能",
        "ollama_command": "ollama pull qwen4-preview:32b",
        "tier": "tier_4",
        "updated": "2026-07",
    },
    {
        "name": "llama4:scout",
        "display_name": "Llama 4 Scout (109B active)",
        "model_type": "multimodal",
        "params": "109B (17B active MoE)",
        "min_ram_gb": 32,
        "recommended_ram_gb": 64,
        "license": "Llama 4 Community",
        "context_window": "10M",
        "mmlu": 87.0,
        "humaneval": 86.0,
        "hallucination_rate": 2.0,
        "chinese_support": "moderate",
        "speed_tokens_per_sec": 20,
        "use_cases": ["long_context", "multimodal", "enterprise", "vision"],
        "strengths": ["10M 超长上下文", "多模态支持", "MoE 架构"],
        "weaknesses": ["资源需求大", "响应速度慢"],
        "recommended_for": "超长文档 / 企业级多模态应用",
        "ollama_command": "ollama pull llama4:scout",
        "tier": "tier_4",
        "updated": "2026-07",
    },
    {
        "name": "mistral-medium4",
        "display_name": "Mistral Medium 4 41B",
        "model_type": "text_only",
        "params": "41B (13B active MoE)",
        "min_ram_gb": 24,
        "recommended_ram_gb": 48,
        "license": "Apache 2.0",
        "context_window": "128K",
        "mmlu": 84.0,
        "humaneval": 82.0,
        "hallucination_rate": 2.3,
        "chinese_support": "moderate",
        "speed_tokens_per_sec": 48,
        "use_cases": ["commercial", "coding", "tool_use"],
        "strengths": ["Apache 协议", "工具调用强", "速度快"],
        "weaknesses": ["中文支持一般"],
        "recommended_for": "商业编码场景",
        "ollama_command": "ollama pull mistral-medium4",
        "tier": "tier_4",
        "updated": "2026-07",
    },
]


# ============================================================
# 公开基准测试集信息
# ============================================================

BENCHMARK_DATASETS = [
    {
        "name": "LCSTS",
        "full_name": "Large-scale Chinese Short Text Summary",
        "description": "大规模中文短文本摘要数据集，用于评估中文摘要质量",
        "size": "200万+ 条",
        "language": "Chinese",
        "task": "summarization",
        "metric": "ROUGE-1/ROUGE-L",
        "location": "tests/workflow/public_benchmarks/lcsts_dataset.json",
        "weight_in_notemeld": 0.15,
    },
    {
        "name": "HalluQA",
        "full_name": "Hallucination Question Answering",
        "description": "中文幻觉检测基准，评估模型回答中的幻觉率",
        "size": "2万+ 条",
        "language": "Chinese",
        "task": "hallucination_detection",
        "metric": "Hallucination Rate",
        "location": "tests/workflow/public_benchmarks/halluqa_dataset.json",
        "weight_in_notemeld": 0.10,
    },
    {
        "name": "Factual Benchmark",
        "full_name": "NoteMeld Factual Consistency Benchmark",
        "description": "总结任务幻觉专项测试，基于 Vectara HHEM 方法论",
        "size": "自定义",
        "language": "Chinese",
        "task": "hallucination_detection",
        "metric": "Faithfulness Rate",
        "location": "tests/workflow/hallucination/factual_benchmark.json",
        "weight_in_notemeld": 0.20,
    },
    {
        "name": "MMLU",
        "full_name": "Massive Multitask Language Understanding",
        "description": "57 学科多任务理解测试，衡量通用知识和推理能力",
        "size": "15,908 题",
        "language": "English",
        "task": "general_understanding",
        "metric": "Accuracy",
        "reference": "https://arxiv.org/abs/2009.03300",
        "weight_in_notemeld": 0.05,
    },
    {
        "name": "HumanEval",
        "full_name": "HumanEval Programming Benchmark",
        "description": "164 道 Python 编程题，衡量代码生成能力",
        "size": "164 题",
        "language": "English",
        "task": "code_generation",
        "metric": "Pass@1",
        "reference": "https://arxiv.org/abs/2108.07732",
        "weight_in_notemeld": 0.05,
    },
    {
        "name": "Vectara HHEM Leaderboard",
        "full_name": "Hughes Hallucination Evaluation Model",
        "description": "基于 HHEM 模型的幻觉率排行榜，130+ 模型对比",
        "size": "1006 问题",
        "language": "English",
        "task": "hallucination_detection",
        "metric": "Hallucination Rate",
        "reference": "https://huggingface.co/spaces/vectara/leaderboard",
        "weight_in_notemeld": 0.10,
    },
    {
        "name": "TruthfulQA",
        "full_name": "TruthfulQA Benchmark",
        "description": "测试模型是否诚实回答，评估事实一致性",
        "size": "8,126 题",
        "language": "English",
        "task": "truthfulness",
        "metric": "Truthful Rate",
        "reference": "https://arxiv.org/abs/2109.07958",
        "weight_in_notemeld": 0.05,
    },
]


# ============================================================
# 推荐引擎
# ============================================================

@dataclass
class Recommendation:
    model: dict
    score: float
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    can_run: bool = True
    download_command: str = ""
    test_command: str = ""
    est_speed_tok_s: float = 0.0
    inference_method: str = "CPU"
    installed: bool = False


# ============================================================
# 硬性限制规则（与 SKILL.md 规则 1-4 同步）
# ============================================================

def get_device_class(device_info: dict) -> str:
    """
    判断设备类型，对应 SKILL.md 规则 1 的表格

    Returns:
        one of:
        - 'intel_mac_no_gpu'    → 最严格限制
        - 'intel_mac_gpu'
        - 'apple_silicon'
        - 'desktop_nvidia_gpu'
        - 'desktop_no_gpu'
        - 'low_ram'
    """
    platform = device_info.get("platform", "")
    has_apple_silicon = device_info.get("has_apple_silicon", False)
    gpu_vram = device_info.get("gpu_vram_gb", 0)
    ram_gb = device_info.get("ram_gb", 0)

    if ram_gb <= 8:
        return "low_ram"

    if has_apple_silicon:
        return "apple_silicon"

    if platform == "Darwin":  # macOS but not Apple Silicon → Intel
        if gpu_vram <= 2:
            return "intel_mac_no_gpu"
        else:
            return "intel_mac_gpu"

    # Windows / Linux
    if gpu_vram >= 8:
        return "desktop_nvidia_gpu"
    return "desktop_no_gpu"


HARD_LIMITS = {
    #                  max_multimodal  max_text_only
    "intel_mac_no_gpu":   (8_000_000_000,   8_000_000_000),
    "intel_mac_gpu":      (14_000_000_000, 32_000_000_000),
    "apple_silicon":      (32_000_000_000, 72_000_000_000),
    "desktop_nvidia_gpu": (32_000_000_000, 70_000_000_000),
    "desktop_no_gpu":     (7_000_000_000,  14_000_000_000),
    "low_ram":            (4_000_000_000,   4_000_000_000),
}


def _params_to_billions(params_str: str) -> float:
    """把模型参数字符串转成 十亿(B) 单位数，用于上限比较"""
    s = params_str.lower().replace(" ", "")

    # 提取第一个数字（MoE 场景取第一个有效参数）
    import re
    m = re.match(r"([\d\.]+)", s)
    if not m:
        return 0.0
    val = float(m.group(1))

    # 后缀判断
    if "t" in s:
        return val * 1000.0
    if "b" in s or not any(k in s for k in ("m", "k")):
        return val
    if "m" in s:
        return val / 1000.0
    return val


def within_hard_limit(model: dict, device_class: str, model_type: str) -> bool:
    """按 SKILL.md 规则 1，判断模型是否在硬性参数上限之内"""
    limit_b = HARD_LIMITS.get(device_class, (8, 8))
    max_b = limit_b[0] if model_type == "multimodal" else limit_b[1]
    actual_b = _params_to_billions(model.get("params", "1B"))
    # HARD_LIMITS 存的是「十亿」数，把上限 B 数对齐
    return actual_b * 1_000_000_000 <= max_b


def estimate_cpu_speed_tok_s(params_b: float, cpu_cores: int = 6) -> float:
    """
    粗略估算无 GPU 情况下 CPU 推理速度（tok/s）
    基于 Intel 6 核无 GPU 的经验区间，按 CPU 核数线性缩放
    """
    # 基准（Intel 6 核）: 3B~18tps, 7B~6tps, 14B~2tps, 27B~0.8tps
    baseline_core = 6.0
    scale = max(1.0, cpu_cores / baseline_core)
    if params_b <= 3:
        return 25.0 * scale
    elif params_b <= 4.5:
        return 15.0 * scale
    elif params_b <= 8:
        return 6.0 * scale
    elif params_b <= 14:
        return 2.0 * scale
    elif params_b <= 32:
        return 0.8 * scale
    else:
        return 0.3 * scale


def estimate_speed_and_method(model: dict, device_info: dict, device_class: str) -> tuple[float, str]:
    """返回 (tok/s, 推理方式)"""
    params_b = _params_to_billions(model.get("params", "1B"))
    base_speed = model.get("speed_tokens_per_sec", 20)

    if device_class == "apple_silicon":
        # Apple Silicon 基本可达到官方标称速度
        return (base_speed, "Apple ANE + Unified RAM")

    if device_class in ("intel_mac_gpu", "desktop_nvidia_gpu"):
        # 有独立 GPU，速度略低于官方标称
        return (max(8.0, base_speed * 0.8), "GPU")

    # 纯 CPU 推理
    return (estimate_cpu_speed_tok_s(params_b, device_info.get("cpu_cores", 6)), "CPU")


def get_supported_models(tier: str) -> list:
    """获取指定等级的所有模型"""
    return [m for m in MODEL_DATABASE if m["tier"] == tier]


def estimate_available_tiers(ram_gb: float, gpu_vram_gb: float = 0) -> list:
    """根据硬件估计可运行的等级"""
    effective_ram = max(ram_gb, gpu_vram_gb * 2) if gpu_vram_gb > 0 else ram_gb

    tiers = []
    if effective_ram >= 96:
        tiers.extend(["tier_5", "tier_4", "tier_3", "tier_2", "tier_1"])
    elif effective_ram >= 48:
        tiers.extend(["tier_4", "tier_3", "tier_2", "tier_1"])
    elif effective_ram >= 32:
        tiers.extend(["tier_3", "tier_2", "tier_1"])
    elif effective_ram >= 16:
        tiers.extend(["tier_2", "tier_1"])
    elif effective_ram >= 8:
        tiers.extend(["tier_1"])
    else:
        tiers = ["tier_0"]

    return tiers


def score_model(
    model: dict,
    device_info: dict,
    use_case: str = "notemeld",
    device_class: Optional[str] = None,
    est_speed: Optional[float] = None,
) -> dict:
    """
    为模型打分（与 SKILL.md 规则 2 权重调整同步）

    默认权重: hardware 30 + chinese 20 + hallucination 20 + capability 15 + speed 15 = 100
    Intel 无独立 GPU 权重调整: speed 权重翻倍，部分权重从综合能力/硬件中补偿
    """
    scores = {
        "hardware": 0,
        "chinese": 0,
        "hallucination": 0,
        "capability": 0,
        "speed": 0,
        "total": 0,
    }
    reasons = []
    warnings = []

    # 默认权重
    weights = {
        "hardware": 1.0,     # 30 * 1 = 30
        "chinese": 1.0,      # 20 * 1 = 20
        "hallucination": 1.0, # 20 * 1 = 20
        "capability": 1.0,   # 15 * 1 = 15
        "speed": 1.0,        # 15 * 1 = 15
    }

    # 规则 2: Intel Mac 无独立 GPU → 速度权重提升到 ~35%
    if device_class is None:
        device_class = get_device_class(device_info)
    if device_class == "intel_mac_no_gpu":
        weights["speed"] = 2.3       # 15*2.3 ≈ 35
        weights["capability"] = 0.6  # 15*0.6 ≈ 9  (减少综合能力权重，补偿给速度)
        weights["hardware"] = 0.8    # 30*0.8 = 24
    elif device_class == "low_ram":
        weights["speed"] = 2.0
        weights["capability"] = 0.7
    elif device_class in ("desktop_no_gpu",):
        weights["speed"] = 1.8
        weights["capability"] = 0.8

    ram = device_info.get("ram_gb", 0)
    gpu_vram = device_info.get("gpu_vram_gb", 0)
    has_apple_silicon = device_info.get("has_apple_silicon", False)

    effective_ram = max(ram, gpu_vram * 2) if gpu_vram > 0 else ram

    # 1. 硬件匹配度（满分 30）
    min_ram = model["min_ram_gb"]
    rec_ram = model["recommended_ram_gb"]

    if effective_ram >= rec_ram:
        scores["hardware"] = 30
        reasons.append(f"内存充足 ({effective_ram:.0f}GB ≥ 推荐 {rec_ram}GB)")
    elif effective_ram >= min_ram:
        scores["hardware"] = 20
        reasons.append(f"内存可用 ({effective_ram:.0f}GB ≥ 最低 {min_ram}GB)，但建议关闭其他程序")
    elif effective_ram >= min_ram * 0.7:
        scores["hardware"] = 10
        warnings.append(f"内存紧张 ({effective_ram:.0f}GB < 最低 {min_ram}GB)，可能需要使用更小量化")
    else:
        scores["hardware"] = 0
        warnings.append(f"内存不足 ({effective_ram:.0f}GB < 最低 {min_ram}GB)，不推荐运行")

    if has_apple_silicon and model.get("tier") in ["tier_3", "tier_4"]:
        scores["hardware"] = min(30, scores["hardware"] + 5)
        reasons.append("Apple Silicon 统一内存架构优势")

    # 2. 中文支持（满分 20）
    chinese_level = model.get("chinese_support", "limited")
    chinese_scores_map = {
        "excellent": 20,
        "good": 15,
        "moderate": 10,
        "limited": 5,
    }
    scores["chinese"] = chinese_scores_map.get(chinese_level, 5)
    if chinese_level == "excellent":
        reasons.append("中文支持优秀")
    elif chinese_level in ["good", "moderate"]:
        reasons.append(f"中文支持{chinese_level}")
    else:
        warnings.append("中文支持有限，可能影响中文笔记总结质量")

    # 3. 幻觉率（满分 20，越低越好）
    halluc_rate = model.get("hallucination_rate", 10)
    if halluc_rate <= 2.0:
        scores["hallucination"] = 20
        reasons.append(f"幻觉率极低 ({halluc_rate}%)")
    elif halluc_rate <= 3.5:
        scores["hallucination"] = 15
        reasons.append(f"幻觉率低 ({halluc_rate}%)")
    elif halluc_rate <= 5.0:
        scores["hallucination"] = 10
        reasons.append(f"幻觉率中等 ({halluc_rate}%)")
    else:
        scores["hallucination"] = 5
        warnings.append(f"幻觉率较高 ({halluc_rate}%)")

    # 4. 综合能力（MMLU，满分 15）
    mmlu = model.get("mmlu", 50)
    if mmlu >= 85:
        scores["capability"] = 15
    elif mmlu >= 75:
        scores["capability"] = 12
    elif mmlu >= 65:
        scores["capability"] = 8
    else:
        scores["capability"] = 5

    # 5. 速度（满分 15）
    if est_speed is None:
        est_speed = model.get("speed_tokens_per_sec", 20)
    speed = est_speed
    if speed >= 20:
        scores["speed"] = 15
        reasons.append(f"响应速度快 ({speed:.0f} tok/s)")
    elif speed >= 10:
        scores["speed"] = 12
    elif speed >= 5:
        scores["speed"] = 8
        reasons.append(f"响应速度中等 ({speed:.0f} tok/s)")
    elif speed >= 3:
        scores["speed"] = 4
        warnings.append(f"速度偏慢 ({speed:.1f} tok/s，CPU 推理较慢，日常使用可能不舒适)")
    else:
        scores["speed"] = 0
        warnings.append(f"速度极慢 ({speed:.1f} tok/s，仅适合测试不适合日常使用)")

    # 计算总分（带动态权重）
    scores["total"] = (
        scores["hardware"] * weights["hardware"] +
        scores["chinese"] * weights["chinese"] +
        scores["hallucination"] * weights["hallucination"] +
        scores["capability"] * weights["capability"] +
        scores["speed"] * weights["speed"]
    )

    return {
        "scores": scores,
        "reasons": reasons,
        "warnings": warnings,
    }


def recommend_models(
    device_info: dict,
    top_n: int = 5,
    use_case: str = "notemeld",
    model_type: str = "all",
    min_tier: str = "tier_0",
) -> list:
    """
    根据设备信息推荐模型（硬性限制规则先于打分）

    1. 先调用 get_device_class() 判定设备类型，确定参数上限
    2. 用 within_hard_limit() 过滤超上限模型（直接过滤，不进入打分）
    3. 为每个模型估算 CPU/GPU 实际速度，带入打分
    4. 已装模型标记 installed，在同样分数下优先
    """
    ram_gb = device_info.get("ram_gb", 0)
    gpu_vram_gb = device_info.get("gpu_vram_gb", 0)

    # === 规则 1: 确定设备类型 + 硬性参数上限 ===
    device_class = get_device_class(device_info)
    installed_models = set(device_info.get("ollama_models") or [])

    # 获取可用的等级（按内存）
    available_tiers = estimate_available_tiers(ram_gb, gpu_vram_gb)

    # 先按 tier 拉候选，再按硬性参数上限过滤
    candidates = []
    for tier in available_tiers:
        for model in get_supported_models(tier):
            if model["min_ram_gb"] > ram_gb + gpu_vram_gb:
                continue
            if model_type != "all" and model.get("model_type") != model_type:
                continue
            # 硬性上限先筛 —— 超出直接不进候选
            mt = model.get("model_type", "text_only")
            if not within_hard_limit(model, device_class, mt):
                continue
            candidates.append(model)

    # 打分排序
    scored_models = []
    for model in candidates:
        mt = model.get("model_type", "text_only")
        # 计算实际速度（考虑设备是否有 GPU 加速）
        est_speed, inference_method = estimate_speed_and_method(model, device_info, device_class)
        score_result = score_model(
            model, device_info, use_case,
            device_class=device_class,
            est_speed=est_speed,
        )

        # can_run: 内存足够 + 硬性上限内（上面筛过，这里是冗余保险）
        can_run = (
            model["min_ram_gb"] <= ram_gb * 1.5
            and within_hard_limit(model, device_class, mt)
        )

        # 生成测试命令
        if mt == "multimodal":
            test_cmd = (
                f'python3 tests/workflow/evaluate_model.py --model "{model["name"]}" '
                f"--skip-lcsts --skip-halluqa"
            )
        else:
            test_cmd = (
                f'python3 tests/workflow/evaluate_model.py --model "{model["name"]}" '
                f"--skip-lcsts --skip-halluqa"
            )

        installed = model["name"] in installed_models

        rec = Recommendation(
            model=model,
            score=score_result["scores"]["total"],
            reasons=score_result["reasons"],
            warnings=score_result["warnings"],
            can_run=can_run,
            download_command=model["ollama_command"],
            test_command=test_cmd,
            est_speed_tok_s=est_speed,
            inference_method=inference_method,
            installed=installed,
        )
        scored_models.append(rec)

    # 排序：score 高的在前，同分时已装模型优先
    scored_models.sort(key=lambda x: (-x.score, 0 if x.installed else 1))
    return scored_models[:top_n]


def _format_model_entry(rec, rank: int) -> list:
    """格式化单个模型推荐条目（规则 3：必须标注速度+推理方式+已装状态）"""
    m = rec.model
    model_t = m.get("model_type", "text_only")
    type_badge = "🖼️ 多模态" if model_t == "multimodal" else "📝 纯文本"
    installed_badge = " ✅已装" if rec.installed else ""

    lines = []
    lines.append(
        f"\n{'⭐' if rank == 1 else f'  {rank}'}  #{rank} {m['display_name']} "
        f"{type_badge}{installed_badge}"
    )
    lines.append(f"   综合评分: {rec.score:.0f}/100")
    lines.append(f"   参数规模: {m['params']}")
    lines.append(f"   内存需求: {m['min_ram_gb']}GB (建议 {m['recommended_ram_gb']}GB)")
    lines.append(f"   幻觉率: {m['hallucination_rate']}%")
    lines.append(f"   MMLU: {m['mmlu']}%")
    lines.append(f"   中文支持: {m['chinese_support']}")
    lines.append(f"   许可证: {m['license']}")

    # 规则 3: 必须标注推理速度 + 推理方式
    speed_str = f"{rec.est_speed_tok_s:.0f} tok/s" if rec.est_speed_tok_s else f"{m['speed_tokens_per_sec']} tok/s"
    lines.append(f"   ⚡ 预估速度: {speed_str} ({rec.inference_method})")
    if rec.est_speed_tok_s and 0 < rec.est_speed_tok_s < 5:
        lines.append("   ⚠️  速度较慢，日常使用可能不舒适")
    if rec.est_speed_tok_s and 0 < rec.est_speed_tok_s < 2:
        lines.append("   ⚠️⚠️ 速度极慢，仅适合测试不建议日常使用")

    if rec.reasons:
        lines.append(f"   ✅ 优势: {'; '.join(rec.reasons[:3])}")
    if rec.warnings:
        lines.append(f"   ⚠️  注意: {'; '.join(rec.warnings[:2])}")

    lines.append(f"   📥 下载: {rec.download_command}")
    lines.append(f"   🧪 测试: {rec.test_command}")
    return lines


def generate_recommendation_report(
    device_info: dict,
    multimodal_recs: list,
    text_only_recs: list,
) -> str:
    """生成推荐报告（同时输出多模态和纯文本两类推荐，带硬性限制说明）"""
    ram = device_info.get("ram_gb", 0)
    gpu = device_info.get("gpu_model", "未检测到")
    tier = device_info.get("ollama_available", False)
    device_class = get_device_class(device_info)
    max_multi_b, max_text_b = HARD_LIMITS.get(device_class, (8_000_000_000, 8_000_000_000))

    class_names = {
        "intel_mac_no_gpu":    "Intel Mac 无独立 GPU（最严格限制）",
        "intel_mac_gpu":       "Intel Mac 有独立 GPU",
        "apple_silicon":       "Apple Silicon M 系列",
        "desktop_nvidia_gpu":  "Windows/Linux 有 NVIDIA GPU",
        "desktop_no_gpu":      "Windows/Linux 无独立 GPU",
        "low_ram":             "低内存设备（≤8GB）",
    }

    lines = []
    lines.append("=" * 70)
    lines.append("NoteMeld 本地模型推荐报告")
    lines.append("=" * 70)
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"设备内存: {ram} GB")
    lines.append(f"GPU: {gpu}")
    lines.append(f"Ollama: {'已安装' if tier else '未安装'}")
    lines.append(f"设备类型: {class_names.get(device_class, device_class)}")
    lines.append(
        f"硬性参数上限: 多模态 ≤ {max_multi_b/1e9:.0f}B, "
        f"纯文本 ≤ {max_text_b/1e9:.0f}B"
    )
    lines.append("")

    # 设备等级
    effective_ram = max(ram, device_info.get("gpu_vram_gb", 0) * 2)
    if effective_ram >= 96:
        device_tier = "tier_5"
    elif effective_ram >= 48:
        device_tier = "tier_4"
    elif effective_ram >= 32:
        device_tier = "tier_3"
    elif effective_ram >= 16:
        device_tier = "tier_2"
    elif effective_ram >= 8:
        device_tier = "tier_1"
    else:
        device_tier = "tier_0"

    tier_descriptions = {
        "tier_5": "服务器级 (96GB+)",
        "tier_4": "高端桌面 (48GB+)",
        "tier_3": "高端笔记本 (32GB+)",
        "tier_2": "标准笔记本 (16GB+)",
        "tier_1": "入门笔记本 (8GB+)",
        "tier_0": "移动设备 (<8GB)",
    }
    lines.append(f"设备等级: {tier_descriptions.get(device_tier, '未知')}")
    lines.append(f"可运行等级: {', '.join(estimate_available_tiers(ram, device_info.get('gpu_vram_gb', 0)))}")
    lines.append("")

    # NoteMeld 场景说明
    lines.append("-" * 70)
    lines.append("📌 NoteMeld 双场景说明")
    lines.append("-" * 70)
    lines.append("")
    lines.append("场景 A: Workflow 视频总结流水线")
    lines.append("  需要多模态模型 (multimodal) - 能理解视频截图/图片内容")
    lines.append("  关键能力: 图片理解、OCR、场景描述")
    lines.append("")
    lines.append("场景 B: Agent 对话 (知识库问答)")
    lines.append("  纯文本模型 (text_only) 即可 - 处理文本检索和生成")
    lines.append("  关键能力: 长文本理解、幻觉率低、中文支持好")
    lines.append("")

    # 多模态推荐
    lines.append("-" * 70)
    lines.append("📊 场景 A: 多模态模型推荐 (视频总结用)")
    lines.append("-" * 70)
    if multimodal_recs:
        for i, rec in enumerate(multimodal_recs, 1):
            lines.extend(_format_model_entry(rec, i))
    else:
        lines.append("  当前设备无可推荐的多模态模型")

    # 纯文本推荐
    lines.append("")
    lines.append("-" * 70)
    lines.append("📊 场景 B: 纯文本模型推荐 (Agent 对话用)")
    lines.append("-" * 70)
    if text_only_recs:
        for i, rec in enumerate(text_only_recs, 1):
            lines.extend(_format_model_entry(rec, i))
    else:
        lines.append("  当前设备无可推荐的纯文本模型")

    # 基准测试说明
    lines.append("")
    lines.append("-" * 70)
    lines.append("📚 NoteMeld 评测指标说明")
    lines.append("-" * 70)
    lines.append("")
    lines.append("场景 A 多模态模型排名指标:")
    lines.append("  幻觉率 35% | 模板遵循度 25% | 章节召回率 15% | 引用正确率 15% | ROUGE-1 10%")
    lines.append("")
    lines.append("场景 B 纯文本模型排名指标:")
    lines.append("  Recall@10 30% | Recall@5 20% | MRR 25% | 引用准确率(Top-1) 25%")
    lines.append("")
    lines.append("通用硬件指标: 设备匹配度 | 中文支持 | 响应速度")
    lines.append("")

    # 使用指南
    lines.append("-" * 70)
    lines.append("🚀 快速开始")
    lines.append("-" * 70)
    lines.append("")
    lines.append("步骤 1: 安装 Ollama (如未安装)")
    lines.append("   macOS: curl -fsSL https://ollama.com/install.sh | sh")
    lines.append("   Windows: winget install Ollama.Ollama")
    lines.append("")
    lines.append("步骤 2: 下载推荐模型")
    if multimodal_recs:
        lines.append(f"   多模态(视频总结): {multimodal_recs[0].download_command}")
    if text_only_recs:
        lines.append(f"   纯文本(Agent对话): {text_only_recs[0].download_command}")
    lines.append("")
    lines.append("步骤 3: 运行 NoteMeld 评测")
    lines.append("   python3 tests/workflow/evaluate_model.py --model <model-name>")
    lines.append("   python3 tests/agent/evaluate_retrieval.py")
    lines.append("")
    lines.append("步骤 4: 查看报告")
    lines.append("   报告自动输出到 tests/reports/ 目录")
    lines.append("")
    lines.append("=" * 70)
    lines.append("更多信息: https://notemeld.wiki/")
    lines.append("=" * 70)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="NoteMeld 本地模型推荐 Skill（内部脚本，由 SKILL.md 调用）")
    parser.add_argument("--device-json", type=str, default=None, help="设备信息 JSON（可选，不指定则自动检测）")
    parser.add_argument("--top-n", type=int, default=5, help="每类返回前 N 个推荐")
    parser.add_argument("--detect-device", action="store_true", help="仅检测设备信息，不推荐模型")
    parser.add_argument("--list-models", action="store_true", help="列出所有可用模型")
    parser.add_argument("--list-benchmarks", action="store_true", help="列出所有基准测试")
    parser.add_argument("--recommend-only", action="store_true", help="仅推荐，不生成报告")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()

    # 仅检测设备
    if args.detect_device:
        device_info = collect_device_info()
        print(json.dumps(device_info, ensure_ascii=False, indent=2))
        return

    # 列出所有模型
    if args.list_models:
        print("=" * 70)
        print("NoteMeld 支持的本地模型列表 (2026年7月)")
        print("=" * 70)
        current_tier = ""
        for model in MODEL_DATABASE:
            if model["tier"] != current_tier:
                current_tier = model["tier"]
                tier_names = {
                    "tier_1": "\n📱 Tier 1: 8GB RAM (入门级)",
                    "tier_2": "\n💻 Tier 2: 16GB RAM (标准笔记本)",
                    "tier_3": "\n🖥️ Tier 3: 32GB RAM (高端笔记本)",
                    "tier_4": "\n🎯 Tier 4: 48GB+ RAM (专业级)",
                }
                print(tier_names.get(current_tier, f"\n{current_tier}"))
            model_type_label = "🖼️多模态" if model.get("model_type") == "multimodal" else "📝纯文本"
            print(f"  {model['display_name']:30s} | {model_type_label:10s} | {model['params']:15s} | RAM: {model['min_ram_gb']:5.0f}GB | 幻觉: {model['hallucination_rate']:5.1f}% | 中文: {model['chinese_support']}")
        text_only_count = len([m for m in MODEL_DATABASE if m.get("model_type") == "text_only"])
        multimodal_count = len([m for m in MODEL_DATABASE if m.get("model_type") == "multimodal"])
        print(f"\n共 {len(MODEL_DATABASE)} 个模型 (📝 纯文本: {text_only_count} | 🖼️ 多模态: {multimodal_count})")
        return

    # 列出基准测试
    if args.list_benchmarks:
        print("=" * 70)
        print("NoteMeld 使用的公开基准测试集")
        print("=" * 70)
        for ds in BENCHMARK_DATASETS:
            print(f"\n📊 {ds['name']} ({ds['full_name']})")
            print(f"   描述: {ds['description']}")
            print(f"   规模: {ds['size']}")
            print(f"   语言: {ds['language']}")
            print(f"   任务: {ds['task']}")
            print(f"   指标: {ds['metric']}")
            if ds.get("location"):
                print(f"   本地路径: {ds['location']}")
            if ds.get("reference"):
                print(f"   参考: {ds['reference']}")
            print(f"   NoteMeld 权重: {ds['weight_in_notemeld']*100:.0f}%")
        return

    # 获取设备信息
    if args.device_json:
        device_info = json.loads(args.device_json)
    else:
        device_info = collect_device_info()

    # 同时推荐两类模型
    multimodal_recs = recommend_models(device_info, top_n=args.top_n, model_type="multimodal")
    text_only_recs = recommend_models(device_info, top_n=args.top_n, model_type="text_only")

    if args.recommend_only:
        print("📊 多模态模型 (视频总结用):")
        for i, rec in enumerate(multimodal_recs, 1):
            print(f"  #{i} {rec.model['display_name']} (评分: {rec.score:.0f}) → {rec.download_command}")
        print("\n📊 纯文本模型 (Agent 对话用):")
        for i, rec in enumerate(text_only_recs, 1):
            print(f"  #{i} {rec.model['display_name']} (评分: {rec.score:.0f}) → {rec.download_command}")
        return

    # 生成报告
    if args.format == "json":
        report = {
            "timestamp": datetime.now().isoformat(),
            "device_info": device_info,
            "recommendations": {
                "multimodal": [
                    {
                        "rank": i + 1,
                        "model": rec.model["name"],
                        "display_name": rec.model["display_name"],
                        "model_type": "multimodal",
                        "score": rec.score,
                        "download_command": rec.download_command,
                        "test_command": rec.test_command,
                        "reasons": rec.reasons,
                        "warnings": rec.warnings,
                    }
                    for i, rec in enumerate(multimodal_recs)
                ],
                "text_only": [
                    {
                        "rank": i + 1,
                        "model": rec.model["name"],
                        "display_name": rec.model["display_name"],
                        "model_type": "text_only",
                        "score": rec.score,
                        "download_command": rec.download_command,
                        "test_command": rec.test_command,
                        "reasons": rec.reasons,
                        "warnings": rec.warnings,
                    }
                    for i, rec in enumerate(text_only_recs)
                ],
            },
        }
        output = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        output = generate_recommendation_report(device_info, multimodal_recs, text_only_recs)

    # 输出
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"报告已保存到: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
