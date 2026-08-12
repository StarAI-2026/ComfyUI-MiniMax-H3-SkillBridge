"""Runtime-only MiniMax H3 motion-context transport and conditioning patch."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Any

import torch


H3_CONTEXT_SCHEMA = 1
CONTEXT_FRAME_STEPS = {5: 2, 22: 7, 39: 12}
FRAME_PER_TOKEN = (1, 4, 4, 4, 4)
FPS = 24
AUDIO_LATENT_FPS = 40
FRAME_RESCALE = 5.0 / 3.0
MOTION_FRAME_INDEX = "stariai_h3_motion_context_index"
MOTION_AUDIO_END_FRAME = "stariai_h3_motion_context_audio_end_frame"
CONDITIONING_KEY = "stariai_h3_motion_context_schema"


def pixel_frames_from_latent_t(latent_t: int) -> int:
    if latent_t < 1:
        raise ValueError("MiniMax H3 视频 latent 时间维度必须大于 0")
    return sum(FRAME_PER_TOKEN[index % len(FRAME_PER_TOKEN)] for index in range(latent_t))


def step_offsets(latent_t: int) -> list[int]:
    offsets: list[int] = []
    current = 0
    for index in range(latent_t):
        offsets.append(current)
        current += FRAME_PER_TOKEN[index % len(FRAME_PER_TOKEN)]
    return offsets


def _nested_av_parts(av_latent: dict) -> tuple[torch.Tensor, torch.Tensor]:
    samples = av_latent.get("samples") if isinstance(av_latent, dict) else None
    if hasattr(samples, "unbind"):
        parts = list(samples.unbind())
    elif isinstance(samples, (list, tuple)):
        parts = list(samples)
    else:
        raise ValueError("上下文必须来自 MiniMax H3 的最终 AV sampler latent")
    if len(parts) < 2 or not isinstance(parts[0], torch.Tensor) or not isinstance(parts[1], torch.Tensor):
        raise ValueError("MiniMax H3 AV latent 中缺少视频或音频张量")
    video, audio = parts[0], parts[1]
    if video.ndim == 4:
        video = video.unsqueeze(0)
    if audio.ndim == 3:
        audio = audio.unsqueeze(0)
    if video.ndim != 5 or audio.ndim != 4:
        raise ValueError("MiniMax H3 AV latent 形状不符合 [B,24,T,H,W] / [B,32,2,T]")
    if video.shape[0] < 1 or video.shape[1] != 24 or audio.shape[:3] != (video.shape[0], 32, 2):
        raise ValueError("MiniMax H3 AV latent 通道或批次不匹配")
    return video, audio


def _tensor_sha256(tensor: torch.Tensor) -> str:
    raw = tensor.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def _envelope_sha256(video: torch.Tensor, audio: torch.Tensor, metadata: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(_tensor_sha256(video).encode("ascii"))
    digest.update(_tensor_sha256(audio).encode("ascii"))
    for key in sorted(metadata):
        digest.update(f"{key}={metadata[key]}\n".encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class ContextEnvelope:
    ref: str
    chain_id: str
    source_segment_index: int
    candidate_id: str
    context_frames: int
    sha256: str
    video_tail: torch.Tensor
    audio_tail: torch.Tensor
    metadata: dict[str, Any]


class ContextRegistry:
    """A deliberately process-local registry. It never creates a latent file."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, ContextEnvelope] = {}
        self._chain_refs: dict[str, set[str]] = {}

    def register(
        self,
        chain_id: str,
        source_segment_index: int,
        candidate_id: str,
        av_latent: dict,
        context_frames: int,
    ) -> ContextEnvelope:
        context_frames = int(context_frames)
        if context_frames not in CONTEXT_FRAME_STEPS:
            raise ValueError("H3 上下文帧必须是 5、22 或 39")
        video, audio = _nested_av_parts(av_latent)
        video_steps = CONTEXT_FRAME_STEPS[context_frames]
        if int(video.shape[2]) < video_steps:
            raise ValueError("最终 H3 视频 latent 不足以截取所需上下文")
        audio_steps = round(context_frames / FPS * AUDIO_LATENT_FPS)
        if int(audio.shape[-1]) < audio_steps:
            raise ValueError("最终 H3 音频 latent 不足以截取所需上下文")
        video_tail = video[:1, :, -video_steps:].detach().cpu().contiguous()
        audio_tail = audio[:1, :, :, -audio_steps:].detach().cpu().contiguous()
        total_frames = pixel_frames_from_latent_t(int(video.shape[2]))
        audio_overhang = float(audio.shape[-1]) - FRAME_RESCALE * total_frames
        if not -0.5 < audio_overhang < 0.5:
            audio_overhang = 0.0
        metadata = {
            "schema": H3_CONTEXT_SCHEMA,
            "chain_id": str(chain_id),
            "source_segment_index": int(source_segment_index),
            "candidate_id": str(candidate_id),
            "context_frames": context_frames,
            "source_total_frames": total_frames,
            "audio_overhang": audio_overhang,
            "video_shape": list(video_tail.shape),
            "audio_shape": list(audio_tail.shape),
            "created_unix": time.time(),
        }
        sha256 = _envelope_sha256(video_tail, audio_tail, metadata)
        ref = f"h3ctx://{chain_id}/{int(source_segment_index)}/{candidate_id}/{sha256[:16]}"
        envelope = ContextEnvelope(
            ref, str(chain_id), int(source_segment_index), str(candidate_id), context_frames, sha256,
            video_tail, audio_tail, metadata,
        )
        with self._lock:
            self._items[ref] = envelope
            self._chain_refs.setdefault(str(chain_id), set()).add(ref)
        return envelope

    def resolve(
        self,
        ref: str,
        chain_id: str,
        expected_source_segment_index: int,
        expected_sha256: str = "",
    ) -> ContextEnvelope:
        with self._lock:
            envelope = self._items.get(str(ref))
        if envelope is None:
            raise RuntimeError(
                "H3 内存上下文已不可用（ComfyUI 进程重启、云端迁移或链路被释放）。"
                "该链已进入 detached/recovery_required 状态，不会猜测或扫描 safetensors 文件。"
            )
        if envelope.chain_id != str(chain_id):
            raise ValueError("H3 内存上下文属于另一条链，已拒绝使用")
        if envelope.source_segment_index != int(expected_source_segment_index):
            raise ValueError("H3 内存上下文不是上一段已接受的结果")
        if expected_sha256 and envelope.sha256 != str(expected_sha256):
            raise ValueError("H3 内存上下文 SHA-256 校验失败")
        if _envelope_sha256(envelope.video_tail, envelope.audio_tail, envelope.metadata) != envelope.sha256:
            raise ValueError("H3 内存上下文在进程内校验失败")
        return envelope

    def release_chain(self, chain_id: str) -> None:
        with self._lock:
            for ref in self._chain_refs.pop(str(chain_id), set()):
                self._items.pop(ref, None)

    def status(self, chain_id: str) -> dict[str, Any]:
        with self._lock:
            refs = sorted(self._chain_refs.get(str(chain_id), set()))
        return {
            "context_transport": "memory",
            "file_required": False,
            "available_context_count": len(refs),
            "context_refs": refs,
        }


CONTEXTS = ContextRegistry()


def context_from_envelope(envelope: ContextEnvelope, target_segment_index: int) -> dict[str, Any]:
    return {
        "schema": H3_CONTEXT_SCHEMA,
        "empty": False,
        "video_tail": envelope.video_tail,
        "audio_tail": envelope.audio_tail,
        "metadata": envelope.metadata | {
            "target_segment_index": int(target_segment_index),
            "context_ref": envelope.ref,
            "context_sha256": envelope.sha256,
        },
    }


def empty_context(chain_id: str, target_segment_index: int) -> dict[str, Any]:
    return {
        "schema": H3_CONTEXT_SCHEMA,
        "empty": True,
        "chain_id": str(chain_id),
        "target_segment_index": int(target_segment_index),
    }


def inject_motion_context(conditioning: Any, context: dict[str, Any], frame_count: int) -> Any:
    """Append previous AV tail without destroying Ref2VA references."""

    if context.get("empty"):
        return conditioning
    try:
        import node_helpers
    except ImportError as error:
        raise RuntimeError("ComfyUI node_helpers 不可用，无法注入 H3 motion context") from error
    video = context.get("video_tail")
    audio = context.get("audio_tail")
    metadata = context.get("metadata") or {}
    context_frames = int(metadata.get("context_frames", 0))
    video_steps = CONTEXT_FRAME_STEPS.get(context_frames)
    if not isinstance(video, torch.Tensor) or not isinstance(audio, torch.Tensor) or video_steps is None:
        raise ValueError("H3 motion context 内容无效")
    if int(video.shape[2]) < video_steps:
        raise ValueError("H3 motion context 视频 tail 太短")
    audio_steps = round(context_frames / FPS * AUDIO_LATENT_FPS)
    if int(audio.shape[-1]) < audio_steps:
        raise ValueError("H3 motion context 音频 tail 太短")
    keyframes = [
        {
            "resolved_frame_index": 0,
            MOTION_FRAME_INDEX: offset,
            "latent": video[:, :, index:index + 1].contiguous(),
        }
        for index, offset in enumerate(step_offsets(video_steps))
    ]
    refs = [{
        "kind": "audio",
        "ref_audio_t": audio_steps,
        "audio_latent": audio[:, :, :, -audio_steps:].contiguous(),
        MOTION_AUDIO_END_FRAME: context_frames + float(metadata.get("audio_overhang", 0.0)) / FRAME_RESCALE,
    }]
    merged = []
    for embedding, original in conditioning:
        values = original.copy()
        previous_keyframes = list(values.get("minimax_keyframes") or [])
        previous_refs = list(values.get("minimax_refs") or [])
        values.update({
            CONDITIONING_KEY: H3_CONTEXT_SCHEMA,
            "minimax_keyframes": previous_keyframes + keyframes,
            # Ref2VA references are part of the user workflow. Context audio
            # must append to them, never replace them.
            "minimax_refs": previous_refs + refs,
            "minimax_frame_count": int(frame_count),
        })
        merged.append([embedding, values])
    return merged


def repair_h3_payload(out: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Keep keyframe and Ref2VA latent lists in PackedLayout row order.

    ``ensure_h3_layout_patch`` owns all position edits. Keeping payload repair
    limited to the stock keyframe/ref overwrite makes that ABI surface small
    and lets the layout self-test guard continuation timing independently.
    """

    if int(kwargs.get(CONDITIONING_KEY, 0) or 0) != H3_CONTEXT_SCHEMA:
        return out
    cond = out.get("minimax_payload")
    payload = getattr(cond, "cond", None) if cond is not None else None
    if not isinstance(payload, dict):
        raise RuntimeError("无法访问 MiniMax H3 payload，已停止上下文续写")
    keyframes = list(kwargs.get("minimax_keyframes") or [])
    motion_refs = list(kwargs.get("minimax_refs") or [])
    payload["cond_video_latents"] = [item["latent"] for item in keyframes if "latent" in item] + [
        item["latent"] for item in motion_refs if "latent" in item
    ]
    payload["cond_audio_latents"] = [
        item["audio_latent"] for item in motion_refs if item.get("audio_latent") is not None
    ]
    payload["frame_count"] = int(kwargs.get("minimax_frame_count"))
    return out


def patch_h3_model(model: Any) -> Any:
    from .h3_abi import assert_minimax_h3_model, ensure_h3_layout_patch

    if not hasattr(model, "clone") or not hasattr(model, "add_object_patch"):
        raise ValueError("H3 motion context 需要 ComfyUI MODEL patcher")
    assert_minimax_h3_model(model)
    ensure_h3_layout_patch()
    patched = model.clone()
    original = patched.get_model_object("extra_conds")
    if getattr(original, "_stariai_h3_motion_patch", False):
        return patched

    def _patched_extra_conds(_self: Any, **kwargs: Any) -> dict[str, Any]:
        return repair_h3_payload(original(**kwargs), kwargs)

    _patched_extra_conds._stariai_h3_motion_patch = True
    import types

    patched.add_object_patch("extra_conds", types.MethodType(_patched_extra_conds, patched.model))
    return patched
