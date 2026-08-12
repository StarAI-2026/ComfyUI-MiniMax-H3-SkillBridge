import importlib.util
import json
import sys
from concurrent.futures import Future
from pathlib import Path


ROOT = Path(__file__).parents[1]
PACKAGE = "skillbridge_h3_runtime_test"
SPEC = importlib.util.spec_from_file_location(
    PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
package = importlib.util.module_from_spec(SPEC)
sys.modules[PACKAGE] = package
assert SPEC.loader is not None
SPEC.loader.exec_module(package)
runtime = sys.modules[f"{PACKAGE}.h3_chain_runtime"]


def _plan_json():
    return json.dumps({
        "schema": "stariai_h3_segment_plan_v1",
        "skill": "holographic-explainer",
        "max_segment_duration_seconds": 15,
        "segment_count": 2,
        "segments": [
            {"index": 0, "prompt": "one", "narration": "one", "duration_seconds": 15, "timeline_start_seconds": 0, "timeline_end_seconds": 15, "continuity": "initial"},
            {"index": 1, "prompt": "two", "narration": "two", "duration_seconds": 14, "timeline_start_seconds": 15, "timeline_end_seconds": 29, "continuity": "continue"},
        ],
    })


def _single_plan_json():
    return json.dumps({
        "schema": "stariai_h3_segment_plan_v1",
        "skill": "holographic-explainer",
        "max_segment_duration_seconds": 15,
        "segment_count": 1,
        "segments": [
            {"index": 0, "prompt": "single", "narration": "single", "duration_seconds": 15, "timeline_start_seconds": 0, "timeline_end_seconds": 15, "continuity": "initial"},
        ],
    })


class _Queue:
    def __init__(self):
        self.deleted = []
        self.interrupted = []
        self.location = "queued"

    def get_current_queue(self):
        item = (0, "prompt-1")
        return (([item], []) if self.location == "running" else ([], [item]) if self.location == "queued" else ([], []))

    def delete_queue_item(self, predicate):
        item = (0, "prompt-1")
        if self.location == "queued" and predicate(item):
            self.deleted.append(item[1])
            self.location = "missing"
            return True
        return False

    def interrupt_if_running(self, prompt_id):
        self.interrupted.append(prompt_id)
        return self.location == "running"


class _Server:
    def __init__(self, queue):
        self.prompt_queue = queue
        self.events = []

    def send_sync(self, name, payload):
        self.events.append((name, payload))


def test_queue_continuation_replays_only_the_next_segment(monkeypatch):
    record = _record("continuation")
    record.current_segment_index = 1
    record.client_id = "client-1"
    record.prompt_snapshot = {
        "147": {"class_type": "StariAI-MiniMaxH3-Skill", "inputs": {"skill": "holographic-explainer"}},
        "195": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {"prompt": ["__stariai_h3_chain_start_147", 2]}},
        "__stariai_h3_chain_start_147": {"class_type": "StariAIH3ChainStart", "inputs": {"segment_plan_json": _plan_json()}},
        "__stariai_h3_chain_segment_147": {"class_type": "StariAIH3SegmentPrompt", "inputs": {"segment_index": 0}},
    }
    enqueued = []

    class _PromptQueue:
        def put(self, item):
            enqueued.append(item)

    class _ContinuationServer:
        def __init__(self):
            self.loop = object()
            self.number = 7
            self.prompt_queue = _PromptQueue()

        def trigger_on_prompt(self, data):
            return data

        class node_replace_manager:
            @staticmethod
            def apply_replacements(prompt):
                return None

    async def _valid(*_args):
        return True, "", [], {}

    def _run_inline(coroutine, _loop):
        future = Future()
        try:
            future.set_result(__import__("asyncio").run(coroutine))
        except Exception as error:
            future.set_exception(error)
        return future

    server = _ContinuationServer()
    monkeypatch.setattr(runtime, "_server", lambda: server)
    monkeypatch.setattr(runtime.asyncio, "run_coroutine_threadsafe", _run_inline)
    import execution
    monkeypatch.setattr(execution, "validate_prompt", _valid)

    prompt_id = runtime._queue_continuation(record)

    assert prompt_id
    assert len(enqueued) == 1
    _number, queued_id, prompt, extra, _outputs, _flags = enqueued[0]
    assert queued_id == prompt_id
    assert extra["client_id"] == "client-1"
    assert prompt["147"] == {
        "class_type": "StariAIH3PlanReplay",
        "inputs": {"chain_id": record.chain_id, "segment_index": 1},
    }
    assert prompt["195"]["inputs"]["prompt"] == ["147", 2]
    assert prompt["__stariai_h3_chain_segment_147"]["inputs"]["segment_index"] == 1


def _record(start_key="start"):
    plan = runtime.parse_serialized_segment_plan(_plan_json())
    return runtime.CHAINS.create(plan, "147", {"x": {"inputs": {}}}, None, start_key)


def test_chain_start_key_keeps_one_chain_but_new_key_creates_new_chain():
    first = _record("run-a")
    same = runtime.CHAINS.get_or_create(
        "run-a", first.plan, "147", first.prompt_snapshot, None
    )
    second = _record("run-b")

    assert same.chain_id == first.chain_id
    assert second.chain_id != first.chain_id


def test_chain_start_accepts_a_single_segment_holographic_plan(monkeypatch):
    monkeypatch.setattr(runtime, "_persist_record", lambda record: None)
    monkeypatch.setattr(runtime, "_publish_status", lambda record: None)

    chain_id, _status, prompt = runtime.StariAIH3ChainStart().start(
        _single_plan_json(), "147", "single-segment", prompt={"147": {"inputs": {}}}
    )

    assert chain_id.startswith("skillbridge-")
    assert prompt == "single"
    assert runtime.CHAINS.get(chain_id).plan.segment_count == 1


def test_pause_removes_only_queued_continuation(monkeypatch):
    record = _record("pause")
    record.state = "running"
    record.prompt_id = "prompt-1"
    queue = _Queue()
    server = _Server(queue)
    monkeypatch.setattr(runtime, "_server", lambda: server)
    monkeypatch.setattr(runtime, "_persist_record", lambda record: None)

    status = runtime.control_pause_chain(record.chain_id)

    assert queue.deleted == ["prompt-1"]
    assert not queue.interrupted
    assert status["state"] == "paused"
    assert status["last_control_result"]["deleted_from_queue"] is True


def test_pause_does_not_interrupt_current_render(monkeypatch):
    record = _record("current")
    record.state = "running"
    record.prompt_id = "prompt-1"
    queue = _Queue()
    queue.location = "running"
    server = _Server(queue)
    monkeypatch.setattr(runtime, "_server", lambda: server)
    monkeypatch.setattr(runtime, "_persist_record", lambda record: None)

    status = runtime.control_pause_chain(record.chain_id)

    assert queue.deleted == []
    assert queue.interrupted == []
    assert status["state"] == "pausing"


def test_cancel_targets_active_prompt_and_releases_memory(monkeypatch):
    record = _record("cancel")
    record.state = "running"
    record.prompt_id = "prompt-1"
    queue = _Queue()
    server = _Server(queue)
    released = []
    monkeypatch.setattr(runtime, "_server", lambda: server)
    monkeypatch.setattr(runtime, "_persist_record", lambda record: None)
    monkeypatch.setattr(runtime.CONTEXTS, "release_chain", lambda chain_id: released.append(chain_id))

    status = runtime.control_cancel_chain(record.chain_id)

    assert queue.deleted == ["prompt-1"]
    assert released == [record.chain_id]
    assert status["state"] == "cancelled"


def test_final_composition_does_not_override_an_inflight_cancellation(monkeypatch):
    record = _record("cancel-during-compose")
    record.current_segment_index = 1
    monkeypatch.setattr(runtime, "_persist_record", lambda record: None)
    monkeypatch.setattr(runtime, "_publish_status", lambda record: None)
    monkeypatch.setattr(runtime.CONTEXTS, "release_chain", lambda chain_id: None)

    def _compose(_chain_id, _accepted):
        record.cancel_requested = True
        record.state = "cancelled"
        return "final.mp4", {"output_sha256": "hash"}

    monkeypatch.setattr(runtime, "compose_segment_videos", _compose)

    _filenames, status = runtime.StariAIH3SegmentTerminal().complete(
        (True, ["segment-1.mp4"]), {}, record.chain_id, 1
    )

    assert json.loads(status)["state"] == "cancelled"
    assert record.final_video_path == "final.mp4"
