import importlib.util
import json
import sys
from pathlib import Path


def load_package():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "minimax_h3_skillbridge_chat_test",
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["minimax_h3_skillbridge_chat_test"] = module
    spec.loader.exec_module(module)
    return module


def test_chat_node_is_registered_and_has_confirmation_outputs():
    module = load_package()
    node = module.NODE_CLASS_MAPPINGS["StariAI-MiniMaxH3-Chat"]
    inputs = node.INPUT_TYPES()

    assert node.OUTPUT_NODE is True
    assert inputs["required"]["run_mode"][0] == ["一次性输出", "多轮对话"]
    assert inputs["required"]["conversation_action"][0] == ["继续对话", "确认并生成", "清空对话"]
    assert node.RETURN_NAMES[2] == "最终提示词"
    assert node.RETURN_TYPES == ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    assert node.RETURN_NAMES == (
        "视觉分析",
        "当前结果",
        "最终提示词",
        "对话历史",
        "运行状态",
        "模型信息",
    )
    assert inputs["optional"]["video_duration"][1]["min"] == 5
    assert inputs["optional"]["video_duration"][1]["max"] == 15
    assert inputs["optional"]["cut_count"][0][-1] == "切镜15"
    assert len([name for name in inputs["optional"] if name.startswith("image_")]) == 6


def test_chat_state_is_bounded_and_confirmation_uses_latest_prompt():
    module = load_package()
    node = module.NODE_CLASS_MAPPINGS["StariAI-MiniMaxH3-Chat"]

    state = node._load_state(json.dumps({
        "turns": [{"user": str(index), "assistant": "answer"} for index in range(20)],
        "last_prompt": "latest prompt",
    }, ensure_ascii=False))

    assert len(state["turns"]) == node.MAX_TURNS
    assert state["turns"][0]["user"] == "8"
    assert node._history_messages(state)[-1] == {"role": "assistant", "content": "answer"}

    state["confirmed"] = True
    state["confirmed_prompt"] = state["last_prompt"]
    assert state["confirmed_prompt"] == "latest prompt"


def test_chat_state_recovers_from_invalid_json():
    module = load_package()
    node = module.NODE_CLASS_MAPPINGS["StariAI-MiniMaxH3-Chat"]

    state = node._load_state("not-json")

    assert state == node._empty_state()


def test_chat_state_contains_shot_plan():
    module = load_package()
    node = module.NODE_CLASS_MAPPINGS["StariAI-MiniMaxH3-Chat"]
    node_module = sys.modules["minimax_h3_skillbridge_chat_test.nodes"]

    assert node._empty_state()["shot_plan"] is None
    shot_plan = node_module.parse_shot_plan(8, "切镜2")
    state = node._load_state(json.dumps({"shot_plan": shot_plan}, ensure_ascii=False))

    assert state["shot_plan"] == shot_plan