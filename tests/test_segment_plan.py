import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "skillbridge_segment_plan_test", ROOT / "segment_plan.py"
)
segment_plan = importlib.util.module_from_spec(spec)
sys.modules["skillbridge_segment_plan_test"] = segment_plan
assert spec.loader is not None
spec.loader.exec_module(segment_plan)


def plan_payload(second_duration=14.0):
    return {
        "schema": "stariai_h3_segment_plan_v1",
        "skill": "holographic-explainer",
        "max_segment_duration_seconds": 15,
        "segment_count": 2,
        "segments": [
            {
                "index": 0, "prompt": "first prompt", "narration": "first narration",
                "duration_seconds": 15, "timeline_start_seconds": 0,
                "timeline_end_seconds": 15, "continuity": "initial",
            },
            {
                "index": 1, "prompt": "second prompt", "narration": "second narration",
                "duration_seconds": second_duration, "timeline_start_seconds": 15,
                "timeline_end_seconds": 15 + second_duration, "continuity": "continue previous motion",
            },
        ],
    }


def raw_plan(payload):
    return "[最终视频提示词]\nhuman readable\n[SEGMENT_PLAN_JSON]\n" + json.dumps(payload, ensure_ascii=False)


def test_valid_plan_normalizes_and_hides_machine_block():
    plan = segment_plan.parse_segment_plan(raw_plan(plan_payload()), "holographic-explainer")

    assert plan.segment_count == 2
    assert plan.segments[1].prompt == "second prompt"
    assert len(plan.plan_hash) == 64
    assert segment_plan.remove_plan_block(raw_plan(plan_payload())).endswith("human readable")
    assert json.loads(segment_plan.serialize_segment_plan(plan))["segment_count"] == 2


def test_plan_rejects_continuation_that_h3_cannot_deliver_after_context_trim():
    try:
        segment_plan.parse_segment_plan(raw_plan(plan_payload(14.5)), "holographic-explainer")
    except ValueError as error:
        assert "14.167" in str(error)
    else:
        raise AssertionError("continuation above physical H3 delivery limit was accepted")


def test_plan_rejects_gap_and_duplicate_index():
    payload = plan_payload()
    payload["segments"][1]["index"] = 2
    try:
        segment_plan.parse_segment_plan(raw_plan(payload), "holographic-explainer")
    except ValueError as error:
        assert "连续" in str(error)
    else:
        raise AssertionError("gapped index was accepted")

    payload = plan_payload()
    payload["segments"][1]["timeline_start_seconds"] = 14
    payload["segments"][1]["timeline_end_seconds"] = 28
    try:
        segment_plan.parse_segment_plan(raw_plan(payload), "holographic-explainer")
    except ValueError as error:
        assert "连续衔接" in str(error)
    else:
        raise AssertionError("overlapping timeline was accepted")
