"""Fail-closed ABI patch for MiniMax H3 continuation anchors.

ComfyUI's stock PackedLayout accepts only first/last keyframes. H3 motion
context needs a short run of interior anchors plus an audio reference placed
on the target clip timeline. This module touches only the live layout's time
column, verifies the ABI before installing, and leaves every unmarked H3 graph
unchanged.
"""

from __future__ import annotations

import inspect
import threading
from typing import Any, Iterable

import torch


LAYOUT_PATCH_MARKER = "_stariai_h3_motion_layout_patch_v1"
FRAME_MARKER = "stariai_h3_motion_context_index"
AUDIO_MARKER = "stariai_h3_motion_context_audio_end_frame"

_LOCK = threading.RLock()
_APPLIED = False
_ORIGINAL_INIT = None


def _modules():
    try:
        import comfy.ldm.minimax.model as minimax
        import comfy.model_base as model_base
    except ImportError as error:
        raise RuntimeError("MiniMax H3 ABI is unavailable in this ComfyUI build") from error
    return minimax, model_base


def _expected_ref_kinds(reference: dict[str, Any]) -> tuple[str, ...]:
    kind = reference.get("kind")
    if kind == "image":
        return ("ref_img",)
    if kind == "audio":
        return ("ref_audio",) if int(reference.get("ref_audio_t", 0)) > 0 else ()
    if kind in {"video", "video_audio"}:
        parts: list[str] = []
        if int(reference.get("ref_audio_t", 0)) > 0:
            parts.append("ref_audio")
        parts.append("ref_img")
        return tuple(parts)
    raise RuntimeError(f"Unsupported MiniMax H3 reference kind: {kind!r}")


def _target_origin(layout: Any) -> float:
    try:
        start, stop, kind = layout.segments[-1]
    except (AttributeError, IndexError, ValueError) as error:
        raise RuntimeError("MiniMax H3 PackedLayout has no target video segment") from error
    if kind != "video" or stop <= start:
        raise RuntimeError("MiniMax H3 PackedLayout target video segment changed")
    return float(layout.position_ids[start, 0])


def _reference_segment_map(layout: Any, refs: Iterable[dict[str, Any]]) -> dict[int, dict[str, tuple[int, int]]]:
    references = list(refs or [])
    expected = [(index, kind) for index, reference in enumerate(references) for kind in _expected_ref_kinds(reference)]
    actual = [(start, stop, kind) for start, stop, kind in layout.segments if kind in {"ref_img", "ref_audio"}]
    if len(expected) != len(actual):
        raise RuntimeError(
            "MiniMax H3 reference layout changed: produced reference segment count does not match"
        )
    mapped: dict[int, dict[str, tuple[int, int]]] = {}
    for (index, expected_kind), (start, stop, actual_kind) in zip(expected, actual):
        if expected_kind != actual_kind:
            raise RuntimeError("MiniMax H3 reference layout changed its segment ordering")
        mapped.setdefault(index, {})[actual_kind] = (start, stop)
    return mapped


def _anchor_time(minimax: Any, latent_t: int, frame_count: int | None, index: int, origin: float) -> float:
    if index < 0 or frame_count is None or index >= int(frame_count):
        raise RuntimeError("H3 motion-context keyframe is outside the target frame window")
    if index == 0:
        return origin
    if index == int(frame_count) - 1:
        return origin + sum(minimax._video_t_spans(latent_t)) - minimax.FRAME_RESCALE
    return origin + minimax.FRAME_RESCALE * float(index)


def _repair_layout(layout: Any, keyframes: list[dict[str, Any]] | None, refs: list[dict[str, Any]] | None, frame_count: int | None) -> None:
    minimax, _model_base = _modules()
    keyframes = list(keyframes or [])
    refs = list(refs or [])
    marked_keyframes = [keyframe for keyframe in keyframes if FRAME_MARKER in keyframe]
    marked_audio = [index for index, reference in enumerate(refs) if AUDIO_MARKER in reference]
    if not marked_keyframes and not marked_audio:
        return

    if marked_keyframes:
        cond_spans = [(start, stop) for start, stop, kind in layout.segments if kind == "cond"]
        if len(cond_spans) != len(keyframes):
            raise RuntimeError("MiniMax H3 keyframe/layout cardinality changed")
        origin = _target_origin(layout)
        latent_t = int(layout.signature[1])
        for (start, stop), keyframe in zip(cond_spans, keyframes):
            if FRAME_MARKER not in keyframe:
                if refs:
                    raise RuntimeError(
                        "H3 continuation refuses unmarked keyframes mixed with motion context references"
                    )
                continue
            anchor = _anchor_time(
                minimax, latent_t, frame_count, int(keyframe[FRAME_MARKER]), origin
            )
            layout.position_ids[start:stop, 0] = anchor

    if marked_audio:
        if len(marked_audio) != 1:
            raise RuntimeError("H3 continuation requires exactly one marked motion audio reference")
        reference_index = marked_audio[0]
        reference = refs[reference_index]
        if reference.get("kind") != "audio":
            raise RuntimeError("H3 motion audio marker must be attached to an audio reference")
        audio_steps = int(reference.get("ref_audio_t", 0))
        if audio_steps <= 0:
            raise RuntimeError("H3 motion audio reference has no latent steps")
        span = _reference_segment_map(layout, refs).get(reference_index, {}).get("ref_audio")
        if span is None:
            raise RuntimeError("MiniMax H3 layout has no rows for the motion audio reference")
        start, stop = span
        if stop - start != audio_steps * 2:
            raise RuntimeError("MiniMax H3 audio layout shape changed")
        origin = _target_origin(layout)
        desired_start = (
            origin
            + minimax.FRAME_RESCALE * float(reference[AUDIO_MARKER])
            - float(audio_steps)
        )
        current_start = float(layout.position_ids[start, 0])
        layout.position_ids[start:stop, 0] += desired_start - current_start


def _patched_layout_init(self: Any, text_len: int, latent_t: int, latent_h: int, latent_w: int, audio_t: int, keyframes=None, refs=None, frame_count=None):
    assert _ORIGINAL_INIT is not None
    _ORIGINAL_INIT(
        self, text_len, latent_t, latent_h, latent_w, audio_t,
        keyframes=keyframes, refs=refs, frame_count=frame_count,
    )
    _repair_layout(self, list(keyframes or []), list(refs or []), frame_count)


setattr(_patched_layout_init, LAYOUT_PATCH_MARKER, True)


def _check_unpatched_abi() -> tuple[Any, Any]:
    minimax, model_base = _modules()
    layout_class = getattr(minimax, "PackedLayout", None)
    h3_class = getattr(model_base, "MiniMaxH3", None)
    if layout_class is None or h3_class is None or not hasattr(h3_class, "extra_conds"):
        raise RuntimeError("This ComfyUI build does not expose the MiniMax H3 layout ABI")
    if not all(hasattr(minimax, attribute) for attribute in ("FRAME_PER_TOKEN", "FRAME_RESCALE", "_video_t_spans")):
        raise RuntimeError("This ComfyUI build is missing required MiniMax H3 layout helpers")
    parameters = inspect.signature(layout_class.__init__).parameters
    if not {"keyframes", "refs", "frame_count"}.issubset(parameters):
        raise RuntimeError("MiniMax H3 PackedLayout constructor ABI changed")
    return minimax, layout_class


def _self_test(minimax: Any, layout_class: Any, original_init: Any) -> None:
    text_len, latent_t, latent_h, latent_w, audio_t = 7, 7, 8, 10, 16
    frame_count = sum(minimax.FRAME_PER_TOKEN[index % len(minimax.FRAME_PER_TOKEN)] for index in range(latent_t))

    def build(keyframes=None, refs=None, repair=False):
        layout = layout_class.__new__(layout_class)
        original_init(
            layout, text_len, latent_t, latent_h, latent_w, audio_t,
            keyframes=keyframes, refs=refs, frame_count=frame_count,
        )
        if repair:
            _repair_layout(layout, list(keyframes or []), list(refs or []), frame_count)
        return layout

    stock = build([
        {"resolved_frame_index": 0},
        {"resolved_frame_index": frame_count - 1},
    ])
    marked = build([
        {"resolved_frame_index": 0, FRAME_MARKER: 0},
        {"resolved_frame_index": 0, FRAME_MARKER: frame_count - 1},
    ], repair=True)
    if not torch.equal(stock.position_ids, marked.position_ids):
        raise RuntimeError("H3 layout patch failed the stock endpoint equivalence probe")

    run = build([
        {"resolved_frame_index": 0, FRAME_MARKER: index}
        for index in (0, 1, 5, 9)
    ], [{"kind": "audio", "ref_audio_t": 8, AUDIO_MARKER: 9}], repair=True)
    cond_times = [float(run.position_ids[start, 0]) for start, _stop, kind in run.segments if kind == "cond"]
    if len(cond_times) != 4 or any(left >= right for left, right in zip(cond_times, cond_times[1:])):
        raise RuntimeError("H3 layout patch failed the interior-keyframe ordering probe")
    span = _reference_segment_map(run, [{"kind": "audio", "ref_audio_t": 8, AUDIO_MARKER: 9}])[0]["ref_audio"]
    expected_end = _target_origin(run) + minimax.FRAME_RESCALE * 9
    actual_end = float(run.position_ids[span[0], 0]) + 8
    if abs(actual_end - expected_end) > 1e-9:
        raise RuntimeError("H3 layout patch failed the motion-audio alignment probe")


def ensure_h3_layout_patch() -> None:
    """Install the verified global layout patch once, or fail closed."""

    global _APPLIED, _ORIGINAL_INIT
    with _LOCK:
        if _APPLIED:
            return
        minimax, layout_class = _check_unpatched_abi()
        current = layout_class.__init__
        if getattr(current, LAYOUT_PATCH_MARKER, False):
            _APPLIED = True
            return
        if (
            getattr(current, "__name__", "") != "__init__"
            or hasattr(current, "__wrapped__")
            or getattr(current, "__module__", None) != getattr(layout_class, "__module__", None)
        ):
            raise RuntimeError(
                "Another plugin already patches MiniMax H3 PackedLayout. Disable the conflicting "
                "motion-context patch before using SkillBridge sequential H3 generation."
            )
        _self_test(minimax, layout_class, current)
        _ORIGINAL_INIT = current
        layout_class.__init__ = _patched_layout_init
        _APPLIED = True


def assert_minimax_h3_model(model: Any) -> None:
    """Reject a graph whose MODEL is not the MiniMax H3 AV model."""

    minimax, model_base = _modules()
    patcher_model = getattr(model, "model", None)
    base_model = patcher_model if patcher_model is not None else model
    if not isinstance(base_model, model_base.MiniMaxH3):
        raise ValueError("H3 motion context can only patch a MiniMaxH3 MODEL")
    diffusion_model = getattr(base_model, "diffusion_model", None)
    if not isinstance(diffusion_model, getattr(minimax, "MiniMaxH3Model", ())):
        raise ValueError("The supplied MODEL does not contain the MiniMax H3 AV diffusion model")
