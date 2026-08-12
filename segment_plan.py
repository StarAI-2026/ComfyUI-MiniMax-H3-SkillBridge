"""Strict, deterministic segment plans for sequential MiniMax H3 renders."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any


PLAN_MARKER = "[SEGMENT_PLAN_JSON]"
PLAN_SCHEMA = "stariai_h3_segment_plan_v1"
FPS = 24
MAX_FIRST_SEGMENT_SECONDS = 15.0
MAX_CONTINUATION_SECONDS = 340 / FPS


@dataclass(frozen=True)
class H3Segment:
    index: int
    prompt: str
    narration: str
    duration_seconds: float
    timeline_start_seconds: float
    timeline_end_seconds: float
    continuity: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SegmentPlan:
    skill: str
    source_hash: str
    max_segment_duration_seconds: float
    segments: tuple[H3Segment, ...]
    plan_hash: str

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": PLAN_SCHEMA,
            "skill": self.skill,
            "source_hash": self.source_hash,
            "max_segment_duration_seconds": self.max_segment_duration_seconds,
            "segment_count": self.segment_count,
            "segments": [segment.as_dict() for segment in self.segments],
            "plan_hash": self.plan_hash,
        }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _as_finite_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"分段计划字段 {name} 必须是数字") from error
    if not math.isfinite(result):
        raise ValueError(f"分段计划字段 {name} 必须是有限数字")
    return result


def _h3_delivery_duration(index: int, requested_seconds: float) -> float:
    """Quantize to the exact H3 17n+5 render grid before scheduling."""

    requested_frames = max(1, round(requested_seconds * FPS))
    context_frames = 0 if index == 0 else 22
    render_frames = 5
    while render_frames < requested_frames + context_frames:
        render_frames += 17
    if render_frames > 362:
        raise ValueError(f"第 {index + 1} 段超过 MiniMax H3 的 362 帧渲染窗口")
    return (render_frames - context_frames) / FPS


def _extract_plan_json(raw_text: str) -> str:
    text = str(raw_text or "").replace("\r\n", "\n").strip()
    marker_at = text.rfind(PLAN_MARKER)
    if marker_at < 0:
        raise ValueError(
            f"全息讲解 skill 必须在结果末尾输出 {PLAN_MARKER} 和有效 JSON 分段计划"
        )
    candidate = text[marker_at + len(PLAN_MARKER):].strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, count=1, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```\s*$", "", candidate, count=1)
    if not candidate:
        raise ValueError("分段计划标记后没有 JSON 内容")
    return candidate


def remove_plan_block(raw_text: str) -> str:
    """Keep the human-readable result while hiding the machine plan from H3."""

    text = str(raw_text or "")
    marker_at = text.rfind(PLAN_MARKER)
    return text[:marker_at].rstrip() if marker_at >= 0 else text.strip()


def _parse_plan_payload(payload: Any, skill_name: str) -> SegmentPlan:
    if skill_name != "holographic-explainer":
        raise ValueError("只有 holographic-explainer 可以创建 H3 自动续写分段计划")
    if not isinstance(payload, dict):
        raise ValueError("分段计划 JSON 根节点必须是对象")
    if payload.get("schema") != PLAN_SCHEMA:
        raise ValueError(f"分段计划 schema 必须是 {PLAN_SCHEMA}")
    if payload.get("skill") not in {None, skill_name}:
        raise ValueError("分段计划 skill 与当前节点选择不一致")

    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("分段计划必须包含至少一个 segments 项")
    claimed_count = payload.get("segment_count", len(raw_segments))
    if int(claimed_count) != len(raw_segments):
        raise ValueError("分段计划 segment_count 与 segments 数量不一致")

    max_duration = _as_finite_float(
        payload.get("max_segment_duration_seconds", MAX_FIRST_SEGMENT_SECONDS),
        "max_segment_duration_seconds",
    )
    if not 0 < max_duration <= MAX_FIRST_SEGMENT_SECONDS:
        raise ValueError("max_segment_duration_seconds 必须在 0 到 15 秒之间")

    requested_segments: list[tuple[int, str, str, float, str]] = []
    previous_end = 0.0
    for expected_index, item in enumerate(raw_segments):
        if not isinstance(item, dict):
            raise ValueError(f"第 {expected_index + 1} 段必须是对象")
        try:
            index = int(item.get("index", expected_index))
        except (TypeError, ValueError) as error:
            raise ValueError(f"第 {expected_index + 1} 段 index 无效") from error
        if index != expected_index:
            raise ValueError("分段 index 必须从 0 开始连续递增，不能重复或跳号")
        prompt = str(item.get("prompt") or "").strip()
        narration = str(item.get("narration") or "").strip()
        continuity = str(item.get("continuity") or "").strip()
        if not prompt:
            raise ValueError(f"第 {index + 1} 段缺少完整 H3 prompt")
        if not narration:
            raise ValueError(f"第 {index + 1} 段缺少 narration，无法验证文案覆盖")
        if index and not continuity:
            raise ValueError(f"第 {index + 1} 段缺少 continuity 续写说明")
        duration = _as_finite_float(item.get("duration_seconds"), f"segments[{index}].duration_seconds")
        start = _as_finite_float(item.get("timeline_start_seconds"), f"segments[{index}].timeline_start_seconds")
        end = _as_finite_float(item.get("timeline_end_seconds"), f"segments[{index}].timeline_end_seconds")
        allowed = min(max_duration, MAX_FIRST_SEGMENT_SECONDS if index == 0 else MAX_CONTINUATION_SECONDS)
        if duration <= 0 or duration > allowed + 1e-6:
            limit = f"{allowed:.3f}"
            raise ValueError(f"第 {index + 1} 段时长必须大于 0 且不超过 {limit} 秒")
        if start < -1e-6 or end <= start:
            raise ValueError(f"第 {index + 1} 段时间线无效")
        if not math.isclose(end - start, duration, rel_tol=0.0, abs_tol=1 / FPS + 1e-6):
            raise ValueError(f"第 {index + 1} 段 duration_seconds 与时间线长度不一致")
        if not math.isclose(start, previous_end, rel_tol=0.0, abs_tol=1 / FPS + 1e-6):
            raise ValueError("分段时间线必须从 0 开始连续衔接，不能重叠或留空")
        requested_segments.append((index, prompt, narration, duration, continuity))
        previous_end = end

    # H3 always renders on 17n+5 frames. Preserve the model's requested
    # narration split but move the runtime timeline to the exact frames that
    # will be delivered, avoiding a slowly growing hidden tail mismatch.
    segments: list[H3Segment] = []
    timeline_cursor = 0.0
    for index, prompt, narration, requested_duration, continuity in requested_segments:
        duration = _h3_delivery_duration(index, requested_duration)
        segments.append(H3Segment(
            index, prompt, narration, duration, timeline_cursor, timeline_cursor + duration, continuity
        ))
        timeline_cursor += duration

    normalized = {
        "schema": PLAN_SCHEMA,
        "skill": skill_name,
        "max_segment_duration_seconds": max_duration,
        "segments": [segment.as_dict() for segment in segments],
    }
    plan_hash = hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()
    source_hash = str(payload.get("source_hash") or plan_hash)
    return SegmentPlan(skill_name, source_hash, max_duration, tuple(segments), plan_hash)


def parse_segment_plan(raw_text: str, skill_name: str) -> SegmentPlan:
    try:
        payload = json.loads(_extract_plan_json(raw_text))
    except json.JSONDecodeError as error:
        raise ValueError(f"分段计划 JSON 无法解析：{error}") from error
    return _parse_plan_payload(payload, skill_name)


def parse_serialized_segment_plan(value: str, skill_name: str = "holographic-explainer") -> SegmentPlan:
    try:
        payload = json.loads(str(value or ""))
    except json.JSONDecodeError as error:
        raise ValueError(f"分段提示词 JSON 无法解析：{error}") from error
    return _parse_plan_payload(payload, skill_name)


def serialize_segment_plan(plan: SegmentPlan) -> str:
    return _canonical_json(plan.as_dict())
