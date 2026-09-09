#!/usr/bin/env python3
"""
NoteMeld 评测框架 v3.0 — 科学、可被第三方信服的评测体系

核心指标（按权重）：
1. 幻觉率（Factual Hallucination Rate）— 你最关心的 No.1
2. 模板遵循度（Template Adherence）— 你最关心的 No.2
3. 章节召回率（Section Recall）— 解决"3段只出2段"
4. 引用正确率（Citation Precision）— *Content-[mm:ss] / *Screenshot-[mm:ss]
5. ROUGE-1 — 通用总结质量

数据集分层（金字塔结构）：
    L3 回归测试（workflow/regression/，用户真实 Bug 反馈）
    L2 业务场景（workflow/business/business_cases.json，真实素材）
    L2 领域标准（workflow/hallucination/factual_benchmark.json，总结类幻觉）
    L1 公开基准（workflow/public_benchmarks/ — LCSTS + HalluQA）

使用方法：
    # 从项目根目录运行
    python3 tests/workflow/evaluate_model.py --model qwen3:8b
    python3 tests/workflow/evaluate_model.py --model qwen3:8b --skip-lcsts --skip-halluqa
    python3 tests/workflow/evaluate_model.py --model qwen3:8b --only-factual
    python3 tests/workflow/evaluate_model.py --model qwen3:8b --only-regression
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx


# ============================================================
# 通用工具
# ============================================================

def _tokenize(text: str) -> List[str]:
    return re.findall(r"[\u4e00-\u9fff]|[a-zA-Z]+|[0-9]+", (text or "").lower())


def _ngrams(tokens: List[str], n: int) -> List[tuple]:
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 指标 1: ROUGE-N / ROUGE-L
# ============================================================

def rouge_n(candidate: str, reference: str, n: int = 1) -> float:
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)
    if len(ref_tokens) < n or len(cand_tokens) < n:
        return 0.0
    cand_ngrams = _ngrams(cand_tokens, n)
    ref_ngrams = _ngrams(ref_tokens, n)
    if not ref_ngrams or not cand_ngrams:
        return 0.0
    cand_counts = Counter(cand_ngrams)
    ref_counts = Counter(ref_ngrams)
    overlap = sum((cand_counts & ref_counts).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(cand_ngrams)
    recall = overlap / len(ref_ngrams)
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0


def rouge_l(candidate: str, reference: str) -> float:
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)
    m, n = len(cand_tokens), len(ref_tokens)
    if m == 0 or n == 0:
        return 0.0
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if cand_tokens[i - 1] == ref_tokens[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, prev
    lcs_len = prev[n]
    if lcs_len == 0:
        return 0.0
    recall = lcs_len / n
    precision = lcs_len / m
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0


def keyword_coverage(candidate: str, keywords: List[str]) -> float:
    if not keywords:
        return 0.0
    lower = (candidate or "").lower()
    hits = sum(1 for kw in keywords if kw and kw.lower() in lower)
    return hits / len(keywords)


# ============================================================
# 指标 2: 幻觉率 Factual Hallucination Rate
#   - 检查 forbidden_claims 是否出现在输出中
#   - 检查 must_not_hallucinate 是否正确保留
# ============================================================

def compute_hallucination(
    candidate: str,
    forbidden_claims: Optional[List[str]] = None,
    must_not_hallucinate: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    基于 source-grounded 方法（TruthfulQA / Vectara HHEM 思路）：
    hallucinated = forbidden_claims 中任一子串出现在 candidate
    faithfulness = must_not_hallucinate 中全部关键词都出现在 candidate
    """
    if not isinstance(forbidden_claims, list):
        forbidden_claims = []
    if not isinstance(must_not_hallucinate, list):
        must_not_hallucinate = []
    forbidden_claims = forbidden_claims or []
    must_not_hallucinate = must_not_hallucinate or []
    text = candidate or ""

    hit_forbidden = [c for c in forbidden_claims if c and c in text]
    missing_required = [c for c in must_not_hallucinate if c and c not in text]

    is_hallucinated = bool(hit_forbidden) or bool(missing_required)
    hallucination_rate = 0.0
    if forbidden_claims:
        hallucination_rate = len(hit_forbidden) / len(forbidden_claims)

    return {
        "is_hallucinated": is_hallucinated,
        "hit_forbidden": hit_forbidden,
        "missing_required": missing_required,
        "hallucination_rate": round(hallucination_rate, 4),
        "faithful": not is_hallucinated,
    }


# ============================================================
# 指标 3: 模板遵循度 Template Adherence
#   - must_include 段落全部出现
#   - must_not_hallucinate 关键词出现
#   - forbidden 禁止项未出现
# ============================================================

_SCREENSHOT_FILE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_SCREENSHOT_TIME_RE = re.compile(r"\*Screenshot-[[\[](\d{1,2}:\d{2})[\]\]]")


def _screenshot_coverage(candidate: str, required_slots: Optional[List[str]]) -> Dict[str, Any]:
    """
    检查要求的截图时间段是否在输出中以 *Screenshot-[mm:ss] 锚点形式出现，
    或至少出现任何截图标记（markdown 图片）。
    """
    required_slots = required_slots or []
    text = candidate or ""
    found_time_slots = list(set(_SCREENSHOT_TIME_RE.findall(text)))
    has_any_image = bool(_SCREENSHOT_FILE_RE.search(text))

    matched = 0
    for slot in required_slots:
        if not slot:
            continue
        slot_sec = _parse_time_to_seconds(slot)
        for ft in found_time_slots:
            if abs(_parse_time_to_seconds(ft) - slot_sec) <= 10:
                matched += 1
                break
        else:
            if has_any_image:
                matched += 1

    coverage = matched / len(required_slots) if required_slots else 1.0
    return {
        "required_slots": required_slots,
        "found_time_slots": found_time_slots,
        "has_any_image": has_any_image,
        "matched": matched,
        "coverage": round(coverage, 4),
    }


def compute_template_adherence(
    candidate: str,
    must_include: Optional[List[str]] = None,
    forbidden: Optional[List[str]] = None,
    required_screenshot_slots: Optional[List[str]] = None,
) -> Dict[str, Any]:
    must_include = must_include or []
    forbidden = forbidden or []
    required_screenshot_slots = required_screenshot_slots or []
    text = candidate or ""

    found_must = [s for s in must_include if s and s in text]
    missing_must = [s for s in must_include if s and s not in text]
    hit_forbidden = [s for s in forbidden if s and s in text]

    must_coverage = len(found_must) / len(must_include) if must_include else 1.0
    forbidden_violation = len(hit_forbidden) / len(forbidden) if forbidden else 0.0
    screenshot_stats = _screenshot_coverage(text, required_screenshot_slots)
    screenshot_cov = screenshot_stats["coverage"]

    # 综合三者，任何一项为 0 都按 0 处理（硬约束）
    overall = must_coverage * (1 - forbidden_violation) * screenshot_cov

    return {
        "must_sections_found": found_must,
        "must_sections_missing": missing_must,
        "forbidden_hit": hit_forbidden,
        "must_coverage": round(must_coverage, 4),
        "forbidden_violation": round(forbidden_violation, 4),
        "screenshot_coverage": screenshot_stats,
        "screenshot_cov": round(screenshot_cov, 4),
        "adherence": round(overall, 4),
    }


# ============================================================
# 指标 4: 章节召回率 Section Recall
#   - 期望出现的段落标题是否全部出现
# ============================================================

def compute_section_recall(
    candidate: str,
    required_sections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    required_sections = required_sections or []
    text = candidate or ""

    found = [s for s in required_sections if s and s in text]
    missing = [s for s in required_sections if s and s not in text]
    recall = len(found) / len(required_sections) if required_sections else 1.0

    return {
        "sections_found": found,
        "sections_missing": missing,
        "recall": round(recall, 4),
    }


# ============================================================
# 指标 5: 引用正确率 Citation Precision
#   - *Content-[mm:ss] 与 expected 时间列表的匹配
#   - *Screenshot-[mm:ss] 与 expected 截图时间列表的匹配
# ============================================================

_CONTENT_RE = re.compile(r"\*Content-[[\[](\d{1,2}:\d{2})[\]\]]")
_SCREENSHOT_RE = re.compile(r"\*Screenshot-[[\[](\d{1,2}:\d{2})[\]\]]")


def _parse_time_to_seconds(t: str) -> int:
    try:
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0


def compute_citation_precision(
    candidate: str,
    expected_content_times: Optional[List[str]] = None,
    expected_screenshot_times: Optional[List[str]] = None,
    tolerance_seconds: int = 10,
) -> Dict[str, Any]:
    """
    允许 tolerance_seconds 的时间偏差。
    """
    expected_content_times = expected_content_times or []
    expected_screenshot_times = expected_screenshot_times or []
    text = candidate or ""

    found_content = list(set(_CONTENT_RE.findall(text)))
    found_screenshot = list(set(_SCREENSHOT_RE.findall(text)))

    def _match(actual_times: List[str], expected_times: List[str]) -> Dict[str, Any]:
        if not expected_times:
            return {"precision": 1.0, "recall": 1.0, "matched": 0, "total_expected": 0}
        matched = 0
        for exp in expected_times:
            exp_sec = _parse_time_to_seconds(exp)
            for act in actual_times:
                act_sec = _parse_time_to_seconds(act)
                if abs(act_sec - exp_sec) <= tolerance_seconds:
                    matched += 1
                    break
        precision = matched / len(actual_times) if actual_times else 1.0
        recall = matched / len(expected_times)
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "matched": matched,
            "total_expected": len(expected_times),
            "found": actual_times,
        }

    content_stats = _match(found_content, expected_content_times)
    screenshot_stats = _match(found_screenshot, expected_screenshot_times)

    # 综合引用正确率
    precisions = [
        content_stats["precision"] if expected_content_times else 1.0,
        screenshot_stats["precision"] if expected_screenshot_times else 1.0,
    ]
    overall = sum(precisions) / len(precisions)

    return {
        "content": content_stats,
        "screenshot": screenshot_stats,
        "overall_precision": round(overall, 4),
    }


# ============================================================
# Ollama / 云端通用客户端
# ============================================================

class OllamaClient:
    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434/v1", api_key: str = ""):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._is_cloud = bool(api_key) and "127.0.0.1" not in base_url and "localhost" not in base_url
        transport = httpx.HTTPTransport(http2=False) if not self._is_cloud else None
        self.client = httpx.Client(transport=transport, timeout=300)

    def chat(
        self,
        messages: List[Dict],
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        start = time.time()
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = self.client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers=headers,
            )
            elapsed = time.time() - start
            if resp.status_code != 200:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}", "elapsed": elapsed}
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            if not content and "reasoning" in msg:
                content = msg["reasoning"].strip()
            usage = data.get("usage", {})
            return {
                "success": True,
                "content": content,
                "elapsed": elapsed,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "elapsed": time.time() - start}


# ============================================================
# 任务 1: LCSTS（通用中文摘要基准）
# ============================================================

def run_lcsts(client: OllamaClient, cases: List[Dict], limit: int = 30) -> Dict[str, Any]:
    cases = cases[:limit]
    results = []
    for i, tc in enumerate(cases):
        print(f"  [LCSTS {i + 1}/{len(cases)}] {tc.get('id', f'c{i}')}...", end="", flush=True)
        messages = [
            {"role": "system", "content": "你是中文摘要助手。请对以下文本进行简洁中文摘要，保留关键信息，不要添加原文中没有的内容。摘要不超过 30 字。"},
            {"role": "user", "content": f"请摘要以下文本：\n\n{tc['input']}"}
        ]
        resp = client.chat(messages, max_tokens=100, temperature=0.3)
        if not resp["success"]:
            print(f" 失败: {resp['error'][:40]}")
            results.append({"id": tc.get("id"), "status": "failed", "error": resp["error"]})
            continue
        summary = resp["content"]
        expected = tc.get("expected_summary", "")
        keywords = tc.get("keywords", [])
        r1 = rouge_n(summary, expected, 1)
        rl = rouge_l(summary, expected)
        kw = keyword_coverage(summary, keywords)
        print(f" R1={r1:.3f} RL={rl:.3f} KW={kw:.0%} ({resp['elapsed']:.1f}s)")
        results.append({
            "id": tc.get("id"), "status": "success",
            "metrics": {"rouge_1": r1, "rouge_l": rl, "keyword_coverage": kw, "elapsed": resp["elapsed"]},
        })
    return _summarize("LCSTS", results)


# ============================================================
# 任务 2: HalluQA（通用中文幻觉基准）
# ============================================================

def run_halluqa(client: OllamaClient, cases: List[Dict], limit: int = 30) -> Dict[str, Any]:
    cases = cases[:limit]
    results = []
    for i, tc in enumerate(cases):
        qid = tc.get("question_id", f"hq_{i + 1}")
        print(f"  [HalluQA {i + 1}/{len(cases)}] q{qid}...", end="", flush=True)
        messages = [
            {"role": "system", "content": "请根据你的知识回答。如果不确定请说明，不要编造信息。"},
            {"role": "user", "content": tc.get("question", "")}
        ]
        resp = client.chat(messages, max_tokens=200, temperature=0.1)
        if not resp["success"]:
            print(" 失败")
            results.append({"id": qid, "status": "failed", "error": resp["error"]})
            continue
        answer = resp["content"]
        best = tc.get("best_answer1", "")
        wrong = tc.get("wrong_answers", []) or []
        if not isinstance(wrong, list):
            wrong = []
        for w in wrong:
            if not isinstance(w, str):
                wrong = [str(x) for x in wrong if x]
                break
        halluc = compute_hallucination(answer, forbidden_claims=list(wrong))
        label = "幻觉" if halluc["is_hallucinated"] else "正常"
        print(f" {label} ({resp['elapsed']:.1f}s)")
        results.append({
            "id": qid, "status": "success",
            "metrics": {**halluc, "elapsed": resp["elapsed"]},
        })
    return _summarize("HalluQA", results, hallucination_key="is_hallucinated")


# ============================================================
# 任务 3: Factual Benchmark（总结任务幻觉基准 — 新增）
# ============================================================

def run_factual_benchmark(client: OllamaClient, cases: List[Dict]) -> Dict[str, Any]:
    """
    每个 case 给模型 source_text，让它生成总结，然后检查是否违反 forbidden_claims。
    """
    results = []
    for i, tc in enumerate(cases):
        cid = tc.get("id", f"fb_{i + 1}")
        print(f"  [Factual {i + 1}/{len(cases)}] {cid}...", end="", flush=True)

        source = tc.get("source_text", "")
        # 给模型一个总结指令
        prompt_text = f"请基于以下原文生成一段简洁的中文总结，只允许使用原文中的事实，不要添加任何原文没有的信息。\n\n原文：\n{source}\n\n总结："

        messages = [
            {"role": "system", "content": "你是严格基于原文的摘要助手。不得编造原文没有的事实。"},
            {"role": "user", "content": prompt_text}
        ]
        resp = client.chat(messages, max_tokens=400, temperature=0.1)
        if not resp["success"]:
            print(" 失败")
            results.append({"id": cid, "status": "failed", "error": resp["error"]})
            continue

        summary = resp["content"]
        expected_faithful = tc.get("ground_truth", "faithful")
        halluc = compute_hallucination(
            summary,
            forbidden_claims=tc.get("hallucinated_claims", []) or [],
            must_not_hallucinate=tc.get("must_not_hallucinate", []) or [],
        )
        # 与 gold label 对比
        pred_faithful = not halluc["is_hallucinated"]
        expected_faithful_flag = expected_faithful == "faithful"
        correct = pred_faithful == expected_faithful_flag

        print(f" {'✓' if correct else '✗'} pred={'faithful' if pred_faithful else 'halluc'} ({resp['elapsed']:.1f}s)")
        results.append({
            "id": cid, "status": "success",
            "metrics": {
                **halluc,
                "expected_label": expected_faithful,
                "predicted_label": "faithful" if pred_faithful else "hallucinated",
                "correct": correct,
                "elapsed": resp["elapsed"],
            },
        })
    return _summarize(
        "FactualBenchmark",
        results,
        accuracy_keys=["correct"],
        hallucination_key="is_hallucinated",
    )


# ============================================================
# 任务 4: 业务场景（business_cases.json — 核心）
# ============================================================

_BUSINESS_SYSTEM_PROMPT = (
    "你是 NoteMeld 的专业笔记助手。"
    "请严格按照用户指定的模板输出，不得编造原文中没有的信息。"
    "保留所有关键数据、时间节点和事实。"
)


def _build_business_messages(tc: Dict) -> List[Dict]:
    input_data = tc.get("input", {})
    text = input_data.get("text_excerpt", "") or input_data.get("text", "") or ""
    expected = tc.get("expected", {})
    template_id = expected.get("template_id", "")

    # 构造模板说明
    must_include = expected.get("must_include", []) or []
    must_sections = expected.get("required_sections", []) or must_include
    forbidden = expected.get("forbidden_claims", []) or []
    required_citations = expected.get("required_citations", []) or []
    required_screenshots = expected.get("required_screenshot_slots", []) or []

    template_hint = ""
    if must_sections:
        template_hint += f"\n必须包含的段落标题：{', '.join(must_sections)}"
    if forbidden:
        template_hint += f"\n严禁出现的内容：{', '.join(forbidden)}"
    if required_citations:
        template_hint += f"\n必须添加的时间戳引用：{', '.join(required_citations)}"
    if required_screenshots:
        template_hint += f"\n必须添加的截图引用：{', '.join(required_screenshots)}"
    if template_id:
        template_hint += f"\n笔记模板：{template_id}"

    user_msg = (
        f"请基于以下原文生成符合要求的笔记。\n"
        f"原文：\n{text}\n"
        f"{template_hint}\n"
        f"请直接输出笔记内容，不要输出解释。"
    )

    return [
        {"role": "system", "content": _BUSINESS_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]


def run_business(client: OllamaClient, cases: List[Dict]) -> Dict[str, Any]:
    """
    运行 business_cases.json，核心计算 5 个指标：
    - template_adherence
    - hallucination_rate
    - section_recall
    - citation_precision
    - rouge_1
    """
    results = []
    for i, tc in enumerate(cases):
        cid = tc.get("id", f"biz_{i + 1}")
        category = tc.get("category", "")
        print(f"  [业务 {i + 1}/{len(cases)}] {cid} ({category})...", end="", flush=True)

        messages = _build_business_messages(tc)
        # 基于类型调整 max_tokens
        category = category or ""
        max_tokens = 600
        if "template" in category or "section" in category:
            max_tokens = 800
        elif "hallucination" in category:
            max_tokens = 400
        elif "citation" in category:
            max_tokens = 500
        elif "edge_case" in category:
            max_tokens = 200

        resp = client.chat(messages, max_tokens=max_tokens, temperature=0.1)
        if not resp["success"]:
            print(f"  失败: {resp['error'][:40]}")
            results.append({"id": cid, "category": category, "status": "failed", "error": resp["error"]})
            continue

        candidate = resp["content"]
        expected = tc.get("expected", {})

        # 计算 5 大指标
        halluc = compute_hallucination(
            candidate,
            forbidden_claims=expected.get("forbidden_claims", []) or [],
            must_not_hallucinate=expected.get("must_not_hallucinate", []) or [],
        )
        template = compute_template_adherence(
            candidate,
            must_include=expected.get("must_include", []) or [],
            forbidden=expected.get("forbidden_claims", []) or [],
            required_screenshot_slots=expected.get("required_screenshot_slots", []) or [],
        )
        section = compute_section_recall(
            candidate,
            required_sections=expected.get("required_sections", []) or expected.get("must_include", []) or [],
        )
        citation = compute_citation_precision(
            candidate,
            expected_content_times=expected.get("required_citations", []) or [],
            expected_screenshot_times=expected.get("required_screenshot_slots", []) or [],
        )
        ref_summary = expected.get("summary", "")
        r1 = rouge_n(candidate, ref_summary, 1) if ref_summary else None

        keywords = expected.get("keywords", []) or []
        kw_cov = keyword_coverage(candidate, keywords) if keywords else None

        # 打印核心指标
        parts = []
        if halluc["is_hallucinated"]:
            parts.append(f"幻觉={halluc['hallucination_rate']:.0%}")
        if template["adherence"] < 1.0:
            parts.append(f"模板={template['adherence']:.0%}")
        if section["recall"] < 1.0:
            parts.append(f"章节={section['recall']:.0%}")
        if citation["overall_precision"] < 1.0:
            parts.append(f"引用={citation['overall_precision']:.0%}")
        if not parts:
            parts.append("OK")
        print(f" {'|'.join(parts)} ({resp['elapsed']:.1f}s)")

        metrics = {
            "hallucination": halluc,
            "template_adherence": template,
            "section_recall": section,
            "citation_precision": citation,
            "elapsed": resp["elapsed"],
        }
        if r1 is not None:
            metrics["rouge_1"] = r1
        if kw_cov is not None:
            metrics["keyword_coverage"] = kw_cov

        results.append({
            "id": cid,
            "category": category,
            "status": "success",
            "output_excerpt": candidate[:200],
            "metrics": metrics,
        })

    # 按 category 分层汇总
    by_category: Dict[str, List[Dict]] = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r)

    category_summary = {}
    for cat, items in by_category.items():
        succ = [i for i in items if i["status"] == "success"]
        if not succ:
            category_summary[cat] = {"total": len(items), "success": 0}
            continue
        agg = {}
        for key, extractor in [
            ("hallucination_rate", lambda m: m["hallucination"]["hallucination_rate"]),
            ("template_adherence", lambda m: m["template_adherence"]["adherence"]),
            ("section_recall", lambda m: m["section_recall"]["recall"]),
            ("citation_precision", lambda m: m["citation_precision"]["overall_precision"]),
            ("rouge_1", lambda m: m.get("rouge_1", 0)),
            ("keyword_coverage", lambda m: m.get("keyword_coverage", 0)),
            ("elapsed", lambda m: m["elapsed"]),
        ]:
            vals = [extractor(i["metrics"]) for i in succ if extractor(i["metrics"]) is not None]
            if vals:
                agg[key] = round(sum(vals) / len(vals), 4)
        category_summary[cat] = {
            "total": len(items),
            "success": len(succ),
            "avg": agg,
        }

    # 全局汇总
    succ_all = [i for i in results if i["status"] == "success"]
    overall = {}
    for key, extractor in [
        ("hallucination_rate", lambda m: m["hallucination"]["hallucination_rate"]),
        ("template_adherence", lambda m: m["template_adherence"]["adherence"]),
        ("section_recall", lambda m: m["section_recall"]["recall"]),
        ("citation_precision", lambda m: m["citation_precision"]["overall_precision"]),
        ("elapsed", lambda m: m["elapsed"]),
    ]:
        vals = [extractor(i["metrics"]) for i in succ_all]
        if vals:
            overall[key] = round(sum(vals) / len(vals), 4)

    return {
        "dataset": "NoteMeld Business",
        "total": len(results),
        "success": len(succ_all),
        "failed": len(results) - len(succ_all),
        "overall": overall,
        "by_category": category_summary,
        "details": results,
    }


# ============================================================
# 任务 5: 回归测试（线上问题 → 沉淀 → 永不复发）
#   每条 case 必须全绿，否则视为修复失败
# ============================================================

def run_regression(client: OllamaClient, cases: List[Dict]) -> Dict[str, Any]:
    """
    对 regression_cases.json 中的每条真实 Bug 进行检测。
    失败条件（任一命中即视为回归失败）：
      1) forbidden_claims 任一命中 → is_hallucinated
      2) required_sections 缺失 → section_recall < 1
      3) required_screenshot_slots 未覆盖 → screenshot_cov < 1
      4) required_citations 未覆盖 → citation recall < 1
      5) keywords_required 未完全覆盖
    """
    results = []
    for i, tc in enumerate(cases):
        cid = tc.get("id", f"reg_{i + 1}")
        bug_type = tc.get("bug_type", "")
        source_ticket = tc.get("source_ticket", "")
        print(f"  [回归 {i + 1}/{len(cases)}] {cid} ({bug_type})...", end="", flush=True)

        input_data = tc.get("input", {})
        text = input_data.get("text", "")
        expected = tc.get("expected", {})

        must_sections = expected.get("required_sections", []) or []
        forbidden_claims = expected.get("forbidden_claims", []) or []
        required_citations = expected.get("required_citations", []) or []
        required_screenshots = expected.get("required_screenshot_slots", []) or []
        keywords_required = expected.get("keywords_required", []) or []

        template_hint = ""
        if must_sections:
            template_hint += f"\n必须包含的段落标题：{', '.join(must_sections)}"
        if forbidden_claims:
            template_hint += f"\n严禁出现的内容：{', '.join(forbidden_claims)}"
        if required_citations:
            template_hint += f"\n必须添加的时间戳引用：{', '.join(required_citations)}"
        if required_screenshots:
            template_hint += f"\n必须添加截图锚点的时间段：{', '.join(required_screenshots)}"

        messages = [
            {"role": "system", "content": _BUSINESS_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"请基于以下原文生成符合要求的笔记。\n"
                f"原文：\n{text}\n"
                f"{template_hint}\n"
                f"请直接输出笔记内容，不要输出解释。"
            )},
        ]

        resp = client.chat(messages, max_tokens=800, temperature=0.1)
        if not resp["success"]:
            print(f" 失败: {resp['error'][:40]}")
            results.append({
                "id": cid, "bug_type": bug_type, "source_ticket": source_ticket,
                "status": "failed", "error": resp["error"],
                "pass": False,
            })
            continue

        candidate = resp["content"]

        halluc = compute_hallucination(candidate, forbidden_claims=forbidden_claims)
        section = compute_section_recall(candidate, required_sections=must_sections)
        template = compute_template_adherence(
            candidate,
            must_include=must_sections,
            forbidden=forbidden_claims,
            required_screenshot_slots=required_screenshots,
        )
        citation = compute_citation_precision(
            candidate,
            expected_content_times=required_citations,
            expected_screenshot_times=required_screenshots,
        )
        kw_cov = keyword_coverage(candidate, keywords_required) if keywords_required else 1.0

        # 任何一项不满足视为回归失败
        fails = []
        if halluc["is_hallucinated"]:
            fails.append(f"hallucination(hit={halluc['hit_forbidden']})")
        if section["recall"] < 1.0:
            fails.append(f"missing_sections={section['sections_missing']}")
        if template["screenshot_cov"] < 1.0 and required_screenshots:
            fails.append(f"screenshot_missing(cov={template['screenshot_cov']})")
        if citation["screenshot"].get("recall", 1.0) < 1.0 and required_screenshots:
            fails.append(f"citation_screenshot_recall={citation['screenshot'].get('recall', 0)}")
        if citation["content"].get("recall", 1.0) < 1.0 and required_citations:
            fails.append(f"citation_content_recall={citation['content'].get('recall', 0)}")
        if kw_cov < 1.0 and keywords_required:
            fails.append(f"keywords_missing(cov={kw_cov})")

        passed = len(fails) == 0
        if passed:
            print(f" ✓ PASS ({resp['elapsed']:.1f}s)")
        else:
            print(f" ✗ FAIL: {'; '.join(fails)} ({resp['elapsed']:.1f}s)")

        results.append({
            "id": cid,
            "bug_type": bug_type,
            "source_ticket": source_ticket,
            "status": "success",
            "pass": passed,
            "fails": fails,
            "metrics": {
                "hallucination": halluc,
                "section_recall": section,
                "template_adherence": template,
                "citation_precision": citation,
                "keyword_coverage": kw_cov,
                "elapsed": resp["elapsed"],
            },
        })

        if not passed:
            print(f"    ❌ 回归失败，该用例对应工单：{source_ticket}")

    passed_count = sum(1 for r in results if r.get("pass"))
    total = len(results)
    return {
        "dataset": "NoteMeld Regression",
        "total": total,
        "success": len([r for r in results if r["status"] == "success"]),
        "failed": total - len([r for r in results if r["status"] == "success"]),
        "passed": passed_count,
        "failed_cases": [
            {"id": r["id"], "bug_type": r.get("bug_type"), "source_ticket": r.get("source_ticket"), "fails": r.get("fails", [])}
            for r in results if not r.get("pass", False)
        ],
        "pass_rate": round(passed_count / total, 4) if total else 0.0,
        "details": results,
    }


# ============================================================
# 通用汇总
# ============================================================

def _summarize(
    name: str,
    results: List[Dict],
    hallucination_key: Optional[str] = None,
    accuracy_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    succ = [r for r in results if r["status"] == "success"]
    summary: Dict[str, Any] = {
        "dataset": name,
        "total": len(results),
        "success": len(succ),
        "failed": len(results) - len(succ),
    }

    if name == "LCSTS" and succ:
        summary["avg_rouge_1"] = round(sum(r["metrics"]["rouge_1"] for r in succ) / len(succ), 4)
        summary["avg_rouge_l"] = round(sum(r["metrics"]["rouge_l"] for r in succ) / len(succ), 4)
        summary["avg_keyword_coverage"] = round(sum(r["metrics"]["keyword_coverage"] for r in succ) / len(succ), 4)
        summary["avg_elapsed"] = round(sum(r["metrics"]["elapsed"] for r in succ) / len(succ), 2)
    elif hallucination_key and succ:
        hallucinated = [r for r in succ if r["metrics"].get(hallucination_key)]
        summary["hallucinated"] = len(hallucinated)
        summary["hallucination_rate"] = round(len(hallucinated) / len(succ), 4)
        summary["non_hallucination_rate"] = round(1 - summary["hallucination_rate"], 4)
    elif accuracy_keys and succ:
        for k in accuracy_keys:
            vals = [r["metrics"].get(k) for r in succ if isinstance(r["metrics"].get(k), (int, float))]
            if vals:
                summary[f"avg_{k}"] = round(sum(vals) / len(vals), 4)

    return summary


# ============================================================
# 报告生成
# ============================================================

def _human_label(rate: float) -> str:
    if rate >= 0.95:
        return "🟢 优秀"
    if rate >= 0.85:
        return "🟡 良好"
    if rate >= 0.70:
        return "🟠 一般"
    return "🔴 待改进"


def generate_report(all_results: Dict, model: str, output_dir: str) -> tuple:
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(output_dir, f"eval_{model.replace(':', '_')}_{ts}.json")
    md_path = os.path.join(output_dir, f"eval_{model.replace(':', '_')}_{ts}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    r = all_results.get("results", {})
    biz = r.get("business", {})
    overall = biz.get("overall", {})

    # 一级指标评分
    h_rate = overall.get("hallucination_rate", 0)
    t_adhere = overall.get("template_adherence", 0)
    s_recall = overall.get("section_recall", 0)
    c_prec = overall.get("citation_precision", 0)

    # 综合评分（加权）
    weighted_score = (
        (1 - h_rate) * 0.35 +
        t_adhere * 0.25 +
        s_recall * 0.15 +
        c_prec * 0.15
    )
    grade = _human_label(weighted_score)

    md = f"""# NoteMeld 模型评测报告 v3.1

## 评测元信息

- **模型**: {model}
- **时间**: {all_results['timestamp']}
- **硬件**: {all_results['hardware']}
- **评测套件**: LCSTS + HalluQA + FactualBenchmark + 业务场景 + 回归测试（线上真实 Bug 沉淀）

## 综合评分（加权）

**综合得分**: {weighted_score:.2%} {grade}

| 一级指标 | 得分 | 权重 | 评价 |
|---|---|---|---|
| ① 幻觉率（越低越好） | {h_rate:.2%} | 0.35 | {_human_label(1 - h_rate)} |
| ② 模板遵循度 | {t_adhere:.2%} | 0.25 | {_human_label(t_adhere)} |
| ③ 章节召回率 | {s_recall:.2%} | 0.15 | {_human_label(s_recall)} |
| ④ 引用正确率 | {c_prec:.2%} | 0.15 | {_human_label(c_prec)} |
| ⑤ ROUGE-1（通用质量） | {overall.get('rouge_1', 0):.2%} | 0.10 | {_human_label(overall.get('rouge_1', 0))} |

> **门槛**：生产环境 ≤ 5% 幻觉率，Beta ≤ 10%。模板遵循度 ≥ 95%。章节召回率 ≥ 90%。

## 数据集总览

| 数据集 | 测试数 | 成功 | 核心指标 |
|---|---|---|---|
"""
    for key in ["lcsts", "halluqa", "factual", "business", "regression"]:
        if key not in r:
            continue
        info = r[key]
        if key == "lcsts":
            core = f"ROUGE-1={info.get('avg_rouge_1', 0):.4f}, ROUGE-L={info.get('avg_rouge_l', 0):.4f}"
        elif key == "halluqa":
            core = f"幻觉率={info.get('hallucination_rate', 0):.2%}"
        elif key == "factual":
            core = f"Factual 准确率={info.get('avg_correct', 0):.2%}"
        elif key == "regression":
            core = f"通过率={info.get('pass_rate', 0):.2%} (通过 {info.get('passed', 0)}/{info.get('total', 0)})"
        else:
            core = (
                f"幻觉率={info.get('overall', {}).get('hallucination_rate', 0):.2%} · "
                f"模板={info.get('overall', {}).get('template_adherence', 0):.2%} · "
                f"章节={info.get('overall', {}).get('section_recall', 0):.2%} · "
                f"引用={info.get('overall', {}).get('citation_precision', 0):.2%}"
            )
        md += f"| {info.get('dataset', key)} | {info.get('total', 0)} | {info.get('success', 0)} | {core} |\n"

    # 业务分层
    if "business" in r:
        biz = r["business"]
        md += "\n## 业务场景分层指标\n\n"
        md += "| 类别 | 总数 | 成功 | 幻觉率 | 模板遵循 | 章节召回 | 引用正确率 |\n"
        md += "|---|---|---|---|---|---|---|\n"
        for cat, info in biz.get("by_category", {}).items():
            avg = info.get("avg", {})
            md += (
                f"| {cat} | {info.get('total', 0)} | {info.get('success', 0)} | "
                f"{avg.get('hallucination_rate', 0):.2%} | "
                f"{avg.get('template_adherence', 0):.2%} | "
                f"{avg.get('section_recall', 0):.2%} | "
                f"{avg.get('citation_precision', 0):.2%} |\n"
            )

    # 失败 case
    if "business" in r:
        bad = [
            d for d in r["business"]["details"]
            if d["status"] == "success"
            and (
                d["metrics"]["hallucination"]["is_hallucinated"]
                or d["metrics"]["template_adherence"]["adherence"] < 0.7
                or d["metrics"]["section_recall"]["recall"] < 0.7
            )
        ]
        if bad:
            md += "\n## 典型失败样例（供回归使用）\n\n"
            for d in bad[:8]:
                m = d["metrics"]
                md += f"- **{d['id']}** ({d.get('category', '')}) "
                if m["hallucination"]["is_hallucinated"]:
                    md += f"· 幻觉命中：{m['hallucination']['hit_forbidden']}"
                if m["template_adherence"]["adherence"] < 0.7:
                    md += f" · 缺失段落：{m['template_adherence']['must_sections_missing']}"
                if m["section_recall"]["recall"] < 0.7:
                    md += f" · 章节缺失：{m['section_recall']['sections_missing']}"
                md += "\n"

    md += "\n## 结论\n\n"
    md += f"- **综合评分**: {weighted_score:.2%} {grade}\n"
    if h_rate <= 0.05:
        md += "- ✅ 幻觉率 ≤ 5%，达到生产标准\n"
    elif h_rate <= 0.10:
        md += "- ⚠️ 幻觉率在 5%-10% 之间，Beta 可用\n"
    else:
        md += "- ❌ 幻觉率 > 10%，不建议上线\n"
    if t_adhere >= 0.95:
        md += "- ✅ 模板遵循度 ≥ 95%\n"
    else:
        md += f"- ⚠️ 模板遵循度仅 {t_adhere:.2%}，存在「3 段只出 2 段」类问题\n"

    md += f"\n报告文件:\n- JSON: {json_path}\n- Markdown: {md_path}\n"

    # 回归专项章节
    if "regression" in r:
        reg = r["regression"]
        md += "\n## 回归测试结果（线上真实 Bug 沉淀）\n\n"
        md += f"- **通过率**: {reg.get('pass_rate', 0):.2%} ({reg.get('passed', 0)}/{reg.get('total', 0)})\n"
        md += f"- **通过数**: {reg.get('passed', 0)}\n"
        md += f"- **失败数**: {reg.get('total', 0) - reg.get('passed', 0)}\n"
        if reg.get("failed_cases"):
            md += "\n### ❌ 失败用例（需修复）\n\n"
            for fc in reg["failed_cases"]:
                md += f"- **{fc['id']}** ({fc.get('bug_type', '')}) — 工单：{fc.get('source_ticket', '')}\n"
                md += f"  - 失败原因：{'; '.join(fc.get('fails', []))}\n"
        md += "\n"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    return json_path, md_path


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="NoteMeld 评测框架 v3.0 — 科学、多指标、分层")
    parser.add_argument("--model", type=str, required=True, help="模型名")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:11434/v1")
    parser.add_argument("--api-key", type=str, default="", help="云端 API Key（不填则使用本地 Ollama）")
    parser.add_argument("--lcsts-limit", type=int, default=30)
    parser.add_argument("--halluqa-limit", type=int, default=30)
    parser.add_argument("--output-dir", type=str, default=None, help="报告输出目录（默认 tests/reports）")
    parser.add_argument("--skip-lcsts", action="store_true")
    parser.add_argument("--skip-halluqa", action="store_true")
    parser.add_argument("--skip-business", action="store_true")
    parser.add_argument("--skip-factual", action="store_true")
    parser.add_argument("--skip-regression", action="store_true")
    parser.add_argument("--only-factual", action="store_true", help="仅跑总结任务幻觉评测")
    parser.add_argument("--only-regression", action="store_true", help="仅跑线上问题回归")
    args = parser.parse_args()

    # 路径定位：脚本位于 tests/workflow/，tests/ 是其父目录，项目根是 tests/ 的父目录
    script_dir = os.path.dirname(os.path.abspath(__file__))  # tests/workflow/
    tests_root = os.path.dirname(script_dir)                 # tests/
    data_dir = os.path.join(script_dir, "public_benchmarks")
    output_dir = args.output_dir or os.path.join(tests_root, "reports")

    lcsts_data = []
    if not args.skip_lcsts and not args.only_factual:
        raw = _load_json(os.path.join(data_dir, "lcsts_dataset.json")) or {}
        lcsts_data = raw.get("test_cases", [])
        print(f"✓ LCSTS: {len(lcsts_data)} 条")

    halluqa_data = []
    if not args.skip_halluqa and not args.only_factual:
        raw = _load_json(os.path.join(data_dir, "halluqa_dataset.json")) or []
        for item in raw:
            halluqa_data.append({
                "question_id": item.get("question_id"),
                "question": item.get("question", ""),
                "best_answer1": item.get("Best Answer1", item.get("best_answer1", "")),
                "wrong_answers": [v for k, v in item.items() if k.startswith("Wrong_Answer") and v],
                "category": item.get("Category", item.get("category", "")),
            })
        print(f"✓ HalluQA: {len(halluqa_data)} 条")

    factual_data = []
    if not args.skip_factual:
        raw = _load_json(os.path.join(script_dir, "hallucination", "factual_benchmark.json")) or {}
        factual_data = raw.get("cases", [])
        print(f"✓ FactualBenchmark: {len(factual_data)} 条")

    business_data = []
    if not args.skip_business and not args.only_factual and not args.only_regression:
        raw = _load_json(os.path.join(script_dir, "business", "business_cases.json")) or {}
        business_data = raw.get("cases", [])
        print(f"✓ Business: {len(business_data)} 条 (categories: {len(set(c['category'] for c in business_data))})")

    regression_data = []
    if not args.skip_regression and not args.only_factual:
        raw = _load_json(os.path.join(script_dir, "regression", "regression_cases.json")) or {}
        regression_data = raw.get("cases", [])
        print(f"✓ Regression: {len(regression_data)} 条 (真实 Bug 沉淀)")

    client = OllamaClient(args.model, args.base_url, args.api_key)
    print("\n--- 连接测试 ---")
    test = client.chat([{"role": "user", "content": "你好"}], max_tokens=10)
    if not test["success"]:
        print(f"✗ 连接失败: {test['error']}")
        sys.exit(1)
    print(f"✓ 连接成功 ({test['elapsed']:.1f}s)")

    results: Dict[str, Any] = {}

    if lcsts_data:
        print(f"\n--- LCSTS ({min(args.lcsts_limit, len(lcsts_data))} 条) ---")
        results["lcsts"] = run_lcsts(client, lcsts_data, args.lcsts_limit)

    if halluqa_data:
        print(f"\n--- HalluQA ({min(args.halluqa_limit, len(halluqa_data))} 条) ---")
        results["halluqa"] = run_halluqa(client, halluqa_data, args.halluqa_limit)

    if factual_data:
        print(f"\n--- Factual Benchmark ({len(factual_data)} 条) ---")
        results["factual"] = run_factual_benchmark(client, factual_data)

    if business_data:
        print(f"\n--- Business ({len(business_data)} 条) ---")
        results["business"] = run_business(client, business_data)

    if regression_data:
        print(f"\n--- Regression ({len(regression_data)} 条) ---")
        results["regression"] = run_regression(client, regression_data)

    hardware_desc = "云端推理" if args.api_key and client._is_cloud else "MacBook Pro 2019 Intel, 32GB RAM, Intel UHD Graphics 630, Ollama 本地推理"
    if args.api_key and client._is_cloud:
        hardware_desc += f" (Provider: {args.base_url})"

    all_results = {
        "model": args.model,
        "timestamp": datetime.now().isoformat(),
        "hardware": hardware_desc,
        "results": results,
    }

    json_path, md_path = generate_report(all_results, args.model, output_dir)

    biz = results.get("business", {})
    overall = biz.get("overall", {})
    reg = results.get("regression", {})
    print("\n" + "=" * 60)
    print(f"  评测完成: {args.model}")
    print("=" * 60)
    if overall:
        print(f"  综合指标:")
        print(f"    ① 幻觉率      : {overall.get('hallucination_rate', 0):.2%}")
        print(f"    ② 模板遵循    : {overall.get('template_adherence', 0):.2%}")
        print(f"    ③ 章节召回    : {overall.get('section_recall', 0):.2%}")
        print(f"    ④ 引用正确    : {overall.get('citation_precision', 0):.2%}")
        print(f"    ⑤ ROUGE-1     : {overall.get('rouge_1', 0):.4f}")
        weighted = (
            (1 - overall.get("hallucination_rate", 0)) * 0.35 +
            overall.get("template_adherence", 0) * 0.25 +
            overall.get("section_recall", 0) * 0.15 +
            overall.get("citation_precision", 0) * 0.15
        )
        print(f"    加权综合      : {weighted:.2%}")
    if reg:
        print(f"\n  回归测试（线上 Bug 沉淀）:")
        print(f"    通过率        : {reg.get('pass_rate', 0):.2%} ({reg.get('passed', 0)}/{reg.get('total', 0)})")
        if reg.get("failed_cases"):
            print(f"    ❌ 失败用例:")
            for fc in reg["failed_cases"]:
                print(f"       - {fc['id']} ({fc.get('bug_type', '')})")
                print(f"         工单: {fc.get('source_ticket', '')}")
                print(f"         原因: {'; '.join(fc.get('fails', []))}")
    print(f"\n  报告:")
    print(f"    JSON: {json_path}")
    print(f"    MD  : {md_path}")


if __name__ == "__main__":
    main()
