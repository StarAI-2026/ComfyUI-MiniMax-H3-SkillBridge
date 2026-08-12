"""Inject the private SkillBridge H3 chain into a validated existing graph."""

from __future__ import annotations

from copy import deepcopy
import uuid
from typing import Any, Mapping

from .h3_chain_runtime import (
    RUNTIME_PREFIX,
    H3Topology,
    _link,
    _node_inputs,
    _safe_node_id,
    discover_h3_topology,
)

from .skill_catalog import resolve_skill_directory


def _runtime_id(kind: str, skill_node_id: str) -> str:
    return f"{RUNTIME_PREFIX}{kind}_{_safe_node_id(skill_node_id)}"


def _node(class_type: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def _assert_new_id(prompt: Mapping[str, Any], node_id: str) -> None:
    if node_id in prompt:
        raise ValueError(f"SkillBridge 运行时节点 ID 冲突：{node_id}")


def _sequential_enabled(prompt: Mapping[str, Any], skill_node_id: str) -> bool:
    inputs = _node_inputs(prompt, skill_node_id)
    raw = str(inputs.get("skill") or "").strip()
    try:
        return resolve_skill_directory(raw) == "holographic-explainer"
    except ValueError:
        return False


def inject_h3_chain(prompt: Mapping[str, Any], client_id: str | None = None) -> dict[str, Any]:
    """Return an executable graph with only private runtime nodes added.

    The injection deliberately accepts just one proven H3 Ref2VA topology. A
    mismatched graph stays untouched instead of guessing which sampler or mux
    should carry context.
    """

    graph = deepcopy(dict(prompt))
    topology = discover_h3_topology(graph)
    if topology is None:
        return graph
    if not _sequential_enabled(graph, topology.skill_node_id):
        return graph
    if any(str(node_id).startswith(RUNTIME_PREFIX) for node_id in graph):
        return graph

    skill_inputs = _node_inputs(graph, topology.skill_node_id)
    chat_mode = graph[topology.skill_node_id].get("class_type") == "StariAI-MiniMaxH3-Chat"
    if chat_mode and str(skill_inputs.get("conversation_action")) != "确认并生成":
        return graph

    start_id = _runtime_id("start", topology.skill_node_id)
    segment_id = _runtime_id("segment", topology.skill_node_id)
    context_id = _runtime_id("context", topology.skill_node_id)
    trim_id = _runtime_id("trim", topology.skill_node_id)
    terminal_id = _runtime_id("terminal", topology.skill_node_id)
    patch_ids = {
        source_id: _runtime_id(f"model_{_safe_node_id(source_id)}", topology.skill_node_id)
        for source_id in topology.model_source_node_ids
    }
    for node_id in (start_id, segment_id, context_id, trim_id, terminal_id, *patch_ids.values()):
        _assert_new_id(graph, node_id)

    graph[start_id] = _node("StariAIH3ChainStart", {
        "segment_plan_json": _link(topology.skill_node_id, 4 if graph[topology.skill_node_id].get("class_type") == "StariAI-MiniMaxH3-Skill" else 6),
        "skill_node_id": topology.skill_node_id,
        # A user-queued workflow is a new chain. The prompt snapshot retained
        # by that chain preserves this nonce for its later private requeues.
        "start_key": f"skill-node-{topology.skill_node_id}-{uuid.uuid4().hex}",
    })
    graph[segment_id] = _node("StariAIH3SegmentPrompt", {
        "chain_id": _link(start_id, 0),
        "segment_index": 0,
    })
    graph[context_id] = _node("StariAIH3ContextConditioning", {
        "conditioning": _link(topology.reference_node_id, 0),
        "chain_id": _link(start_id, 0),
        "segment_index": _link(segment_id, 3),
        "frame_count": _link(segment_id, 1),
    })
    graph[trim_id] = _node("StariAIH3TrimAV", {
        "images": _link(topology.final_video_decode_node_id, 0),
        "audio": _link(topology.final_audio_decode_node_id, 0),
        "trim_frames": _link(segment_id, 2),
    })
    graph[terminal_id] = _node("StariAIH3SegmentTerminal", {
        "filenames": _link(topology.final_combine_node_id, 0),
        "final_av_latent": _link(topology.final_sampler_node_id, 0),
        "chain_id": _link(start_id, 0),
        "segment_index": _link(segment_id, 3),
    })
    for source_id, patch_id in patch_ids.items():
        graph[patch_id] = _node("StariAIH3PatchModel", {"model": _link(source_id, 0)})

    # The first prompt comes from ChainStart, which validates the plan and
    # registers a chain before Ref2VA begins. Future queued prompts replace
    # the Skill node with PlanReplay, but the Ref2VA link stays stable.
    reference_inputs = _node_inputs(graph, topology.reference_node_id)
    reference_inputs["prompt"] = _link(start_id, 2)
    reference_inputs["length"] = _link(segment_id, 1)

    # Both guider branches must see the exact same continuing conditioning.
    for guider_id in topology.guider_node_ids:
        guider_inputs = _node_inputs(graph, guider_id)
        guider_inputs["conditioning"] = _link(context_id, 0)
        model_source = guider_inputs.get("model")
        if isinstance(model_source, (list, tuple)) and str(model_source[0]) in patch_ids:
            guider_inputs["model"] = _link(patch_ids[str(model_source[0])], 0)
    for scheduler_id in topology.scheduler_node_ids:
        scheduler_inputs = _node_inputs(graph, scheduler_id)
        model_source = scheduler_inputs.get("model")
        if isinstance(model_source, (list, tuple)) and str(model_source[0]) in patch_ids:
            scheduler_inputs["model"] = _link(patch_ids[str(model_source[0])], 0)

    # Replace the final delivery inputs only after the final sampler. The
    # first sampler remains an internal acceleration stage, never a context source.
    combine_inputs = _node_inputs(graph, topology.final_combine_node_id)
    combine_inputs["images"] = _link(trim_id, 0)
    combine_inputs["audio"] = _link(trim_id, 1)

    # The private terminal must execute after video output creation. Connecting
    # VHS_FILENAMES supplies the ordering dependency without exposing a node.
    graph[topology.final_combine_node_id].setdefault("inputs", {})
    return graph
