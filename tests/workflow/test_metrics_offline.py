#!/usr/bin/env python3
"""
离线单元测试：验证 5 大核心指标的计算逻辑。
不需要 Ollama 模型。
用法: python3 tests/workflow/test_metrics_offline.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluate_model import (
    compute_hallucination,
    compute_template_adherence,
    compute_section_recall,
    compute_citation_precision,
    rouge_n,
    rouge_l,
    keyword_coverage,
)


def test_hallucination():
    # Case 1: 命中 forbidden
    r = compute_hallucination("产品发布于 2023 年 9 月", forbidden_claims=["2023 年 9 月", "50 万"])
    assert r["is_hallucinated"] is True
    assert "2023 年 9 月" in r["hit_forbidden"]

    # Case 2: 无 forbidden 命中，faithful
    r = compute_hallucination("NoteMeld 支持 macOS Windows Linux", forbidden_claims=["iOS", "Android"])
    assert r["is_hallucinated"] is False

    # Case 3: must_not_hallucinate 缺失
    r = compute_hallucination("模型很弱", must_not_hallucinate=["NoteMeld", "AI"])
    assert r["is_hallucinated"] is True
    assert "NoteMeld" in r["missing_required"]

    print("✓ test_hallucination PASS")


def test_template_adherence():
    r = compute_template_adherence(
        "# 核心结论\n产品很好\n\n# 关键发现\n功能强大",
        must_include=["核心结论", "关键发现"],
    )
    assert r["must_coverage"] == 1.0
    assert r["adherence"] == 1.0

    r = compute_template_adherence(
        "# 核心结论\n产品很好",
        must_include=["核心结论", "关键发现", "可执行建议"],
    )
    assert len(r["must_sections_missing"]) >= 2
    assert r["adherence"] < 1.0

    r = compute_template_adherence(
        "文章出现了营销内容",
        must_include=["核心结论"],
        forbidden=["营销", "标题党"],
    )
    assert r["forbidden_violation"] > 0
    print("✓ test_template_adherence PASS")


def test_section_recall():
    r = compute_section_recall("议题内容。决议内容。", required_sections=["议题", "决议", "行动项"])
    assert abs(r["recall"] - 2 / 3) < 1e-4
    assert "行动项" in r["sections_missing"]
    print("✓ test_section_recall PASS")


def test_citation_precision():
    r = compute_citation_precision(
        "# 开场 *Content-[00:00]\n# 核心 *Content-[02:00]\n截图 *Screenshot-[00:30]",
        expected_content_times=["00:00", "02:00"],
        expected_screenshot_times=["00:30"],
    )
    assert r["content"]["matched"] == 2
    assert r["screenshot"]["matched"] == 1
    assert r["overall_precision"] == 1.0

    # 时间偏差允许 10s
    r = compute_citation_precision(
        "# X *Content-[02:01]",
        expected_content_times=["02:00"],
    )
    assert r["content"]["matched"] == 1
    print("✓ test_citation_precision PASS")


def test_rouge():
    assert rouge_n("我是猫", "我是猫", 1) == 1.0
    # 差异较大的句子，LCS 较短
    assert rouge_l("一只猫在沙发上睡觉", "今天天气很好适合出门") < 0.5
    assert keyword_coverage("产品支持 AI 和 云", ["AI", "云", "移动端"]) == 2 / 3
    print("✓ test_rouge PASS")


def test_business_cases_loadable():
    import json
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for name, path in [
        ("business", "business/business_cases.json"),
        ("factual", "hallucination/factual_benchmark.json"),
        ("template", "spec/template_definitions.json"),
        ("spec", "spec/test_set_spec.json"),
        ("regression", "regression/regression_cases.json"),
        ("public_benchmarks", "public_benchmarks/public_benchmarks.json"),
    ]:
        data = json.load(open(os.path.join(base_dir, path), "r", encoding="utf-8"))
        print(f"✓ {path} 加载成功")
    print("✓ test_business_cases_loadable PASS")


def test_regression_case_schema():
    import json
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data = json.load(open(os.path.join(base_dir, "regression/regression_cases.json"), "r", encoding="utf-8"))
    cases = data["cases"]
    required_fields = ["id", "source_ticket", "bug_type", "input", "expected", "source"]
    for c in cases:
        for f in required_fields:
            assert f in c, f"regression case {c.get('id', '?')} missing field: {f}"
        assert "text" in c["input"], "regression input.text required"
        assert "template_id" in c["expected"], "regression expected.template_id required"
        assert "origin" in c["source"], "regression source.origin required"
    bug_types = {"hallucination", "missing_section", "screenshot_missing", "wrong_citation", "wrong_template", "schema_violation", "content_deletion"}
    for c in cases:
        assert c["bug_type"] in bug_types, f"bug_type {c['bug_type']} not in enum"
    print(f"✓ test_regression_case_schema PASS ({len(cases)} cases)")


if __name__ == "__main__":
    test_hallucination()
    test_template_adherence()
    test_section_recall()
    test_citation_precision()
    test_rouge()
    test_business_cases_loadable()
    test_regression_case_schema()
    print("\n🎉 全部离线指标测试通过")
