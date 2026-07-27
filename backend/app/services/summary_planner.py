from app.models.summary_input import SummaryInput, WeightedContextPack
from app.models.summary_plan import SummaryPlan, build_default_render_contract


class VisionSamplingPlanner:
    DEFAULT_MAX_POINTS = 8
    VISUAL_KEYWORDS = [
        "演示",
        "展示",
        "架构图",
        "流程图",
        "图表",
        "截图",
        "画面",
        "屏幕",
        "操作",
        "步骤",
        "流程",
        "架构",
        "关键",
        "对比",
        "总结",
        "数据",
        "图",
    ]

    def plan(self, summary_input: SummaryInput) -> dict:
        mode = summary_input.user_options.get("vision_mode")
        if not mode:
            mode = "fixed_interval" if summary_input.user_options.get("video_understanding") else "disabled"

        if mode == "fixed_interval":
            return self._build_fixed_interval_policy(summary_input)
        if mode == "smart_sampling":
            return self._build_smart_sampling_policy(summary_input)

        return {"mode": "disabled", "fixed_interval": 0, "timestamps": [], "sampling_points": []}

    def _build_fixed_interval_policy(self, summary_input: SummaryInput) -> dict:
        interval = summary_input.user_options.get("video_interval", 0) or 0
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = 0

        duration = self._duration(summary_input)
        timestamps = []
        if interval > 0 and duration > 0:
            current = 0.0
            while current < duration:
                timestamps.append(round(current, 3))
                current += interval

        max_points = self._max_points(summary_input)
        if max_points:
            timestamps = timestamps[:max_points]

        return {
            "mode": "fixed_interval",
            "fixed_interval": interval,
            "timestamps": timestamps,
            "sampling_points": [
                {
                    "timestamp": timestamp,
                    "source": "fixed_interval",
                    "reason": f"每 {interval} 秒抽帧",
                }
                for timestamp in timestamps
            ],
        }

    def _build_smart_sampling_policy(self, summary_input: SummaryInput) -> dict:
        transcript = summary_input.transcript_context
        if not transcript or not transcript.segments:
            return {"mode": "smart_sampling", "fixed_interval": 0, "timestamps": [], "sampling_points": []}

        max_points = self._max_points(summary_input)
        scored_segments = []
        fallback_segments = []
        for index, segment in enumerate(transcript.segments):
            text = (segment.text or "").strip()
            if not text:
                continue
            matched = self._matched_keywords(text)
            midpoint = round((float(segment.start) + float(segment.end)) / 2, 3)
            if matched:
                scored_segments.append((index, len(matched), segment, midpoint, matched))
            else:
                fallback_segments.append((index, segment, midpoint))

        selected = sorted(scored_segments, key=lambda item: (-item[1], item[0]))[:max_points]
        if not selected:
            selected = [
                (index, 0, segment, midpoint, [])
                for index, segment, midpoint in fallback_segments[:max_points]
            ]
        selected.sort(key=lambda item: item[0])

        key_moments = [
            {
                "timestamp": midpoint,
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text,
                "source": "transcript",
                "reason": self._reason(matched),
                "importance": 0.9 if matched else 0.5,
            }
            for _, _, segment, midpoint, matched in selected
        ]
        transcript.key_moments = key_moments

        return {
            "mode": "smart_sampling",
            "fixed_interval": 0,
            "timestamps": [moment["timestamp"] for moment in key_moments],
            "sampling_points": key_moments,
        }

    def _matched_keywords(self, text: str) -> list[str]:
        matched = []
        for keyword in self.VISUAL_KEYWORDS:
            if keyword in text and not any(keyword in existing for existing in matched):
                matched.append(keyword)
        return matched

    def _reason(self, matched: list[str]) -> str:
        if matched:
            return "命中视觉线索：" + "、".join(matched)
        return "字幕段落代表点"

    def _duration(self, summary_input: SummaryInput) -> float:
        if summary_input.transcript_context and summary_input.transcript_context.duration:
            return float(summary_input.transcript_context.duration)
        if summary_input.meta_context.duration:
            return float(summary_input.meta_context.duration)
        return 0.0

    def _max_points(self, summary_input: SummaryInput) -> int:
        raw_value = summary_input.user_options.get("max_sampling_points", self.DEFAULT_MAX_POINTS)
        try:
            return max(0, int(raw_value))
        except (TypeError, ValueError):
            return self.DEFAULT_MAX_POINTS


class SummaryPlanner:
    LONG_VIDEO_SECONDS = 30 * 60
    LONG_TRANSCRIPT_SEGMENTS = 120

    def plan(self, summary_input: SummaryInput, pack: WeightedContextPack) -> SummaryPlan:
        output_type = summary_input.user_options.get("output_type", "note_markdown")
        strategy = self._choose_strategy(summary_input, output_type)
        return SummaryPlan(
            input_id=summary_input.input_id,
            output_type=output_type,
            strategy=strategy,
            chunk_policy={
                "max_segments_per_chunk": 80,
                "compress_every_steps": 4,
                "preserve_timeline": True,
            },
            context_policy={
                "direct": ["page", "transcript", "vision", "social"],
                "map": ["transcript"],
                "refine": ["transcript", "vision_summary"],
                "final": ["page", "transcript_summary", "vision", "social"],
                "wiki": ["page", "transcript_summary", "vision", "entities", "concepts"],
            },
            vision_policy=VisionSamplingPlanner().plan(summary_input),
            render_contract=build_default_render_contract(output_type),
            checkpoint_policy={"enabled": True, "key": summary_input.input_id},
            wiki_policy={"enabled": bool(summary_input.user_options.get("enable_wiki", True))},
        )

    def _choose_strategy(self, summary_input: SummaryInput, output_type: str) -> str:
        if output_type == "export_outline":
            return "map_reduce"

        duration = summary_input.meta_context.duration or 0
        segment_count = 0
        if summary_input.transcript_context:
            segment_count = len(summary_input.transcript_context.segments or [])

        if duration >= self.LONG_VIDEO_SECONDS or segment_count >= self.LONG_TRANSCRIPT_SEGMENTS:
            return "hybrid"

        return "direct"
