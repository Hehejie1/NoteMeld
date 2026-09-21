#!/usr/bin/env python3
"""
NoteMeld 检索系统离线评测脚本 v1.0
基于真实 wiki concepts 评估 Recall@3/5/10、MRR、引用准确率

指标定义：
- Recall@k: 前 k 个结果中命中任意 expected page 的查询比例
- MRR (Mean Reciprocal Rank): 第一个命中结果的排名倒数的平均值
- Citation Accuracy (引用准确率): 返回结果的 top 1 是否在 expected_pages 中
- Hit@k per query: 单条查询前 k 结果中命中的 expected 数量比例

用法:
  # 从项目根目录运行
  python3 tests/agent/evaluate_retrieval.py
  python3 tests/agent/evaluate_retrieval.py --wiki-dir vector_db/note_results/wiki
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# 确保能导入 backend 模块
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # tests/agent/ → tests/ → 项目根
sys.path.insert(0, str(PROJECT_ROOT / "desktop" / "backend"))

from app.services.wiki_search import WikiSearch


def load_queries(queries_path: Path) -> dict[str, Any]:
    with open(queries_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_page_id_from_result(result: dict[str, Any]) -> str | None:
    """从 WikiSearch 返回结果中提取 page_id。"""
    metadata = result.get("metadata") or {}
    page_id = metadata.get("page_id")
    if page_id:
        return str(page_id)
    # wiki_concept/wiki_entity 类型的 id 格式可能是 wiki-concept-xxx 或 concept-xxx-xxx
    result_id = str(result.get("id") or "")
    # 尝试从 title 匹配
    title = str(result.get("title") or "")
    return title if title else None


def hits_at_k(retrieved_pages: list[str], expected_pages: list[str], k: int) -> float:
    """计算前 k 结果中命中 expected 的数量比例。"""
    if not expected_pages:
        return 0.0
    top_k = retrieved_pages[:k]
    hits = sum(1 for p in top_k if p in expected_pages)
    return hits / len(expected_pages)


def recall_at_k(retrieved_pages: list[str], expected_pages: list[str], k: int) -> bool:
    """判断前 k 结果中是否命中任意 expected page。"""
    top_k = retrieved_pages[:k]
    return any(p in expected_pages for p in top_k)


def reciprocal_rank(retrieved_pages: list[str], expected_pages: list[str]) -> float:
    """计算第一个命中结果的排名倒数 (1-based rank)。"""
    for idx, page in enumerate(retrieved_pages, start=1):
        if page in expected_pages:
            return 1.0 / idx
    return 0.0


def first_hit_rank(retrieved_pages: list[str], expected_pages: list[str]) -> int:
    """返回第一个命中结果的排名 (1-based)，未命中返回 0。"""
    for idx, page in enumerate(retrieved_pages, start=1):
        if page in expected_pages:
            return idx
    return 0


def evaluate_query(searcher: WikiSearch, query_item: dict[str, Any], limit: int = 10) -> dict[str, Any]:
    """评估单条 query。"""
    qid = query_item["id"]
    query_text = query_item["query"]
    expected = query_item.get("expected_pages", [])
    category = query_item.get("category", "unknown")

    results = searcher.search(query_text, limit=limit)

    # 提取 page_id 列表
    retrieved_page_ids: list[str] = []
    retrieved_details: list[dict[str, Any]] = []
    for r in results:
        pid = extract_page_id_from_result(r)
        if pid:
            retrieved_page_ids.append(pid)
            retrieved_details.append({
                "page_id": pid,
                "title": r.get("title"),
                "score": r.get("score"),
                "source_type": r.get("type") or r.get("source_type"),
            })

    # 计算指标
    r_at_3 = recall_at_k(retrieved_page_ids, expected, 3)
    r_at_5 = recall_at_k(retrieved_page_ids, expected, 5)
    r_at_10 = recall_at_k(retrieved_page_ids, expected, 10)
    mrr = reciprocal_rank(retrieved_page_ids, expected)
    first_rank = first_hit_rank(retrieved_page_ids, expected)
    citation_acc = 1.0 if retrieved_page_ids and retrieved_page_ids[0] in expected else 0.0
    hit_ratio = hits_at_k(retrieved_page_ids, expected, limit)

    return {
        "id": qid,
        "query": query_text,
        "category": category,
        "expected_pages": expected,
        "retrieved_pages": retrieved_page_ids,
        "retrieved_details": retrieved_details,
        "metrics": {
            "recall@3": r_at_3,
            "recall@5": r_at_5,
            "recall@10": r_at_10,
            "mrr": mrr,
            "citation_accuracy": citation_acc,
            "hit_ratio": hit_ratio,
            "first_hit_rank": first_rank,
        },
    }


def aggregate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总所有 query 的指标。"""
    n = len(results)
    if n == 0:
        return {}

    total_recall_3 = sum(r["metrics"]["recall@3"] for r in results) / n
    total_recall_5 = sum(r["metrics"]["recall@5"] for r in results) / n
    total_recall_10 = sum(r["metrics"]["recall@10"] for r in results) / n
    total_mrr = sum(r["metrics"]["mrr"] for r in results) / n
    total_citation = sum(r["metrics"]["citation_accuracy"] for r in results) / n

    # 按类别统计
    by_category: dict[str, dict[str, Any]] = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"count": 0, "recall@3": 0, "recall@5": 0, "recall@10": 0, "mrr": 0, "citation_accuracy": 0}
        by_category[cat]["count"] += 1
        by_category[cat]["recall@3"] += r["metrics"]["recall@3"]
        by_category[cat]["recall@5"] += r["metrics"]["recall@5"]
        by_category[cat]["recall@10"] += r["metrics"]["recall@10"]
        by_category[cat]["mrr"] += r["metrics"]["mrr"]
        by_category[cat]["citation_accuracy"] += r["metrics"]["citation_accuracy"]

    for cat in by_category:
        cnt = by_category[cat]["count"]
        for k in ("recall@3", "recall@5", "recall@10", "mrr", "citation_accuracy"):
            by_category[cat][k] = round(by_category[cat][k] / cnt, 4) if cnt > 0 else 0

    # 未命中的 case
    missed = [r for r in results if not r["metrics"]["recall@10"]]

    return {
        "total_queries": n,
        "overall": {
            "recall@3": round(total_recall_3, 4),
            "recall@5": round(total_recall_5, 4),
            "recall@10": round(total_recall_10, 4),
            "mrr": round(total_mrr, 4),
            "citation_accuracy": round(total_citation, 4),
        },
        "by_category": by_category,
        "missed_cases": [
            {
                "id": r["id"],
                "query": r["query"],
                "expected_pages": r["expected_pages"],
                "retrieved_pages": r["retrieved_pages"][:5],
            }
            for r in missed
        ],
        "missed_count": len(missed),
    }


def generate_markdown_report(
    summary: dict[str, Any],
    query_results: list[dict[str, Any]],
    wiki_dir: Path,
    elapsed: float,
) -> str:
    """生成 Markdown 格式的评测报告。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    overall = summary["overall"]

    lines: list[str] = []
    lines.append(f"# NoteMeld 检索评测报告")
    lines.append("")
    lines.append(f"生成时间: {ts}")
    lines.append(f"评测集: NoteMeld Retrieval Benchmark v1.0")
    lines.append(f"Wiki 目录: {wiki_dir}")
    lines.append(f"Query 数量: {summary['total_queries']}")
    lines.append(f"评测耗时: {elapsed:.2f}s")
    lines.append("")

    lines.append("## 一、总体指标")
    lines.append("")
    lines.append("| 指标 | 值 | 说明 |")
    lines.append("|---|---|---|")
    lines.append(f"| **Recall@3** | {overall['recall@3']:.2%} | 前 3 结果中命中正确答案的查询比例 |")
    lines.append(f"| **Recall@5** | {overall['recall@5']:.2%} | 前 5 结果中命中正确答案的查询比例 |")
    lines.append(f"| **Recall@10** | {overall['recall@10']:.2%} | 前 10 结果中命中正确答案的查询比例 |")
    lines.append(f"| **MRR** | {overall['mrr']:.4f} | 平均倒数排名，越高越好（1.0 为满分） |")
    lines.append(f"| **引用准确率 (Top-1)** | {overall['citation_accuracy']:.2%} | 第一条结果即为正确答案的比例 |")
    lines.append(f"| **未命中数** | {summary['missed_count']}/{summary['total_queries']} | top10 仍未命中的查询 |")
    lines.append("")

    # 业界基准参考
    lines.append("### 业界参考基线")
    lines.append("")
    lines.append("| 系统/论文 | Recall@5 | MRR | 场景 |")
    lines.append("|---|---|---|---|")
    lines.append("| BM25 (传统关键词) | ~60-70% | ~0.45 | 通用搜索 |")
    lines.append("| DPR (dense retrieval) | ~75-85% | ~0.55 | 开放域 QA |")
    lines.append("| Hybrid (BM25+Dense) | ~80-90% | ~0.65 | 企业 RAG |")
    lines.append("| NoteMeld WikiSearch (关键词) | - | - | 个人知识库 |")
    lines.append("")

    lines.append("## 二、按问题类型细分")
    lines.append("")
    lines.append("| 类别 | 数量 | Recall@3 | Recall@5 | Recall@10 | MRR | 引用准确率 |")
    lines.append("|---|---|---|---|---|---|---|")
    category_names = {
        "concept_definition": "概念定义",
        "how_to": "方法类",
        "comparison": "对比类",
        "detail": "细节类",
        "entity_lookup": "实体查询",
    }
    for cat, stats in summary["by_category"].items():
        name = category_names.get(cat, cat)
        lines.append(
            f"| {name} | {stats['count']} | {stats['recall@3']:.2%} | {stats['recall@5']:.2%} | "
            f"{stats['recall@10']:.2%} | {stats['mrr']:.4f} | {stats['citation_accuracy']:.2%} |"
        )
    lines.append("")

    lines.append("## 三、未命中 Case 分析")
    lines.append("")
    if summary["missed_cases"]:
        lines.append("以下 query 在 top10 结果中仍未找到期望页面：")
        lines.append("")
        lines.append("| ID | Query | 期望页面 | 实际返回 top5 |")
        lines.append("|---|---|---|---|")
        for m in summary["missed_cases"]:
            expected = ", ".join(m["expected_pages"])
            retrieved = ", ".join(m["retrieved_pages"][:5]) if m["retrieved_pages"] else "(无结果)"
            lines.append(f"| {m['id']} | {m['query']} | {expected} | {retrieved} |")
    else:
        lines.append("🎉 所有 query 均在 top10 中命中！")
    lines.append("")

    lines.append("## 四、每条 Query 详细结果")
    lines.append("")
    lines.append("| ID | Query | R@3 | R@5 | R@10 | MRR | 首命中排名 | 命中 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in query_results:
        m = r["metrics"]
        hit_mark = "✅" if m["recall@10"] else "❌"
        rank_str = str(m["first_hit_rank"]) if m["first_hit_rank"] > 0 else "-"
        lines.append(
            f"| {r['id']} | {r['query'][:20]} | {'✅' if m['recall@3'] else '❌'} | "
            f"{'✅' if m['recall@5'] else '❌'} | {'✅' if m['recall@10'] else '❌'} | "
            f"{m['mrr']:.2f} | {rank_str} | {hit_mark} |"
        )
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="NoteMeld 检索系统离线评测")
    parser.add_argument(
        "--wiki-dir",
        type=str,
    default=str(PROJECT_ROOT / "desktop" / "data" / "note_results" / "wiki"),
        help="Wiki 数据目录路径",
    )
    parser.add_argument(
        "--queries",
        type=str,
        default=str(Path(__file__).parent / "retrieval" / "retrieval_queries.json"),
        help="评测 query 文件路径",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "tests" / "reports"),
        help="报告输出目录",
    )
    parser.add_argument("--limit", type=int, default=10, help="每个 query 检索的 top K 结果数")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir)
    queries_path = Path(args.queries)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("NoteMeld 检索系统离线评测 v1.0")
    print("=" * 60)
    print(f"Wiki 目录: {wiki_dir}")
    print(f"评测集:   {queries_path}")
    print(f"输出目录: {output_dir}")
    print()

    if not wiki_dir.exists():
        print(f"❌ Wiki 目录不存在: {wiki_dir}")
        sys.exit(1)
    if not queries_path.exists():
        print(f"❌ 评测集不存在: {queries_path}")
        sys.exit(1)

    # 加载 query
    dataset = load_queries(queries_path)
    queries = dataset["queries"]
    print(f"加载 {len(queries)} 条 query")
    print()

    # 初始化检索器
    print("初始化 WikiSearch...")
    searcher = WikiSearch(wiki_dir)

    # 执行评测
    print(f"开始评测 (top {args.limit})...")
    start_time = time.time()
    results: list[dict[str, Any]] = []
    for i, q in enumerate(queries, 1):
        r = evaluate_query(searcher, q, limit=args.limit)
        results.append(r)
        m = r["metrics"]
        status = "✅" if m["recall@5"] else "⚠️" if m["recall@10"] else "❌"
        print(f"  [{i:02d}/{len(queries)}] {status} {q['query'][:30]:<30s} "
              f"R@5={m['recall@5']} MRR={m['mrr']:.2f}")
    elapsed = time.time() - start_time
    print()

    # 汇总指标
    summary = aggregate_metrics(results)
    overall = summary["overall"]
    print("=" * 60)
    print("评测完成！总体结果：")
    print(f"  Recall@3:            {overall['recall@3']:.2%}")
    print(f"  Recall@5:            {overall['recall@5']:.2%}")
    print(f"  Recall@10:           {overall['recall@10']:.2%}")
    print(f"  MRR:                 {overall['mrr']:.4f}")
    print(f"  引用准确率(Top-1):   {overall['citation_accuracy']:.2%}")
    print(f"  未命中(top10):       {summary['missed_count']}/{summary['total_queries']}")
    print(f"  耗时:                {elapsed:.2f}s")
    print("=" * 60)

    # 保存报告
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"retrieval_eval_{ts}.json"
    md_path = output_dir / f"retrieval_eval_{ts}.md"
    latest_json = output_dir / "retrieval_eval_latest.json"
    latest_md = output_dir / "retrieval_eval_latest.md"

    report_data = {
        "timestamp": ts,
        "wiki_dir": str(wiki_dir),
        "elapsed_seconds": round(elapsed, 2),
        "summary": summary,
        "per_query_results": results,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    with open(latest_json, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    md_content = generate_markdown_report(summary, results, wiki_dir, elapsed)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    with open(latest_md, "w", encoding="utf-8") as f:
        f.write(md_content)

    print()
    print(f"📄 JSON 报告: {json_path}")
    print(f"📄 Markdown 报告: {md_path}")
    print(f"📄 Latest 快捷链接: {latest_md}")


if __name__ == "__main__":
    main()
