import json
import os
import re
from dataclasses import asdict
from typing import Optional

from app.models.knowledge_packet import (
    KnowledgeClaim,
    KnowledgeConcept,
    KnowledgeEntity,
    KnowledgeEvidence,
    KnowledgePacket,
    KnowledgeRelation,
)
from app.models.summary_input import SummaryInput
from app.models.wiki_analysis import (
    WikiAnalysis,
    WikiAnalysisClaim,
    WikiAnalysisConcept,
    WikiAnalysisEntity,
    WikiAnalysisEvidence,
    WikiAnalysisRelation,
)
from app.services.model_capability import ModelCapabilityService


class KnowledgeExtractor:
    ANALYSIS_TIMEOUT_SECONDS = float(os.getenv("WIKI_ANALYSIS_TIMEOUT_SECONDS", "45"))
    FALLBACK_TIMEOUT_SECONDS = float(os.getenv("WIKI_FALLBACK_TIMEOUT_SECONDS", "90"))
    ANALYSIS_MAX_TOKENS = int(os.getenv("WIKI_ANALYSIS_MAX_TOKENS", "1600"))
    CHUNK_MIN_MARKDOWN_LENGTH = int(os.getenv("WIKI_ANALYSIS_CHUNK_MIN_LENGTH", "6000"))
    CHUNK_MAX_CHARS = int(os.getenv("WIKI_ANALYSIS_CHUNK_MAX_CHARS", "3000"))
    FULLTEXT_MAX_TOKENS = int(os.getenv("WIKI_FULLTEXT_MAX_TOKENS", "900"))
    CHUNK_TARGET_TOKENS = int(os.getenv("WIKI_CHUNK_TARGET_TOKENS", "600"))
    CHUNK_MAX_TOKENS = int(os.getenv("WIKI_CHUNK_MAX_TOKENS", "800"))

    def analyze(self, summary_input: SummaryInput, markdown: str, gpt=None) -> WikiAnalysis:
        response_payload = self._request_analysis_payload(summary_input, markdown, gpt=gpt)
        return self._analysis_from_payload(summary_input, response_payload)

    def build_packet(self, analysis: WikiAnalysis) -> KnowledgePacket:
        return KnowledgePacket(
            packet_id=f"{analysis.source_id}:packet",
            source_id=analysis.source_id,
            source_type=analysis.source_type,
            title=analysis.title,
            summary=analysis.summary,
            entities=[
                KnowledgeEntity(
                    name=item.name,
                    entity_type=item.entity_type,
                    aliases=item.aliases,
                    description=item.description or None,
                    confidence=item.confidence,
                )
                for item in analysis.entities
            ],
            concepts=[
                KnowledgeConcept(
                    name=item.name,
                    aliases=item.aliases,
                    description=item.description,
                    parent=item.parent,
                    related=item.related,
                    confidence=item.confidence,
                )
                for item in analysis.concepts
            ],
            claims=[
                KnowledgeClaim(
                    claim=item.claim,
                    source=item.target_name,
                    target_type=item.target_type,
                    evidence_ids=item.evidence_ids,
                    confidence=item.confidence,
                )
                for item in analysis.claims
            ],
            evidence=[
                KnowledgeEvidence(
                    evidence_id=item.evidence_id,
                    source_id=item.source_id,
                    source_type=item.source_type,
                    text=item.text,
                    timestamp=item.timestamp,
                    url=item.url,
                )
                for item in analysis.evidence
            ],
            relations=[
                KnowledgeRelation(
                    source=item.source,
                    target=item.target,
                    relation_type=item.relation_type,
                    weight=item.weight,
                )
                for item in analysis.relations
            ],
            topics=analysis.topics,
        )

    def extract(self, summary_input: SummaryInput, markdown: str, gpt=None) -> KnowledgePacket:
        return self.build_packet(self.analyze(summary_input, markdown, gpt=gpt))

    def build_source_only_analysis(self, summary_input: SummaryInput, markdown: str) -> WikiAnalysis:
        title = (summary_input.title or "").strip() or summary_input.input_id
        text = re.sub(r"\s+", " ", re.sub(r"[#*_>`\[\]()]", " ", markdown or "")).strip()
        summary = text[:240] if text else "仅生成基础来源页面，知识抽取稍后可重试。"
        return WikiAnalysis(
            source_id=summary_input.input_id,
            source_type=summary_input.input_type,
            title=title,
            summary=summary,
            entities=[],
            concepts=[],
            claims=[],
            evidence=[],
            relations=[],
            topics=[],
        )

    def to_dict(self, packet: KnowledgePacket) -> dict:
        return asdict(packet)

    def _safe_name(self, value: str) -> str:
        return re.sub(r"\s+", "_", (value or "").strip()) or "unknown"

    def _request_analysis_payload(self, summary_input: SummaryInput, markdown: str, gpt=None) -> dict:
        create_chat_completion = getattr(gpt, "create_chat_completion", None) if gpt is not None else None
        if gpt is None or not callable(create_chat_completion) or not getattr(gpt, "model", None):
            raise ValueError("Wiki analysis requires a GPT client")

        return self._request_best_prompt_fallback_payload(summary_input, markdown, gpt)

    def _get_json_mode_support(self, gpt) -> Optional[bool]:
        provider_id = (getattr(gpt, "usage_context", {}) or {}).get("provider_id")
        model_name = getattr(gpt, "model", None)
        if provider_id in (None, "", "unknown") or not model_name:
            return None
        try:
            return ModelCapabilityService.ensure_json_mode_capability(str(provider_id), model_name)
        except Exception:
            return None

    def _request_json_mode_payload(self, summary_input: SummaryInput, markdown: str, gpt) -> dict:
        response = gpt.create_chat_completion(
            phase_label="Wiki Analysis",
            response_format={"type": "json_object"},
            timeout=self.ANALYSIS_TIMEOUT_SECONDS,
            max_tokens=self.ANALYSIS_MAX_TOKENS,
            request_meta={
                "stage": "analysis",
                "source_id": summary_input.input_id,
                "source_type": summary_input.input_type,
            },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 NoteMeld 的 Wiki Analysis 提取器。"
                        "你必须只输出一个合法 JSON 对象。"
                        "禁止输出解释、代码块或额外文字。"
                        "如果证据不足，不要编造。"
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_analysis_prompt(summary_input, markdown),
                },
            ],
        )
        content = ((response.choices or [None])[0].message.content or "").strip()
        if not content:
            raise ValueError("Wiki analysis returned empty content")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("Wiki analysis returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Wiki analysis returned non-object JSON")
        return payload

    def _request_best_prompt_fallback_payload(self, summary_input: SummaryInput, markdown: str, gpt) -> dict:
        chunks = self._split_markdown_chunks(markdown)
        if len(chunks) > 1:
            return self._request_chunked_prompt_json_payload(summary_input, markdown, gpt)
        return self._request_prompt_json_payload(summary_input, markdown, gpt)

    def _request_prompt_json_payload(
        self,
        summary_input: SummaryInput,
        markdown: str,
        gpt,
        stage: str = "analysis_fallback",
    ) -> dict:
        response = gpt.create_chat_completion(
            phase_label="Wiki Analysis Fallback",
            timeout=self.FALLBACK_TIMEOUT_SECONDS,
            max_tokens=self.ANALYSIS_MAX_TOKENS,
            request_meta={
                "stage": stage,
                "source_id": summary_input.input_id,
                "source_type": summary_input.input_type,
            },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 NoteMeld 的 Wiki Analysis 提取器。"
                        "只输出 BEGIN_JSON 和 END_JSON 包裹的 JSON 对象。"
                        "不要解释，不要 Markdown，不要代码块。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        self._build_analysis_prompt(summary_input, markdown)
                        + "\n\n输出格式固定为：\nBEGIN_JSON\n{...}\nEND_JSON"
                    ),
                },
            ],
        )
        content = ((response.choices or [None])[0].message.content or "").strip()
        if not content:
            raise ValueError("Wiki fallback analysis returned empty content")
        return self._normalize_analysis_payload(summary_input, self._parse_prompt_json_payload(content))

    def _parse_prompt_json_payload(self, content: str) -> dict:
        match = re.search(r"BEGIN_JSON\s*(\{[\s\S]*?\})\s*END_JSON", content)
        raw_json = match.group(1) if match else content
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Wiki fallback analysis returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Wiki fallback analysis returned non-object JSON")
        return payload

    def _request_chunked_prompt_json_payload(self, summary_input: SummaryInput, markdown: str, gpt) -> dict:
        chunks = self._split_markdown_chunks(markdown)
        if len(chunks) <= 1:
            raise ValueError("Wiki chunked fallback requires multiple chunks")
        payloads = []
        errors = []
        for index, chunk in enumerate(chunks):
            try:
                payloads.append(
                    self._request_prompt_json_payload(
                        summary_input,
                        chunk,
                        gpt,
                        stage="analysis_fallback_chunk",
                    )
                )
            except Exception as exc:
                errors.append(f"chunk {index + 1}/{len(chunks)} failed: {exc}")
        if not payloads:
            raise ValueError("; ".join(errors) or "Wiki chunked fallback returned no payloads")
        return self._merge_analysis_payloads(summary_input, payloads)

    def _split_markdown_chunks(self, markdown: str) -> list[str]:
        text = markdown or ""
        if self._estimate_tokens(text) <= self.FULLTEXT_MAX_TOKENS:
            return [text]

        h2_sections = re.split(r"(?m)(?=^##\s+)", text)
        h2_sections = [section.strip() for section in h2_sections if section.strip().startswith("## ")]
        if len(h2_sections) > 1:
            return [
                chunk
                for section in h2_sections
                for chunk in self._split_chunk_to_token_budget(section)
                if chunk
            ]
        sections = re.split(r"(?m)(?=^#{1,3}\s+)", text)
        sections = [section.strip() for section in sections if section.strip()]
        if len(sections) > 1:
            return [
                chunk
                for section in sections
                for chunk in self._split_chunk_to_token_budget(section)
                if chunk
            ]
        chunks = []
        current = ""
        for section in re.split(r"(?m)(?=^#{1,3}\s+)", text):
            section = section.strip()
            if not section:
                continue
            if current and len(current) + len(section) > self.CHUNK_MAX_CHARS:
                chunks.append(current)
                current = section
            else:
                current = f"{current}\n\n{section}".strip()
        if current:
            chunks.append(current)
        return [
            chunk
            for section in (chunks or [text])
            for chunk in self._split_chunk_to_token_budget(section)
            if chunk
        ]

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        try:
            import tiktoken

            encoder = tiktoken.get_encoding("cl100k_base")
            return len(encoder.encode(text))
        except Exception:
            cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
            other_chars = max(0, len(text) - cjk_chars)
            return max(1, int(cjk_chars * 0.75 + other_chars / 4))

    def _split_chunk_to_token_budget(self, text: str) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        if self._estimate_tokens(text) <= self.CHUNK_MAX_TOKENS:
            return [text]

        lines = text.splitlines()
        title = lines[0] if lines and lines[0].startswith("#") else ""
        body = "\n".join(lines[1:] if title else lines).strip()
        if not body:
            return [text]

        split_at = max(1, len(body) // 2)
        left = body[:split_at].strip()
        right = body[split_at:].strip()
        candidates = []
        if left:
            candidates.append(f"{title}\n{left}".strip() if title else left)
        if right:
            candidates.append(f"{title}\n{right}".strip() if title else right)
        return [
            child
            for candidate in candidates
            for child in self._split_chunk_to_token_budget(candidate)
        ]

    def _merge_analysis_payloads(self, summary_input: SummaryInput, payloads: list[dict]) -> dict:
        def unique_items(field: str, key: str) -> list[dict]:
            seen = set()
            merged = []
            for payload in payloads:
                for item in self._ensure_list(payload.get(field)):
                    value = str((item or {}).get(key) or "").strip()
                    if not value or value in seen:
                        continue
                    seen.add(value)
                    merged.append(item)
            return merged

        topics = []
        seen_topics = set()
        for payload in payloads:
            for topic in self._ensure_string_list(payload.get("topics")):
                if topic and topic not in seen_topics:
                    seen_topics.add(topic)
                    topics.append(topic)

        summaries = [str(payload.get("summary") or "").strip() for payload in payloads if str(payload.get("summary") or "").strip()]
        return self._normalize_analysis_payload(summary_input, {
            "title": str((payloads[0] or {}).get("title") or summary_input.title or summary_input.input_id).strip(),
            "summary": " ".join(summaries)[:600] or (summary_input.title or summary_input.input_id),
            "entities": unique_items("entities", "name"),
            "concepts": unique_items("concepts", "name"),
            "claims": unique_items("claims", "claim"),
            "evidence": unique_items("evidence", "evidence_id"),
            "relations": [
                item
                for payload in payloads
                for item in self._ensure_list(payload.get("relations"))
            ],
            "topics": topics,
        })

    def _normalize_analysis_payload(self, summary_input: SummaryInput, payload: dict) -> dict:
        payload = payload if isinstance(payload, dict) else {}
        evidence = []
        seen_evidence_ids = set()
        for index, item in enumerate(self._ensure_list(payload.get("evidence")), start=1):
            item = item if isinstance(item, dict) else {}
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            evidence_id = str(item.get("evidence_id") or f"{summary_input.input_id}:evidence:{index}").strip()
            if evidence_id in seen_evidence_ids:
                continue
            seen_evidence_ids.add(evidence_id)
            evidence.append({**item, "evidence_id": evidence_id, "text": text})

        evidence_ids = {item["evidence_id"] for item in evidence}
        claims = []
        for item in self._ensure_list(payload.get("claims")):
            item = item if isinstance(item, dict) else {}
            claim = str(item.get("claim") or "").strip()
            if not claim:
                continue
            target_type = str(item.get("target_type") or "source").strip()
            if target_type not in {"entity", "concept", "source"}:
                target_type = "source"
            claim_evidence_ids = [
                evidence_id
                for evidence_id in self._ensure_string_list(item.get("evidence_ids"))
                if evidence_id in evidence_ids
            ]
            claims.append({**item, "claim": claim, "target_type": target_type, "evidence_ids": claim_evidence_ids})

        return {
            "title": str(payload.get("title") or summary_input.title or summary_input.input_id).strip(),
            "summary": str(payload.get("summary") or summary_input.title or summary_input.input_id).strip(),
            "entities": [
                item for item in self._ensure_list(payload.get("entities"))
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ],
            "concepts": [
                item for item in self._ensure_list(payload.get("concepts"))
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ],
            "claims": claims,
            "evidence": evidence,
            "relations": [
                item for item in self._ensure_list(payload.get("relations"))
                if isinstance(item, dict)
                and str(item.get("source") or "").strip()
                and str(item.get("target") or "").strip()
            ],
            "topics": [item for item in self._ensure_string_list(payload.get("topics")) if item],
        }

    def _build_analysis_prompt(self, summary_input: SummaryInput, markdown: str) -> str:
        return (
            "请基于下面的源文档，提取一个结构化 Wiki Analysis JSON。\n\n"
            "输出字段必须包含：\n"
            '- "title": string\n'
            '- "summary": string\n'
            '- "entities": [{"name","entity_type","aliases","description","confidence"}]\n'
            '- "concepts": [{"name","aliases","description","parent","related","confidence"}]\n'
            '- "claims": [{"claim","target_type","target_name","evidence_ids","confidence"}]\n'
            '- "evidence": [{"evidence_id","text","timestamp","url"}]\n'
            '- "relations": [{"source","target","relation_type","weight"}]\n'
            '- "topics": string[]\n\n'
            "约束：\n"
            "1. evidence_ids 必须引用 evidence 数组中真实存在的 evidence_id。\n"
            "2. 不要输出 source_id/source_type，它们由系统注入。\n"
            "3. 如果没有足够依据，数组返回空数组，不要猜测。\n"
            "4. claims.target_type 只允许 entity、concept、source。\n\n"
            "5. 输出必须克制：entities 最多 8 个，concepts 最多 8 个，claims 最多 12 条，evidence 最多 12 条，relations 最多 12 条。\n"
            "6. evidence.text 必须引用原文中的短句或压缩后的关键证据，不要整段复制。\n\n"
            f"source_id: {summary_input.input_id}\n"
            f"source_type: {summary_input.input_type}\n"
            f"source_url: {summary_input.source_url or ''}\n"
            f"title_hint: {summary_input.title or ''}\n\n"
            "markdown:\n"
            f"{markdown}"
        )

    def _analysis_from_payload(self, summary_input: SummaryInput, payload: dict) -> WikiAnalysis:
        title = str(payload.get("title") or "").strip()
        summary = str(payload.get("summary") or "").strip()
        if not title:
            raise ValueError("Wiki analysis missing required field: title")
        if not summary:
            raise ValueError("Wiki analysis missing required field: summary")

        evidence = [self._coerce_evidence(summary_input, item) for item in self._ensure_list(payload.get("evidence"))]
        evidence_ids = {item.evidence_id for item in evidence}
        claims = [
            self._coerce_claim(item, evidence_ids)
            for item in self._ensure_list(payload.get("claims"))
        ]
        entities = [self._coerce_entity(item) for item in self._ensure_list(payload.get("entities"))]
        concepts = [self._coerce_concept(item) for item in self._ensure_list(payload.get("concepts"))]
        relations = [self._coerce_relation(item) for item in self._ensure_list(payload.get("relations"))]
        topics = [item for item in self._ensure_string_list(payload.get("topics")) if item]

        return WikiAnalysis(
            source_id=summary_input.input_id,
            source_type=summary_input.input_type,
            title=title,
            summary=summary,
            entities=entities,
            concepts=concepts,
            claims=claims,
            evidence=evidence,
            relations=relations,
            topics=topics,
        )

    def _coerce_entity(self, payload: dict) -> WikiAnalysisEntity:
        name = str((payload or {}).get("name") or "").strip()
        if not name:
            raise ValueError("Wiki analysis entity missing name")
        return WikiAnalysisEntity(
            name=name,
            normalized_name=self._safe_name(name),
            entity_type=str((payload or {}).get("entity_type") or "unknown").strip() or "unknown",
            aliases=self._ensure_string_list((payload or {}).get("aliases")),
            description=str((payload or {}).get("description") or "").strip(),
            confidence=self._coerce_float((payload or {}).get("confidence"), default=0.0),
        )

    def _coerce_concept(self, payload: dict) -> WikiAnalysisConcept:
        name = str((payload or {}).get("name") or "").strip()
        if not name:
            raise ValueError("Wiki analysis concept missing name")
        parent = str((payload or {}).get("parent") or "").strip() or None
        return WikiAnalysisConcept(
            name=name,
            normalized_name=self._safe_name(name),
            aliases=self._ensure_string_list((payload or {}).get("aliases")),
            description=str((payload or {}).get("description") or "").strip(),
            parent=parent,
            related=self._ensure_string_list((payload or {}).get("related")),
            confidence=self._coerce_float((payload or {}).get("confidence"), default=0.0),
        )

    def _coerce_evidence(self, summary_input: SummaryInput, payload: dict) -> WikiAnalysisEvidence:
        evidence_id = str((payload or {}).get("evidence_id") or "").strip()
        text = str((payload or {}).get("text") or "").strip()
        if not evidence_id:
            raise ValueError("Wiki analysis evidence missing evidence_id")
        if not text:
            raise ValueError("Wiki analysis evidence missing text")
        raw_timestamp = (payload or {}).get("timestamp")
        return WikiAnalysisEvidence(
            evidence_id=evidence_id,
            text=text,
            source_id=summary_input.input_id,
            source_type=summary_input.input_type,
            timestamp=self._coerce_timestamp(raw_timestamp),
            url=str((payload or {}).get("url") or summary_input.source_url or "").strip() or None,
        )

    def _coerce_claim(self, payload: dict, evidence_ids: set[str]) -> WikiAnalysisClaim:
        claim = str((payload or {}).get("claim") or "").strip()
        target_type = str((payload or {}).get("target_type") or "").strip()
        target_name = str((payload or {}).get("target_name") or "").strip()
        linked_evidence_ids = self._ensure_string_list((payload or {}).get("evidence_ids"))
        if not claim:
            raise ValueError("Wiki analysis claim missing claim")
        if target_type not in {"entity", "concept", "source"}:
            raise ValueError("Wiki analysis claim target_type must be entity, concept, or source")
        if not target_name:
            raise ValueError("Wiki analysis claim missing target_name")
        missing_ids = [item for item in linked_evidence_ids if item not in evidence_ids]
        if missing_ids:
            raise ValueError(f"Wiki analysis claim references missing evidence_ids: {missing_ids}")
        return WikiAnalysisClaim(
            claim=claim,
            target_type=target_type,
            target_name=target_name,
            evidence_ids=linked_evidence_ids,
            confidence=self._coerce_float((payload or {}).get("confidence"), default=0.0),
        )

    def _coerce_relation(self, payload: dict) -> WikiAnalysisRelation:
        source = str((payload or {}).get("source") or "").strip()
        target = str((payload or {}).get("target") or "").strip()
        relation_type = str((payload or {}).get("relation_type") or "").strip()
        if not source or not target or not relation_type:
            raise ValueError("Wiki analysis relation missing required fields")
        return WikiAnalysisRelation(
            source=source,
            target=target,
            relation_type=relation_type,
            weight=self._coerce_float((payload or {}).get("weight"), default=1.0),
        )

    def _ensure_list(self, value) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        raise ValueError("Wiki analysis expected list field")

    def _ensure_string_list(self, value) -> list[str]:
        return [str(item).strip() for item in self._ensure_list(value) if str(item).strip()]

    def _coerce_float(self, value, default: Optional[float]) -> Optional[float]:
        if value in (None, ""):
            return default
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Wiki analysis expected numeric value, got: {value}") from exc

    def _coerce_timestamp(self, value) -> Optional[float]:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            raw_value = value.strip()
            if not raw_value:
                return None
            try:
                return float(raw_value)
            except ValueError:
                match = re.fullmatch(r"(?:(\d+):)?([0-5]?\d):([0-5]\d)(?:\.\d+)?", raw_value)
                if match:
                    hours = int(match.group(1) or 0)
                    minutes = int(match.group(2))
                    seconds = float(match.group(3))
                    return float(hours * 3600 + minutes * 60 + seconds)
        return None
