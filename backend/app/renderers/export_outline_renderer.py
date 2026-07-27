from app.models.knowledge_packet import KnowledgePacket
from app.models.summary_input import SummaryInput


class ExportOutlineRenderer:
    def render(self, summary_input: SummaryInput, packet: KnowledgePacket) -> dict:
        slides = [
            self._title_slide(summary_input, packet),
            self._claims_slide(packet),
            self._vision_slide(summary_input),
            self._social_slide(summary_input),
            self._evidence_slide(packet),
        ]
        return {
            "target": "pptx",
            "format": "structured_json",
            "source": {
                "id": summary_input.input_id,
                "type": summary_input.input_type,
                "title": summary_input.title or packet.title,
                "url": summary_input.source_url,
                "platform": summary_input.platform,
            },
            "metadata": {
                "topics": packet.topics,
                "entities": [entity.name for entity in packet.entities],
                "concepts": [concept.name for concept in packet.concepts],
            },
            "slides": slides,
        }

    def _title_slide(self, summary_input: SummaryInput, packet: KnowledgePacket) -> dict:
        page = summary_input.page_context
        return {
            "title": summary_input.title or packet.title,
            "main_point": packet.summary,
            "supporting_evidence": [
                item
                for item in [
                    page.description if page else None,
                    f"作者：{page.author}" if page and page.author else None,
                    f"来源：{summary_input.source_url}" if summary_input.source_url else None,
                ]
                if item
            ],
            "quote": "",
            "suggested_visual_timestamp": None,
        }

    def _claims_slide(self, packet: KnowledgePacket) -> dict:
        claims = [claim.claim for claim in packet.claims if claim.claim]
        return {
            "title": "核心观点",
            "main_point": claims[0] if claims else packet.summary,
            "supporting_evidence": claims,
            "quote": "",
            "suggested_visual_timestamp": self._first_evidence_timestamp(packet),
        }

    def _vision_slide(self, summary_input: SummaryInput) -> dict:
        frames = summary_input.vision_context.frames if summary_input.vision_context else []
        frame = frames[0] if frames else None
        return {
            "title": "视觉证据",
            "main_point": frame.summary if frame else "暂无视觉采样帧",
            "supporting_evidence": [frame.summary] if frame else [],
            "quote": "",
            "suggested_visual_timestamp": frame.timestamp if frame else None,
            "image_url": frame.image_url if frame else "",
        }

    def _social_slide(self, summary_input: SummaryInput) -> dict:
        social = summary_input.social_context
        evidence = []
        if social:
            if social.comments_summary:
                evidence.append(social.comments_summary)
            evidence.extend(
                f"{comment.author or '匿名'}：{comment.content}"
                for comment in social.comments[:5]
                if comment.content
            )
            evidence.extend(social.useful_supplements[:5])
        return {
            "title": "受众反馈",
            "main_point": evidence[0] if evidence else "暂无评论上下文",
            "supporting_evidence": evidence,
            "quote": "",
            "suggested_visual_timestamp": None,
        }

    def _evidence_slide(self, packet: KnowledgePacket) -> dict:
        evidence = [item.text for item in packet.evidence if item.text]
        return {
            "title": "证据与来源",
            "main_point": "关键证据摘录",
            "supporting_evidence": evidence,
            "quote": evidence[0] if evidence else "",
            "suggested_visual_timestamp": self._first_evidence_timestamp(packet),
        }

    def _first_evidence_timestamp(self, packet: KnowledgePacket):
        for item in packet.evidence:
            if item.timestamp is not None:
                return item.timestamp
        return None
