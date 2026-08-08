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
    node = module.NODE_CLASS_MAPPINGS["MiniMaxH3SkillBridge"]
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
    assert len([name for name in inputs["optional"] if name.startswith("image_")]) == 64
