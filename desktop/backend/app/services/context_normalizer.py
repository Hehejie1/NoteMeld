from __future__ import annotations

from typing import Optional

from app.models.audio_model import AudioDownloadResult
from app.models.summary_input import (
    ContextBlock,
    DocumentContext,
    InputInspection,
    MetaContext,
    PageContext,
    SocialComment,
    SocialContext,
    SummaryInput,
    TranscriptContext,
    VisionContext,
    WeightedContextPack,
)
from app.models.transcriber_model import TranscriptResult
from app.services.ingestion.types import ParsedDocument


class ContextNormalizer:
    def from_document_task(
        self,
        task_id: str,
        source_url: str,
        parsed_document: ParsedDocument,
        user_options: dict,
    ) -> SummaryInput:
        document_context = DocumentContext(
            title=parsed_document.title,
            parser_name=parsed_document.parser_name,
            parser_backend=parsed_document.parser_backend,
            fallback_used=parsed_document.fallback_used,
            page_count=parsed_document.page_count,
            text=parsed_document.text,
            resource_type=parsed_document.resource_type,
            source_url=source_url,
            quality=parsed_document.quality,
            pages=[
                {
                    "page_number": page.page_number,
                    "text": page.text,
                    "confidence": page.confidence,
                    "warnings": page.warnings,
                }
                for page in parsed_document.pages
            ],
        )
        return SummaryInput(
            input_id=task_id,
            input_type="uploaded_document" if parsed_document.resource_type == "document" else parsed_document.resource_type,
            source_url=source_url,
            platform="uploaded_file",
            title=parsed_document.title,
            user_goal=user_options.get("extras"),
            user_options=user_options,
            page_context=None,
            transcript_context=None,
            vision_context=VisionContext(mode="disabled"),
            social_context=None,
            meta_context=MetaContext(
                resource_type=parsed_document.resource_type,
                model_name=user_options.get("model_name"),
                provider_id=user_options.get("provider_id"),
                raw=parsed_document.metadata,
            ),
            document_context=document_context,
        )

    def from_video_task(
        self,
        task_id: str,
        video_url: str,
        platform: str,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        user_options: dict,
        inspection: Optional[InputInspection] = None,
    ) -> SummaryInput:
        raw = audio_meta.raw_info or {}
        page_context = PageContext(
            title=audio_meta.title or raw.get("title") or "",
            description=raw.get("description"),
            author=raw.get("uploader") or raw.get("author"),
            publish_time=str(raw.get("timestamp")) if raw.get("timestamp") else None,
            url=video_url,
            site_name=platform,
            page_type="video_page",
            topic=audio_meta.title,
            headings=[],
            main_text_summary=raw.get("description"),
            key_points=[],
            links=[],
            detected_media=inspection.detected_media if inspection else [],
            raw_text_path=None,
            confidence=0.7,
        )
        transcript_context = TranscriptContext(
            language=transcript.language,
            full_text=transcript.full_text,
            segments=transcript.segments,
            duration=audio_meta.duration,
            quality={
                "segment_count": len(transcript.segments or []),
                "full_text_chars": len(transcript.full_text or ""),
            },
        )
        social_context = self._build_social_context(raw)
        return SummaryInput(
            input_id=task_id,
            input_type=inspection.input_type if inspection else "video_link",
            source_url=video_url,
            platform=platform,
            title=audio_meta.title,
            user_goal=user_options.get("extras"),
            user_options=user_options,
            page_context=page_context,
            transcript_context=transcript_context,
            vision_context=VisionContext(mode="disabled"),
            social_context=social_context,
            meta_context=MetaContext(
                resource_type=inspection.input_type if inspection else "video_link",
                platform=platform,
                video_id=audio_meta.video_id,
                duration=audio_meta.duration,
                language=transcript.language,
                model_name=user_options.get("model_name"),
                provider_id=user_options.get("provider_id"),
                raw=raw,
            ),
        )

    def build_weighted_pack(self, summary_input: SummaryInput) -> WeightedContextPack:
        blocks = []
        primary_sources = []
        auxiliary_sources = []
        source_weights = {}

        if summary_input.transcript_context:
            primary_sources.append("transcript")
            source_weights["transcript"] = 1.0
            blocks.append(
                ContextBlock(
                    source_type="transcript",
                    role="primary_facts",
                    content=summary_input.transcript_context.full_text,
                    weight=1.0,
                    confidence=0.9,
                    include_policy="refine_stage",
                )
            )

        if getattr(summary_input, "document_context", None):
            primary_sources.append("document")
            source_weights["document"] = 1.0
            document = summary_input.document_context
            blocks.append(
                ContextBlock(
                    source_type="document",
                    role="document_primary_facts",
                    content=self._format_document_context(document),
                    weight=1.0,
                    confidence=0.9,
                    include_policy="always",
                )
            )

        if summary_input.page_context:
            page_is_primary = summary_input.input_type == "web_link" and not summary_input.transcript_context
            page_weight = 1.0 if page_is_primary else 0.65
            page_policy = "always" if page_is_primary else "final_stage"
            if page_is_primary:
                primary_sources.append("page")
            else:
                auxiliary_sources.append("page")
            source_weights["page"] = page_weight
            page = summary_input.page_context
            content = self._format_page_context(page)
            blocks.append(
                ContextBlock(
                    source_type="page",
                    role="page_structure",
                    content=content,
                    weight=page_weight,
                    confidence=page.confidence,
                    include_policy=page_policy,
                )
            )

        web_search_context = summary_input.user_options.get("web_search_context")
        if web_search_context:
            auxiliary_sources.append("search")
            source_weights["search"] = 0.45
            blocks.append(
                ContextBlock(
                    source_type="search",
                    role="external_evidence",
                    content=str(web_search_context),
                    weight=0.45,
                    confidence=0.65,
                    include_policy="final_stage",
                )
            )

        frame_context = summary_input.user_options.get("frame_context")
        if frame_context:
            auxiliary_sources.append("vision")
            source_weights["vision"] = 0.7
            blocks.append(
                ContextBlock(
                    source_type="vision",
                    role="visual_evidence",
                    content=str(frame_context),
                    weight=0.7,
                    confidence=0.7,
                    include_policy="final_stage",
                )
            )

        if summary_input.social_context:
            auxiliary_sources.append("social")
            source_weights["social"] = 0.25
            social = summary_input.social_context
            blocks.append(
                ContextBlock(
                    source_type="social",
                    role="audience_feedback",
                    content=self._format_social_context(social),
                    weight=0.25,
                    confidence=social.confidence,
                    include_policy="final_stage",
                )
            )

        return WeightedContextPack(
            input_id=summary_input.input_id,
            primary_sources=primary_sources,
            auxiliary_sources=auxiliary_sources,
            source_weights=source_weights,
            context_blocks=blocks,
            token_budget={"max_context_chars": 8000},
        )

    def _build_social_context(self, raw: dict) -> SocialContext:
        comments = [self._build_social_comment(item) for item in raw.get("comments", []) if item]
        danmaku_items = self._extract_danmaku_items(raw.get("danmaku") or raw.get("bullet_comments") or [])
        comments_summary = raw.get("hot_comments_summary") or raw.get("comments_summary")
        return SocialContext(
            like_count=raw.get("like_count"),
            comment_count=raw.get("comment_count"),
            share_count=raw.get("share_count"),
            favorite_count=raw.get("favorite_count"),
            comments_summary=comments_summary,
            useful_supplements=danmaku_items,
            comments=comments,
            confidence=0.75 if comments or danmaku_items or comments_summary else (0.5 if raw else 0.0),
        )

    def _build_social_comment(self, item: dict | str) -> SocialComment:
        if isinstance(item, str):
            return SocialComment(content=item)
        return SocialComment(
            author=item.get("author") or item.get("user") or item.get("uname"),
            content=item.get("content") or item.get("text") or item.get("message") or "",
            like_count=item.get("like_count") or item.get("likes"),
            reply_count=item.get("reply_count") or item.get("replies_count"),
            replies=[
                self._build_social_comment(reply)
                for reply in item.get("replies", [])
                if reply
            ],
        )

    def _extract_danmaku_items(self, danmaku: list) -> list[str]:
        items = []
        seen = set()
        for item in danmaku:
            text = item if isinstance(item, str) else item.get("text") or item.get("content") or item.get("message")
            if not text or text in seen:
                continue
            seen.add(text)
            items.append(text)
        return items[:20]

    def _format_social_context(self, social: SocialContext) -> str:
        sections = [
            f"点赞数：{social.like_count}; 评论数：{social.comment_count}; 分享数：{social.share_count}",
        ]
        if social.comments_summary:
            sections.append(f"热评摘要：{social.comments_summary}")
        if social.comments:
            comments = "\n".join(
                f"- {comment.author or '匿名'}：{comment.content}"
                for comment in social.comments[:10]
                if comment.content
            )
            if comments:
                sections.append("代表评论：\n" + comments)
        if social.useful_supplements:
            danmaku = "\n".join(f"- 弹幕：{item}" for item in social.useful_supplements[:10])
            sections.append("弹幕补充：\n" + danmaku)
        return "\n".join(sections)

    def _format_document_context(self, document) -> str:
        sections = [
            f"标题：{document.title}",
            f"解析器：{document.parser_name}",
            f"页数：{document.page_count}",
            f"证据锚点数：{getattr(document, 'evidence_count', 0)}",
            f"知识块数：{getattr(document, 'chunk_count', 0)}",
        ]
        if document.quality:
            sections.append(f"解析质量：{document.quality}")
        if document.raw_json_path:
            sections.append(f"结构化解析文件：{document.raw_json_path}")
        if document.text:
            sections.append("正文：\n" + document.text)
        return "\n".join(section for section in sections if section)

    def _format_page_context(self, page: PageContext) -> str:
        sections = [
            f"标题：{page.title}",
            f"描述：{page.description or ''}",
            f"作者：{page.author or ''}",
            f"主题：{page.topic or ''}",
        ]

        if page.headings:
            headings = "\n".join(
                f"- H{heading.get('level')} {heading.get('text')}"
                for heading in page.headings
                if heading.get("text")
            )
            if headings:
                sections.append("标题层级：\n" + headings)

        if page.links:
            links = "\n".join(
                f"- {link.get('text') or link.get('url')}: {link.get('url')}"
                for link in page.links
                if link.get("url")
            )
            if links:
                sections.append("链接：\n" + links)

        if page.detected_media:
            media = "\n".join(
                f"- {item.get('platform')} {item.get('type')}: {item.get('url')}"
                for item in page.detected_media
                if item.get("url")
            )
            if media:
                sections.append("支持平台媒体：\n" + media)

        return "\n".join(section for section in sections if section)
