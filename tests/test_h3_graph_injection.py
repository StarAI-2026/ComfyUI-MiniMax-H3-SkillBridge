import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
PACKAGE = "skillbridge_h3_graph_test"
spec = importlib.util.spec_from_file_location(
    PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
package = importlib.util.module_from_spec(spec)
sys.modules[PACKAGE] = package
assert spec.loader is not None
spec.loader.exec_module(package)
graph_injection = sys.modules[f"{PACKAGE}.h3_graph_injection"]


def plan_json():
    return json.dumps({
        "schema": "stariai_h3_segment_plan_v1",
        "skill": "holographic-explainer",
        "max_segment_duration_seconds": 15,
        "segment_count": 2,
        "segments": [
            {"index": 0, "prompt": "one", "narration": "one", "duration_seconds": 15, "timeline_start_seconds": 0, "timeline_end_seconds": 15, "continuity": "initial"},
            {"index": 1, "prompt": "two", "narration": "two", "duration_seconds": 14, "timeline_start_seconds": 15, "timeline_end_seconds": 29, "continuity": "continue"},
        ],
    }, ensure_ascii=False)


def graph():
    return {
        "skill": {"class_type": "StariAI-MiniMaxH3-Skill", "inputs": {"skill": "holographic-explainer"}},
        "ref": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {"prompt": ["skill", 1], "length": 124}},
        "guide-a": {"class_type": "BasicGuider", "inputs": {"model": ["model", 0], "conditioning": ["ref", 0]}},
        "guide-b": {"class_type": "BasicGuider", "inputs": {"model": ["model", 0], "conditioning": ["ref", 0]}},
        "sched": {"class_type": "BasicScheduler", "inputs": {"model": ["model", 0]}},
        "sampler-a": {"class_type": "SamplerCustomAdvanced", "inputs": {"guider": ["guide-a", 0], "sigmas": ["sched", 0]}},
        "sampler-final": {"class_type": "SamplerCustomAdvanced", "inputs": {"guider": ["guide-b", 0], "sigmas": ["sched", 0]}},
        "decode-v": {"class_type": "VAEDecode", "inputs": {"samples": ["sampler-final", 0]}},
        "decode-a": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["sampler-final", 0]}},
        "combine": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["decode-v", 0], "audio": ["decode-a", 0]}},
        "model": {"class_type": "DummyModel", "inputs": {}},
    }


def test_injection_uses_final_sampler_and_keeps_canvas_clean():
    injected = graph_injection.inject_h3_chain(graph())
    private = {key: value for key, value in injected.items() if key.startswith("__stariai_h3_chain_")}

    assert len(private) == 6
    terminal = next(value for value in private.values() if value["class_type"] == "StariAIH3SegmentTerminal")
    assert terminal["inputs"]["final_av_latent"] == ["sampler-final", 0]
    combine = injected["combine"]["inputs"]
    assert combine["images"][0].startswith("__stariai_h3_chain_trim_")
    assert combine["audio"][0].startswith("__stariai_h3_chain_trim_")
    assert injected["ref"]["inputs"]["prompt"][0].startswith("__stariai_h3_chain_start_")
    assert injected["__stariai_h3_chain_start_skill"]["inputs"]["start_key"].startswith("skill-node-skill-")


def test_each_manual_injection_receives_a_new_chain_start_key():
    first = graph_injection.inject_h3_chain(graph())
    second = graph_injection.inject_h3_chain(graph())

    first_key = first["__stariai_h3_chain_start_skill"]["inputs"]["start_key"]
    second_key = second["__stariai_h3_chain_start_skill"]["inputs"]["start_key"]

    assert first_key != second_key


def test_injection_refuses_ambiguous_terminal_graph():
    ambiguous = graph()
    ambiguous["combine-2"] = {"class_type": "VHS_VideoCombine", "inputs": {"images": ["decode-v", 0], "audio": ["decode-a", 0]}}
    assert graph_injection.inject_h3_chain(ambiguous) == ambiguous


def test_injection_uses_refined_sampler_when_the_first_pass_is_also_saved():
    dual = graph()
    dual.update({
        "decode-v-first": {"class_type": "VAEDecode", "inputs": {"samples": ["sampler-a", 0]}},
        "decode-a-first": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["sampler-a", 0]}},
        "combine-first": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["decode-v-first", 0], "audio": ["decode-a-first", 0]}},
        "refine-latent": {"class_type": "RefineLatent", "inputs": {"samples": ["sampler-a", 0]}},
    })
    dual["sampler-final"]["inputs"]["latent_image"] = ["refine-latent", 0]

    injected = graph_injection.inject_h3_chain(dual)

    terminal = next(node for node in injected.values() if node["class_type"] == "StariAIH3SegmentTerminal")
    assert terminal["inputs"]["final_av_latent"] == ["sampler-final", 0]


def test_injection_follows_audio_passthrough_to_the_refined_sampler():
    dual = graph()
    dual.update({
        "decode-v-first": {"class_type": "VAEDecode", "inputs": {"samples": ["sampler-a", 0]}},
        "decode-a-first": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["sampler-a", 0]}},
        "combine-first": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["decode-v-first", 0], "audio": ["decode-a-first", 0]}},
        "refine-latent": {"class_type": "RefineLatent", "inputs": {"samples": ["sampler-a", 0]}},
        "audio-passthrough": {"class_type": "ResourceCleaner", "inputs": {"anything": ["decode-a", 0]}},
    })
    dual["sampler-final"]["inputs"]["latent_image"] = ["refine-latent", 0]
    dual["combine"]["inputs"]["audio"] = ["audio-passthrough", 0]

    injected = graph_injection.inject_h3_chain(dual)

    terminal = next(node for node in injected.values() if node["class_type"] == "StariAIH3SegmentTerminal")
    assert terminal["inputs"]["final_av_latent"] == ["sampler-final", 0]

def test_injection_enables_with_chinese_skill_display_name():
    chinese_graph = graph()
    chinese_graph["skill"]["inputs"]["skill"] = "全息讲解"
    injected = graph_injection.inject_h3_chain(chinese_graph)
    private = {key: value for key, value in injected.items() if key.startswith("__stariai_h3_chain_")}
    assert len(private) == 6
