import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("skillbridge_h3_delivery_test", ROOT / "h3_delivery.py")
delivery = importlib.util.module_from_spec(SPEC)
sys.modules["skillbridge_h3_delivery_test"] = delivery
assert SPEC.loader is not None
SPEC.loader.exec_module(delivery)


def _make_mp4(path: Path, color: tuple[int, int, int]) -> None:
    import av

    from fractions import Fraction

    with av.open(str(path), mode="w", format="mp4") as output:
        video = output.add_stream("libx264", rate=24)
        video.width = 16
        video.height = 16
        video.pix_fmt = "yuv420p"
        audio = output.add_stream("aac", rate=32_000, layout="stereo")
        for _ in range(3):
            image = np.zeros((16, 16, 3), dtype=np.uint8)
            image[:] = color
            output.mux(video.encode(av.VideoFrame.from_ndarray(image, format="rgb24")))
        output.mux(video.encode(None))
        samples = np.zeros((2, 4_000), dtype=np.float32)
        frame = av.AudioFrame.from_ndarray(samples, format="fltp", layout="stereo")
        frame.sample_rate = 32_000
        frame.time_base = Fraction(1, 32_000)
        output.mux(audio.encode(frame))
        output.mux(audio.encode(None))


def test_final_delivery_composes_mp4_and_writes_latent_free_ledger(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setitem(sys.modules, "folder_paths", type("Paths", (), {
        "get_output_directory": staticmethod(lambda: str(output)),
    }))

    first = output / "first.mp4"
    second = output / "second.mp4"
    _make_mp4(first, (255, 0, 0))
    _make_mp4(second, (0, 255, 0))
    accepted = [
        {"segment_index": 0, "video_path": str(first), "context_transport": "memory", "context_sha256": "a" * 64},
        {"segment_index": 1, "video_path": str(second)},
    ]

    final_path, report = delivery.compose_segment_videos("chain-a", accepted)
    ledger_path = delivery.write_chain_ledger(
        "chain-a",
        state="completed",
        plan_hash="p" * 64,
        skill_node_id="147",
        accepted=accepted,
        final_video_path=final_path,
        final_video_sha256=report["output_sha256"],
    )

    assert Path(final_path).is_file()
    assert report["frame_count"] == 6
    assert report["latent_files_created"] is False
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert payload["context_transport"] == "memory"
    assert payload["file_required"] is False
    assert "context_ref" not in json.dumps(payload)
    assert not list(output.rglob("*.safetensors"))


def test_existing_ledger_reports_detached_after_process_loss(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setitem(sys.modules, "folder_paths", type("Paths", (), {
        "get_output_directory": staticmethod(lambda: str(output)),
    }))
    segment = output / "segment.mp4"
    _make_mp4(segment, (0, 0, 255))
    delivery.write_chain_ledger(
        "chain-lost",
        state="running",
        plan_hash="p" * 64,
        skill_node_id="147",
        accepted=[{"segment_index": 0, "video_path": str(segment)}],
    )

    status = delivery.detached_status("chain-lost")

    assert status is not None
    assert status["state"] == "detached"
    assert status["recovery_required"] is True
    assert "cannot be recovered" in status["last_error"]
