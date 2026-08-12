import importlib.util
import sys
from pathlib import Path


def load_package():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "minimax_h3_skillbridge_test", root / "__init__.py", submodule_search_locations=[str(root)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["minimax_h3_skillbridge_test"] = module
    spec.loader.exec_module(module)
    return module


def test_node_is_cloud_only():
    module = load_package()
    node = module.NODE_CLASS_MAPPINGS["StariAI-MiniMaxH3-Skill"]
    inputs = node.INPUT_TYPES()
    required = inputs["required"]
    assert "api_base" in required
    assert "model" in required
    # api_key 是节点内置的一次性输入（前端 JS 设 serialize=false 不落工作流）
    assert "api_key" in required
    assert "run_mode" not in required
    assert "local_model" not in required
    assert "quantization" not in required
    assert "attention_mode" not in required
    assert "download_if_missing" not in required
    for field in ("temperature", "top_p", "max_tokens", "repetition_penalty"):
        assert field not in required
    for field in ("video_frame_count", "video_sample_interval", "max_image_side", "proxy_url", "timeout"):
        assert field not in inputs["optional"]
    assert len([name for name in inputs["optional"] if name.startswith("image_")]) == 6
    assert node.RETURN_TYPES[:5] == ("STRING", "STRING", "STRING", "STRING", "STRING")
    assert node.RETURN_TYPES[5:] == tuple(["*"] * 8)
    assert node.RETURN_NAMES[:5] == ("视觉分析", "最终提示词", "运行状态", "模型信息", "分段提示词JSON")
    assert node.RETURN_NAMES[5:] == tuple(f"clone_{index}" for index in range(8))
    assert "clone_functions" in inputs["optional"]
    assert "clone_0" not in inputs["optional"]
    assert inputs["optional"]["video_duration"][1]["min"] == 5
    assert inputs["optional"]["video_duration"][1]["max"] == 15
    assert inputs["optional"]["cut_count"][0][0:3] == ["不切镜", "自动", "切镜1"]
    assert inputs["optional"]["cut_count"][0][-1] == "切镜15"


def test_shot_plan_options():
    module = load_package()
    node_module = sys.modules["minimax_h3_skillbridge_test.nodes"]

    assert node_module.parse_shot_plan(10, "不切镜") == {
        "duration_seconds": 10,
        "cut_mode": "none",
        "cut_count": 0,
        "shot_count": 1,
        "selection": "不切镜",
    }
    assert node_module.parse_shot_plan(10, "自动")["cut_mode"] == "auto"
    assert node_module.parse_shot_plan(10, "切镜3")["cut_count"] == 3
    assert node_module.parse_shot_plan(10, "切镜3")["shot_count"] == 4


def test_shot_plan_rejects_invalid_values():
    module = load_package()
    node_module = sys.modules["minimax_h3_skillbridge_test.nodes"]

    for duration in (4, 16):
        try:
            node_module.parse_shot_plan(duration, "自动")
        except ValueError:
            pass
        else:
            raise AssertionError("无效视频时长未被拒绝")

    try:
        node_module.parse_shot_plan(10, "切镜16")
    except ValueError:
        pass
    else:
        raise AssertionError("超过 15 次切镜未被拒绝")


def test_skill_includes_shot_plan_in_system_prompt(monkeypatch):
    module = load_package()
    node_module = sys.modules["minimax_h3_skillbridge_test.nodes"]
    node = module.NODE_CLASS_MAPPINGS["StariAI-MiniMaxH3-Skill"]
    captured = {}

    monkeypatch.setattr(node_module, "collect_images", lambda *args, **kwargs: [])
    monkeypatch.setattr(node_module, "collect_video_frames", lambda *args, **kwargs: [])
    monkeypatch.setattr(node_module, "load_skill", lambda skill: (skill, "skill rules"))

    def fake_chat(*args, **kwargs):
        captured["system"] = args[2]
        return "[视觉分析]\n分析\n[最终视频提示词]\n提示词"

    monkeypatch.setattr(node_module, "chat_cloud", fake_chat)

    node().run(
        skill="h3-prompt-writing",
        user_prompt="生成提示词",
        api_base="https://example.test/v1",
        model="test-model",
        api_key="test-key",
        video_duration=12,
        cut_count="切镜3",
    )

    assert "严格为 12 秒" in captured["system"]
    assert "恰好发生 3 次镜头切换" in captured["system"]
    assert "生成 4 个连续镜头段" in captured["system"]


def test_skill_injects_cloned_function_into_system_and_outputs(monkeypatch):
    module = load_package()
    node_module = sys.modules["minimax_h3_skillbridge_test.nodes"]
    node = module.NODE_CLASS_MAPPINGS["StariAI-MiniMaxH3-Skill"]
    captured = {}

    monkeypatch.setattr(node_module, "collect_images", lambda *args, **kwargs: [])
    monkeypatch.setattr(node_module, "collect_video_frames", lambda *args, **kwargs: [])
    monkeypatch.setattr(node_module, "load_skill", lambda skill: (skill, "skill rules"))

    def fake_chat(*args, **kwargs):
        captured["system"] = args[2]
        return "[视觉分析]\n分析\n[最终视频提示词]\n提示词"

    monkeypatch.setattr(node_module, "chat_cloud", fake_chat)

    result = node().run(
        skill="h3-prompt-writing",
        user_prompt="生成提示词",
        api_base="https://example.test/v1",
        model="test-model",
        api_key="test-key",
        video_duration=10,
        cut_count="自动",
        clone_functions='[{"index":0,"name":"aspect_ratio","label":"宽高比","value":"9:16"}]',
        clone_0="9:16",
    )

    assert "【已锁定的功能参数】" in captured["system"]
    assert "aspect_ratio" in captured["system"]
    assert "9:16" in captured["system"]
    assert "竖屏构图" in captured["system"]
    assert result[5] == "9:16"
    assert result[6] == ""


def test_parse_clone_functions_ignores_placeholder_and_invalid_slots():
    module = load_package()
    node_module = sys.modules["minimax_h3_skillbridge_test.nodes"]

    parsed = node_module.parse_clone_functions(
        [
            {"index": 0, "name": "aspect_ratio", "value": "1:1 (Square)"},
            {"index": 99, "name": "bad", "value": "x"},
            {"index": 1, "name": "aspect_ratio", "value": node_module.CLONE_PLACEHOLDER},
        ],
        clone_0="16:9",
    )
    assert parsed == [{
        "index": 0,
        "name": "aspect_ratio",
        "label": "aspect_ratio",
        "value": "16:9",
    }]

def test_skill_dropdown_shows_chinese_display_names():
    module = load_package()
    node_module = sys.modules["minimax_h3_skillbridge_test.nodes"]
    catalog = sys.modules["minimax_h3_skillbridge_test.skill_catalog"]

    options = catalog.discover_skill_options()
    assert "全息讲解" in options
    assert "holographic-explainer" not in options
    assert options[0] == "3D动画短片生成"

    inputs = module.NODE_CLASS_MAPPINGS["StariAI-MiniMaxH3-Skill"].INPUT_TYPES()
    assert inputs["required"]["skill"][0] == options


def test_load_skill_accepts_chinese_display_name_and_legacy_directory_name():
    module = load_package()
    node_module = sys.modules["minimax_h3_skillbridge_test.nodes"]

    by_directory = node_module.load_skill("holographic-explainer")
    by_display = node_module.load_skill("全息讲解")

    assert by_directory[0] == "holographic-explainer"
    assert by_display[0] == "holographic-explainer"
    assert by_directory[1] == by_display[1]


def test_load_skill_rejects_unknown_name():
    module = load_package()
    node_module = sys.modules["minimax_h3_skillbridge_test.nodes"]

    try:
        node_module.load_skill("不存在的技能")
    except ValueError:
        pass
    else:
        raise AssertionError("未知技能未被拒绝")
