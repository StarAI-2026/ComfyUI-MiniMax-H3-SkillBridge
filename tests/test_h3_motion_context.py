import importlib.util
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "skillbridge_h3_motion_test", ROOT / "h3_motion_context.py"
)
motion = importlib.util.module_from_spec(spec)
sys.modules["skillbridge_h3_motion_test"] = motion
assert spec.loader is not None
spec.loader.exec_module(motion)


def av_latent():
    video = torch.arange(1 * 24 * 12 * 2 * 2, dtype=torch.float32).reshape(1, 24, 12, 2, 2)
    audio = torch.arange(1 * 32 * 2 * 200, dtype=torch.float32).reshape(1, 32, 2, 200)
    return {"samples": (video, audio)}


def test_memory_registry_keeps_only_expected_tail_and_resolves_exact_identity():
    registry = motion.ContextRegistry()
    envelope = registry.register("chain-a", 0, "candidate-a", av_latent(), 22)

    assert envelope.ref.startswith("h3ctx://chain-a/0/candidate-a/")
    assert envelope.video_tail.shape == (1, 24, 7, 2, 2)
    assert envelope.audio_tail.shape == (1, 32, 2, round(22 / 24 * 40))
    assert envelope.video_tail.device.type == "cpu"
    assert registry.resolve(envelope.ref, "chain-a", 0, envelope.sha256) == envelope

    try:
        registry.resolve(envelope.ref, "another-chain", 0, envelope.sha256)
    except ValueError as error:
        assert "另一条链" in str(error)
    else:
        raise AssertionError("foreign chain context was accepted")

    registry.release_chain("chain-a")
    try:
        registry.resolve(envelope.ref, "chain-a", 0, envelope.sha256)
    except RuntimeError as error:
        assert "detached" in str(error)
    else:
        raise AssertionError("released context was still resolvable")


def test_context_conditioning_preserves_user_reference_blocks():
    envelope = motion.ContextRegistry().register("chain-b", 0, "candidate-b", av_latent(), 22)
    context = motion.context_from_envelope(envelope, 1)
    original = [[None, {"minimax_refs": [{"kind": "image", "latent": torch.zeros(1)}]}]]
    conditioned = motion.inject_motion_context(original, context, 362)

    values = conditioned[0][1]
    assert len(values["minimax_refs"]) == 2
    assert values["minimax_refs"][0]["kind"] == "image"
    assert len(values["minimax_keyframes"]) == 7
