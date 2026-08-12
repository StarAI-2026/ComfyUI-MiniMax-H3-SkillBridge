"""Private runtime nodes and queue ownership for SkillBridge H3 continuations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import asyncio
import json
import threading
import time
import uuid
from typing import Any, Mapping

import torch

from .h3_motion_context import (
    CONTEXTS,
    FPS,
    context_from_envelope,
    inject_motion_context,
    patch_h3_model,
)
from .h3_delivery import compose_segment_videos, detached_status, write_chain_ledger
from .segment_plan import SegmentPlan, parse_serialized_segment_plan, serialize_segment_plan


RUNTIME_PREFIX = "__stariai_h3_chain_"
RUNTIME_SCHEMA = 1
DEFAULT_CONTEXT_FRAMES = 22
MAX_RENDER_FRAMES = 362


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clean_prompt_snapshot(prompt: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(dict(prompt))
    for node in cleaned.values():
        if isinstance(node, dict):
            node.pop("is_changed", None)
    return cleaned


def _safe_node_id(value: Any) -> str:
    return str(value).replace("/", "_").replace("\\", "_")


def _publish_status(record: "ChainRecord") -> None:
    """Best-effort UI update. Queue correctness never depends on the socket."""

    try:
        _server().send_sync("stariai_h3_chain_status", CHAINS.state(record.chain_id))
    except Exception:
        pass


def _persist_record(record: "ChainRecord") -> None:
    """Persist only delivery metadata; prompts and latent tensors stay in memory."""

    try:
        final_path = str(getattr(record, "final_video_path", "") or "")
        final_hash = str(getattr(record, "final_video_sha256", "") or "")
        write_chain_ledger(
            record.chain_id,
            state=record.state,
            plan_hash=record.plan.plan_hash,
            skill_node_id=record.skill_node_id,
            accepted=record.accepted,
            final_video_path=final_path,
            final_video_sha256=final_hash,
            last_error=record.last_error,
        )
    except Exception as error:
        # A ledger cannot be allowed to invalidate a successfully accepted AV
        # segment. It remains diagnostic only, never a continuation input.
        record.last_error = f"{record.last_error}\nDelivery ledger warning: {error}".strip()


def _link(node_id: str, output_index: int) -> list[Any]:
    return [str(node_id), int(output_index)]


def _is_link(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2


def _node_inputs(prompt: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    node = prompt.get(str(node_id))
    if not isinstance(node, dict):
        raise ValueError(f"运行时节点 {node_id} 不存在")
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError(f"运行时节点 {node_id} inputs 无效")
    return inputs


def _source_node_id(value: Any) -> str | None:
    return str(value[0]) if _is_link(value) else None


def _find_consumers(prompt: Mapping[str, Any], source_node: str, source_output: int | None = None) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for name, value in inputs.items():
            if _is_link(value) and str(value[0]) == str(source_node) and (source_output is None or int(value[1]) == source_output):
                found.append((str(node_id), str(name)))
    return found


def _upstream_nodes(prompt: Mapping[str, Any], start_node: str) -> set[str]:
    seen: set[str] = set()
    pending = [str(start_node)]
    while pending:
        node_id = pending.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = prompt.get(node_id)
        if not isinstance(node, dict):
            continue
        for value in (node.get("inputs") or {}).values():
            source = _source_node_id(value)
            if source is not None:
                pending.append(source)
    return seen


def _nearest_upstream_nodes(
    prompt: Mapping[str, Any], start_node: str, class_types: set[str]
) -> list[str]:
    """Return closest upstream nodes of the requested types.

    Final AV branches may cross ordinary pass-through or resource-cleanup
    nodes before they reach VHS_VideoCombine. Following the graph rather than
    requiring a direct link keeps final-sampler selection structural.
    """

    pending: list[tuple[str, int]] = [(str(start_node), 0)]
    visited: set[str] = set()
    closest_distance: int | None = None
    found: list[str] = []
    cursor = 0
    while cursor < len(pending):
        node_id, distance = pending[cursor]
        cursor += 1
        if node_id in visited:
            continue
        visited.add(node_id)
        if closest_distance is not None and distance > closest_distance:
            continue
        node = prompt.get(node_id)
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in class_types:
            closest_distance = distance
            found.append(node_id)
            continue
        for value in (node.get("inputs") or {}).values():
            source = _source_node_id(value)
            if source is not None:
                pending.append((source, distance + 1))
    return sorted(set(found))


@dataclass(frozen=True)
class H3Topology:
    skill_node_id: str
    reference_node_id: str
    final_sampler_node_id: str
    final_video_decode_node_id: str
    final_audio_decode_node_id: str
    final_combine_node_id: str
    guider_node_ids: tuple[str, ...]
    scheduler_node_ids: tuple[str, ...]
    model_source_node_ids: tuple[str, ...]


def discover_h3_topology(prompt: Mapping[str, Any]) -> H3Topology | None:
    skill_nodes = [
        str(node_id) for node_id, node in prompt.items()
        if isinstance(node, dict) and node.get("class_type") in {"StariAI-MiniMaxH3-Skill", "StariAI-MiniMaxH3-Chat"}
    ]
    reference_nodes = [
        str(node_id) for node_id, node in prompt.items()
        if isinstance(node, dict) and node.get("class_type") == "MiniMaxH3ReferenceToVideo"
    ]
    if len(skill_nodes) != 1 or len(reference_nodes) != 1:
        return None
    skill_id, reference_id = skill_nodes[0], reference_nodes[0]
    ref_consumers = _find_consumers(prompt, reference_id, 0)
    guider_ids = tuple(sorted(node_id for node_id, input_name in ref_consumers if input_name == "conditioning" and prompt[node_id].get("class_type") == "BasicGuider"))
    if not guider_ids:
        return None
    sampler_ids: list[str] = []
    for guider_id in guider_ids:
        sampler_ids.extend(
            node_id for node_id, name in _find_consumers(prompt, guider_id, 0)
            if name == "guider" and prompt[node_id].get("class_type") == "SamplerCustomAdvanced"
        )
    sampler_ids = sorted(set(sampler_ids))
    if not sampler_ids:
        return None
    terminal_candidates: list[tuple[str, str, str, str]] = []
    for combine_id, combine_node in prompt.items():
        if not isinstance(combine_node, dict) or combine_node.get("class_type") != "VHS_VideoCombine":
            continue
        combine_inputs = _node_inputs(prompt, str(combine_id))
        image_source = _source_node_id(combine_inputs.get("images"))
        audio_source = _source_node_id(combine_inputs.get("audio"))
        if image_source is None or audio_source is None:
            continue
        video_decodes = _nearest_upstream_nodes(prompt, image_source, {"VAEDecode"})
        audio_decodes = _nearest_upstream_nodes(prompt, audio_source, {"VAEDecodeAudio"})
        video_samplers = _nearest_upstream_nodes(prompt, image_source, {"SamplerCustomAdvanced"})
        audio_samplers = _nearest_upstream_nodes(prompt, audio_source, {"SamplerCustomAdvanced"})
        if (
            len(video_decodes) == 1
            and len(audio_decodes) == 1
            and len(video_samplers) == 1
            and video_samplers == audio_samplers
            and video_samplers[0] in sampler_ids
        ):
            terminal_candidates.append((video_samplers[0], video_decodes[0], audio_decodes[0], str(combine_id)))
    if len(terminal_candidates) == 1:
        final_sampler, video_decode, audio_decode, combine = terminal_candidates[0]
    else:
        # Dual-sampling H3 workflows often retain an MP4 from the first pass
        # for preview, then encode a second MP4 after the refinement pass.
        # Context must come from the sampler that is downstream of another H3
        # sampler, never merely the first candidate encountered in the graph.
        sampler_set = set(sampler_ids)
        refined_candidates = [
            candidate for candidate in terminal_candidates
            if (_upstream_nodes(prompt, candidate[0]) - {candidate[0]}) & sampler_set
        ]
        if len(refined_candidates) != 1:
            return None
        final_sampler, video_decode, audio_decode, combine = refined_candidates[0]
    model_sources: set[str] = set()
    scheduler_ids: set[str] = set()
    for guider_id in guider_ids:
        inputs = _node_inputs(prompt, guider_id)
        source = _source_node_id(inputs.get("model"))
        if source:
            model_sources.add(source)
    for sampler_id in sampler_ids:
        sigmas = _source_node_id(_node_inputs(prompt, sampler_id).get("sigmas"))
        if sigmas and prompt.get(sigmas, {}).get("class_type") == "BasicScheduler":
            scheduler_ids.add(sigmas)
            source = _source_node_id(_node_inputs(prompt, sigmas).get("model"))
            if source:
                model_sources.add(source)
    return H3Topology(
        skill_id, reference_id, final_sampler, video_decode, audio_decode, combine, guider_ids,
        tuple(sorted(scheduler_ids)), tuple(sorted(model_sources)),
    )


@dataclass
class ChainRecord:
    chain_id: str
    start_key: str
    plan: SegmentPlan
    skill_node_id: str
    created_unix: float
    state: str = "planned"
    current_segment_index: int = 0
    prompt_snapshot: dict[str, Any] | None = None
    client_id: str | None = None
    prompt_id: str = ""
    accepted: list[dict[str, Any]] = field(default_factory=list)
    pause_requested: bool = False
    cancel_requested: bool = False
    last_error: str = ""
    final_video_path: str = ""
    final_video_sha256: str = ""


class H3ChainRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._chains: dict[str, ChainRecord] = {}
        self._start_keys: dict[str, str] = {}

    def create(self, plan: SegmentPlan, skill_node_id: str, prompt_snapshot: dict[str, Any], client_id: str | None, start_key: str) -> ChainRecord:
        with self._lock:
            chain_id = f"skillbridge-{uuid.uuid4().hex}"
            record = ChainRecord(chain_id, str(start_key), plan, str(skill_node_id), time.time(), prompt_snapshot=prompt_snapshot, client_id=client_id)
            self._chains[chain_id] = record
            self._start_keys[str(start_key)] = chain_id
            return record

    def get_or_create(
        self, start_key: str, plan: SegmentPlan, skill_node_id: str, prompt_snapshot: dict[str, Any], client_id: str | None
    ) -> ChainRecord:
        with self._lock:
            existing_id = self._start_keys.get(str(start_key))
            if existing_id:
                record = self._chains.get(existing_id)
                if record is None:
                    raise RuntimeError("H3 链索引损坏，无法恢复内存上下文")
                if record.plan.plan_hash != plan.plan_hash:
                    raise RuntimeError("H3 分段计划已改变；请重新提交新的工作流，不能混用上下文")
                return record
        return self.create(plan, skill_node_id, prompt_snapshot, client_id, start_key)

    def get(self, chain_id: str) -> ChainRecord:
        with self._lock:
            record = self._chains.get(str(chain_id))
            if record is None:
                raise ValueError("H3 自动续写链不存在，或已在进程重启后失效")
            return record

    def status_or_detached(self, chain_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._chains.get(str(chain_id))
            if record is not None:
                return self.state(record.chain_id)
        recovered = detached_status(str(chain_id))
        if recovered is not None:
            return recovered
        raise ValueError("H3 自动续写链不存在，或已在进程重启后失效")

    def state(self, chain_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.get(chain_id)
            return {
                "schema": RUNTIME_SCHEMA,
                "chain_id": record.chain_id,
                "skill_node_id": record.skill_node_id,
                "state": record.state,
                "segment_count": record.plan.segment_count,
                "accepted_count": len(record.accepted),
                "current_segment_index": record.current_segment_index,
                "plan_hash": record.plan.plan_hash,
                "context_transport": "memory",
                "file_required": False,
                "recovery_policy": "detached_on_process_loss",
                "final_video_path": record.final_video_path,
                "last_error": record.last_error,
            }

    def mark_detached(self, chain_id: str, message: str) -> None:
        with self._lock:
            record = self.get(chain_id)
            record.state = "detached"
            record.last_error = str(message)
            _persist_record(record)
            _publish_status(record)

    def pause(self, chain_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.get(chain_id)
            if record.state in {"completed", "cancelled", "detached", "failed"}:
                raise ValueError(f"当前链状态为 {record.state}，无法暂停")
            record.pause_requested = True
            record.state = "pausing"
            _persist_record(record)
            _publish_status(record)
            return self.state(chain_id)

    def resume(self, chain_id: str) -> ChainRecord:
        with self._lock:
            record = self.get(chain_id)
            if record.state != "paused":
                raise ValueError("只有已暂停链可以继续")
            if record.prompt_snapshot is None:
                record.state = "detached"
                raise RuntimeError("续写 prompt 快照已失效，链需要恢复，不能猜测上下文")
            record.pause_requested = False
            record.cancel_requested = False
            record.state = "scheduling"
            _persist_record(record)
            _publish_status(record)
            return record

    def cancel(self, chain_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.get(chain_id)
            record.cancel_requested = True
            record.state = "cancelled"
            CONTEXTS.release_chain(record.chain_id)
            _persist_record(record)
            _publish_status(record)
            return self.state(chain_id)


CHAINS = H3ChainRegistry()


class StariAIH3ChainStart:
    CATEGORY = "StariAI-MiniMaxH3-Skill/internal"
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("chain_id", "chain_status", "segment_prompt")
    FUNCTION = "start"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "segment_plan_json": ("STRING",),
                "skill_node_id": ("STRING",),
                "start_key": ("STRING",),
            },
            "hidden": {"prompt": "PROMPT"},
        }

    def start(self, segment_plan_json: str, skill_node_id: str, start_key: str, prompt=None):
        plan = parse_serialized_segment_plan(segment_plan_json)
        if not isinstance(prompt, Mapping):
            raise RuntimeError("ComfyUI 没有提供可复用 prompt 快照，无法安全续写")
        from server import PromptServer
        client_id = getattr(getattr(PromptServer, "instance", None), "client_id", None)
        record = CHAINS.get_or_create(
            str(start_key), plan, str(skill_node_id), _clean_prompt_snapshot(prompt),
            str(client_id) if client_id else None,
        )
        try:
            from comfy_execution.utils import get_executing_context

            execution_context = get_executing_context()
            if execution_context is not None and execution_context.prompt_id:
                record.prompt_id = str(execution_context.prompt_id)
        except Exception:
            # The context is only needed for optional pause/cancel controls.
            # Do not make a valid one-shot generation depend on it.
            pass
        if record.state == "planned":
            record.state = "running"
        _persist_record(record)
        _publish_status(record)
        return record.chain_id, _json(CHAINS.state(record.chain_id)), record.plan.segments[0].prompt


class StariAIH3PlanReplay:
    """Replays the active segment without making another cloud request."""

    CATEGORY = "StariAI-MiniMaxH3-Skill/internal"
    RETURN_TYPES = ("STRING",) * 7
    RETURN_NAMES = (
        "analysis", "current_result", "final_prompt", "history",
        "status", "model_info", "segment_plan_json",
    )
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"chain_id": ("STRING",), "segment_index": ("INT",)}}

    def run(self, chain_id: str, segment_index: int):
        record = CHAINS.get(chain_id)
        index = int(segment_index)
        if index != record.current_segment_index:
            raise RuntimeError("H3 提示词回放段次与当前链状态不一致")
        prompt = record.plan.segments[index].prompt
        status = _json(CHAINS.state(chain_id))
        return "", prompt, prompt, "", status, _json({"mode": "h3_chain_replay"}), serialize_segment_plan(record.plan)


class StariAIH3SegmentPrompt:
    CATEGORY = "StariAI-MiniMaxH3-Skill/internal"
    RETURN_TYPES = ("STRING", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("prompt", "render_frames", "trim_frames", "segment_index", "chain_status")
    FUNCTION = "resolve"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"chain_id": ("STRING",), "segment_index": ("INT",)}}

    def resolve(self, chain_id: str, segment_index: int):
        record = CHAINS.get(chain_id)
        index = int(segment_index)
        if index != record.current_segment_index or index >= record.plan.segment_count:
            raise RuntimeError("H3 分段请求与当前链状态不一致，拒绝跳段")
        segment = record.plan.segments[index]
        trim_frames = 0 if index == 0 else DEFAULT_CONTEXT_FRAMES
        if index and segment.duration_seconds > (MAX_RENDER_FRAMES - trim_frames) / FPS + 1e-6:
            raise RuntimeError("续写片段超过 H3 22 帧上下文的 14.167 秒交付上限")
        requested = max(1, round(segment.duration_seconds * FPS)) + trim_frames
        render_frames = 5
        while render_frames < requested:
            render_frames += 17
        if render_frames > MAX_RENDER_FRAMES:
            raise RuntimeError("H3 续写渲染窗口超过 362 帧上限")
        status = CHAINS.state(chain_id) | {
            "render_frames": render_frames,
            "trim_frames": trim_frames,
            "segment_duration_seconds": segment.duration_seconds,
        }
        _publish_status(record)
        return segment.prompt, render_frames, trim_frames, index, _json(status)


class StariAIH3ContextConditioning:
    CATEGORY = "StariAI-MiniMaxH3-Skill/internal"
    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "conditioning": ("CONDITIONING",),
            "chain_id": ("STRING",),
            "segment_index": ("INT",),
            "frame_count": ("INT",),
        }}

    def apply(self, conditioning: Any, chain_id: str, segment_index: int, frame_count: int):
        index = int(segment_index)
        if index == 0:
            return (conditioning,)
        record = CHAINS.get(chain_id)
        if len(record.accepted) != index:
            raise RuntimeError("上一段尚未被接受，不能为下一段生成 H3 上下文")
        parent = record.accepted[-1]
        try:
            envelope = CONTEXTS.resolve(
                parent["context_ref"], chain_id, index - 1, parent["context_sha256"],
            )
        except RuntimeError as error:
            CHAINS.mark_detached(chain_id, str(error))
            raise
        return (inject_motion_context(conditioning, context_from_envelope(envelope, index), int(frame_count)),)


class StariAIH3PatchModel:
    CATEGORY = "StariAI-MiniMaxH3-Skill/internal"
    RETURN_TYPES = ("MODEL",)
    FUNCTION = "patch"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",)}}

    def patch(self, model: Any):
        return (patch_h3_model(model),)


class StariAIH3TrimAV:
    CATEGORY = "StariAI-MiniMaxH3-Skill/internal"
    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("images", "audio")
    FUNCTION = "trim"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "audio": ("AUDIO",),
            "trim_frames": ("INT",),
        }}

    def trim(self, images: torch.Tensor, audio: dict[str, Any], trim_frames: int):
        trim = max(0, int(trim_frames))
        if images.ndim != 4 or trim >= int(images.shape[0]):
            raise ValueError("H3 上下文裁切会清空视频帧，已拒绝")
        out_images = images[trim:] if trim else images
        waveform = audio.get("waveform") if isinstance(audio, dict) else None
        sample_rate = int(audio.get("sample_rate", 0)) if isinstance(audio, dict) else 0
        if not isinstance(waveform, torch.Tensor) or sample_rate <= 0:
            raise ValueError("H3 解码音频无效，无法与视频同步裁切")
        cut_samples = round(trim * sample_rate / FPS)
        if cut_samples >= int(waveform.shape[-1]):
            raise ValueError("H3 上下文裁切会清空音频，已拒绝")
        trimmed = waveform[..., cut_samples:]
        wanted = round(int(out_images.shape[0]) * sample_rate / FPS)
        if int(trimmed.shape[-1]) > wanted:
            trimmed = trimmed[..., :wanted]
        elif int(trimmed.shape[-1]) < wanted:
            trimmed = torch.nn.functional.pad(trimmed, (0, wanted - int(trimmed.shape[-1])))
        return out_images, {"waveform": trimmed.contiguous(), "sample_rate": sample_rate}


class StariAIH3SegmentTerminal:
    CATEGORY = "StariAI-MiniMaxH3-Skill/internal"
    RETURN_TYPES = ("VHS_FILENAMES", "STRING")
    RETURN_NAMES = ("filenames", "chain_status")
    OUTPUT_NODE = True
    FUNCTION = "complete"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "filenames": ("VHS_FILENAMES",),
            "final_av_latent": ("LATENT",),
            "chain_id": ("STRING",),
            "segment_index": ("INT",),
        }}

    def complete(self, filenames: Any, final_av_latent: dict, chain_id: str, segment_index: int):
        index = int(segment_index)
        record = CHAINS.get(chain_id)
        if record.cancel_requested:
            _persist_record(record)
            _publish_status(record)
            return filenames, _json(CHAINS.state(chain_id))
        if index != record.current_segment_index:
            raise RuntimeError("H3 终点段次与链状态不一致，拒绝推进")
        outputs = filenames[1] if isinstance(filenames, (tuple, list)) and len(filenames) > 1 else []
        if not outputs:
            raise RuntimeError("视频合并节点没有产出文件，不能推进下一段")
        item = {"segment_index": index, "video_path": str(outputs[-1])}
        if index < record.plan.segment_count - 1:
            candidate_id = f"segment-{index}-{uuid.uuid4().hex[:12]}"
            envelope = CONTEXTS.register(chain_id, index, candidate_id, final_av_latent, DEFAULT_CONTEXT_FRAMES)
            item.update({
                "candidate_id": candidate_id,
                "context_transport": "memory",
                "context_ref": envelope.ref,
                "context_sha256": envelope.sha256,
                "file_required": False,
            })
        record.accepted.append(item)
        if index == record.plan.segment_count - 1:
            record.state = "composing"
            record.current_segment_index = index
            _persist_record(record)
            _publish_status(record)
            try:
                final_path, report = compose_segment_videos(chain_id, record.accepted)
                record.final_video_path = final_path
                record.final_video_sha256 = str(report["output_sha256"])
                # Composition is synchronous and can overlap a UI cancel request.
                # Keep cancellation authoritative rather than resurrecting the chain
                # as completed after its final MP4 has already finished encoding.
                if record.cancel_requested or record.state == "cancelled":
                    record.state = "cancelled"
                else:
                    record.state = "completed"
                    record.last_error = ""
            except Exception as error:
                record.state = "failed"
                record.last_error = f"H3 final MP4 composition failed: {error}"
                _persist_record(record)
                _publish_status(record)
                raise
            finally:
                CONTEXTS.release_chain(chain_id)
            _persist_record(record)
            _publish_status(record)
            return filenames, _json(CHAINS.state(chain_id))
        record.current_segment_index = index + 1
        if record.pause_requested:
            record.state = "paused"
            _persist_record(record)
            _publish_status(record)
            return filenames, _json(CHAINS.state(chain_id))
        record.state = "scheduling"
        _persist_record(record)
        _publish_status(record)
        try:
            prompt_id = _queue_continuation(record)
            record.prompt_id = prompt_id
            record.state = "running"
        except Exception as error:
            record.state = "failed"
            record.last_error = str(error)
            _persist_record(record)
            _publish_status(record)
            raise
        _persist_record(record)
        _publish_status(record)
        return filenames, _json(CHAINS.state(chain_id))


NODE_CLASS_MAPPINGS = {
    "StariAIH3ChainStart": StariAIH3ChainStart,
    "StariAIH3PlanReplay": StariAIH3PlanReplay,
    "StariAIH3SegmentPrompt": StariAIH3SegmentPrompt,
    "StariAIH3ContextConditioning": StariAIH3ContextConditioning,
    "StariAIH3PatchModel": StariAIH3PatchModel,
    "StariAIH3TrimAV": StariAIH3TrimAV,
    "StariAIH3SegmentTerminal": StariAIH3SegmentTerminal,
}
NODE_DISPLAY_NAME_MAPPINGS = {name: name for name in NODE_CLASS_MAPPINGS}


def _server():
    from server import PromptServer

    instance = getattr(PromptServer, "instance", None)
    if instance is None:
        raise RuntimeError("ComfyUI PromptServer 尚未就绪")
    return instance


def _cancel_prompt(prompt_id: str) -> dict[str, Any]:
    """Remove or interrupt exactly one chain prompt, never the whole queue."""

    if not prompt_id:
        return {
            "prompt_id": "",
            "deleted_from_queue": False,
            "interrupt_signalled": False,
        }
    queue = _server().prompt_queue
    deleted = queue.delete_queue_item(lambda item: str(item[1]) == str(prompt_id))
    interrupted = False if deleted else queue.interrupt_if_running(str(prompt_id))
    return {
        "prompt_id": str(prompt_id),
        "deleted_from_queue": bool(deleted),
        "interrupt_signalled": bool(interrupted),
    }


def _prompt_location(prompt_id: str) -> str:
    if not prompt_id:
        return "missing"
    queue = _server().prompt_queue
    running, queued = queue.get_current_queue()
    if any(str(item[1]) == str(prompt_id) for item in running):
        return "running"
    if any(str(item[1]) == str(prompt_id) for item in queued):
        return "queued"
    return "missing"


def control_pause_chain(chain_id: str) -> dict[str, Any]:
    record = CHAINS.get(chain_id)
    CHAINS.pause(chain_id)
    try:
        location = _prompt_location(record.prompt_id)
        result = _cancel_prompt(record.prompt_id) if location == "queued" else {
            "prompt_id": record.prompt_id,
            "deleted_from_queue": False,
            "interrupt_signalled": False,
        }
    except Exception as error:
        record.last_error = f"Pause requested; targeted queue control failed: {error}"
        _persist_record(record)
        _publish_status(record)
        raise
    if result["deleted_from_queue"]:
        record.prompt_id = ""
        record.state = "paused"
        record.last_error = ""
    elif location == "missing" and record.state == "pausing":
        # The prior segment has already accepted and no continuation is
        # outstanding. Resume can safely queue the saved next index.
        record.state = "paused"
    _persist_record(record)
    _publish_status(record)
    return CHAINS.state(chain_id) | {"last_control_result": result, "runtime_location": location}


def control_cancel_chain(chain_id: str) -> dict[str, Any]:
    record = CHAINS.get(chain_id)
    prompt_id = record.prompt_id
    status = CHAINS.cancel(chain_id)
    try:
        result = _cancel_prompt(prompt_id)
    except Exception as error:
        record.last_error = f"Cancelled in-memory chain; targeted queue control failed: {error}"
        _persist_record(record)
        _publish_status(record)
        raise
    record.prompt_id = ""
    _persist_record(record)
    _publish_status(record)
    return status | {"last_control_result": result}


def _queue_continuation(record: ChainRecord) -> str:
    if record.prompt_snapshot is None:
        raise RuntimeError("内存 prompt 快照已丢失，链需要恢复")
    server = _server()
    prompt = _clean_prompt_snapshot(record.prompt_snapshot)
    segment_id = f"{RUNTIME_PREFIX}segment_{_safe_node_id(record.skill_node_id)}"
    if segment_id not in prompt:
        raise RuntimeError("续写 prompt 缺少私有段控制节点")
    prompt[segment_id]["inputs"]["segment_index"] = int(record.current_segment_index)
    prompt[record.skill_node_id] = {
        "class_type": "StariAIH3PlanReplay",
        "inputs": {"chain_id": record.chain_id, "segment_index": int(record.current_segment_index)},
    }
    reference_id = None
    for node_id, node in prompt.items():
        if isinstance(node, dict) and node.get("class_type") == "MiniMaxH3ReferenceToVideo":
            reference_id = str(node_id)
            break
    if reference_id is None:
        raise RuntimeError("续写 prompt 缺少 MiniMaxH3ReferenceToVideo")
    prompt[reference_id]["inputs"]["prompt"] = [record.skill_node_id, 2]
    start_id = f"{RUNTIME_PREFIX}start_{_safe_node_id(record.skill_node_id)}"
    if start_id in prompt:
        prompt[start_id]["inputs"]["segment_plan_json"] = serialize_segment_plan(record.plan)

    async def enqueue() -> str:
        import execution

        prompt_id = str(uuid.uuid4())
        data: dict[str, Any] = {"prompt": prompt}
        if record.client_id:
            data["client_id"] = record.client_id
        data = server.trigger_on_prompt(data)
        prompt_copy = deepcopy(dict(data["prompt"]))
        server.node_replace_manager.apply_replacements(prompt_copy)
        valid = await execution.validate_prompt(prompt_id, prompt_copy, None)
        if not valid[0]:
            raise RuntimeError(f"下一段 H3 prompt 验证失败：{valid[1]}")
        number = server.number
        server.number += 1
        extra = {"create_time": int(time.time() * 1000)}
        if record.client_id:
            extra["client_id"] = record.client_id
        server.prompt_queue.put((number, prompt_id, prompt_copy, extra, valid[2], {}))
        return prompt_id

    future = asyncio.run_coroutine_threadsafe(enqueue(), server.loop)
    try:
        return future.result(timeout=60.0)
    except TimeoutError as error:
        future.cancel()
        raise RuntimeError("下一段 H3 prompt 验证或排队超时") from error


def queue_resumed_chain(chain_id: str) -> dict[str, Any]:
    record = CHAINS.resume(chain_id)
    try:
        record.prompt_id = _queue_continuation(record)
        record.state = "running"
        record.last_error = ""
    except Exception as error:
        record.state = "failed"
        record.last_error = f"恢复 H3 续写失败: {error}"
        _persist_record(record)
        _publish_status(record)
        raise
    _persist_record(record)
    _publish_status(record)
    return CHAINS.state(chain_id)
