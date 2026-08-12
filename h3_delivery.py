"""Safe final MP4 delivery for a completed in-memory H3 chain.

Only ordinary rendered segment videos and a small JSON ledger are persisted.
The H3 AV latent never crosses this boundary and is never serialized.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Iterable, Mapping

import numpy as np


DELIVERY_SCHEMA = 1
LEDGER_NAME = "chain.json"
FPS = 24


def _safe_token(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    token = "".join(character if character in allowed else "_" for character in str(value))
    return token.strip("._")[:96] or "chain"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def chain_root(chain_id: str) -> Path:
    import folder_paths

    output_root = Path(folder_paths.get_output_directory()).resolve()
    root = (output_root / "SkillBridge-H3" / _safe_token(chain_id)).resolve()
    if output_root not in root.parents:
        raise ValueError("H3 chain delivery path escaped the ComfyUI output directory")
    return root


def _resolve_segment_video(value: str | os.PathLike[str]) -> Path:
    import folder_paths

    output_root = Path(folder_paths.get_output_directory()).resolve()
    raw = Path(value)
    path = raw.resolve() if raw.is_absolute() else (output_root / raw).resolve()
    if output_root not in path.parents:
        raise ValueError(f"H3 segment video is outside ComfyUI output: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"H3 segment video is missing: {path}")
    return path


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_chain_ledger(
    chain_id: str,
    *,
    state: str,
    plan_hash: str,
    skill_node_id: str,
    accepted: Iterable[Mapping[str, Any]],
    final_video_path: str = "",
    final_video_sha256: str = "",
    last_error: str = "",
) -> Path:
    """Persist audit-safe recovery metadata without prompts or latent tensors."""

    segment_entries = []
    for item in accepted:
        video_path = _resolve_segment_video(str(item["video_path"]))
        segment_entries.append({
            "index": int(item["segment_index"]),
            "video_path": str(video_path),
            "video_sha256": _sha256_file(video_path),
            "context_transport": str(item.get("context_transport") or "none"),
            "context_sha256": str(item.get("context_sha256") or ""),
            "file_required": False,
        })
    payload = {
        "schema": DELIVERY_SCHEMA,
        "format": "stariai_h3_chain_ledger",
        "chain_id": str(chain_id),
        "state": str(state),
        "plan_hash": str(plan_hash),
        "skill_node_id": str(skill_node_id),
        "context_transport": "memory",
        "file_required": False,
        "recovery_policy": "detached_on_process_loss",
        "accepted": segment_entries,
        "final_video_path": str(final_video_path),
        "final_video_sha256": str(final_video_sha256),
        "last_error": str(last_error)[:4000],
        "updated_unix": time.time(),
    }
    path = chain_root(chain_id) / LEDGER_NAME
    _atomic_json(path, payload)
    return path


def read_chain_ledger(chain_id: str) -> dict[str, Any] | None:
    path = chain_root(chain_id) / LEDGER_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != DELIVERY_SCHEMA
        or payload.get("format") != "stariai_h3_chain_ledger"
        or payload.get("chain_id") != str(chain_id)
    ):
        return None
    return payload


def detached_status(chain_id: str) -> dict[str, Any] | None:
    ledger = read_chain_ledger(chain_id)
    if ledger is None:
        return None
    accepted = ledger.get("accepted")
    return {
        "schema": DELIVERY_SCHEMA,
        "chain_id": str(chain_id),
        "state": "detached",
        "segment_count": len(accepted) if isinstance(accepted, list) else 0,
        "accepted_count": len(accepted) if isinstance(accepted, list) else 0,
        "current_segment_index": len(accepted) if isinstance(accepted, list) else 0,
        "plan_hash": str(ledger.get("plan_hash") or ""),
        "context_transport": "memory",
        "file_required": False,
        "recovery_policy": "detached_on_process_loss",
        "recovery_required": True,
        "final_video_path": str(ledger.get("final_video_path") or ""),
        "last_error": (
            "The H3 chain belongs to a previous ComfyUI process. Its in-memory AV context "
            "cannot be recovered, so continuation is deliberately blocked."
        ),
    }


def _decode_audio(path: Path, sample_rate: int) -> np.ndarray:
    import av

    chunks: list[np.ndarray] = []
    with av.open(str(path), mode="r") as source:
        if not source.streams.audio:
            raise ValueError(f"H3 segment has no audio stream: {path}")
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=sample_rate)
        for frame in source.decode(source.streams.audio[0]):
            for converted in resampler.resample(frame):
                array = converted.to_ndarray()
                if array.ndim != 2 or array.shape[0] != 2:
                    raise ValueError(f"H3 segment audio is not stereo: {path}")
                chunks.append(array.astype(np.float32, copy=False))
        for converted in resampler.resample(None):
            array = converted.to_ndarray()
            chunks.append(array.astype(np.float32, copy=False))
    return np.concatenate(chunks, axis=1) if chunks else np.zeros((2, 0), dtype=np.float32)


def _bridge_audio(previous_last: np.ndarray, current: np.ndarray, sample_rate: int) -> np.ndarray:
    if current.shape[1] == 0:
        return current
    count = min(round(sample_rate * 0.005), current.shape[1])
    if count <= 0:
        return current
    weights = np.ones((1,), dtype=np.float32) if count == 1 else 0.5 * (
        1.0 + np.cos(np.linspace(0.0, np.pi, count, dtype=np.float32))
    )
    output = current.copy()
    output[:, :count] += (previous_last - output[:, 0])[:, None] * weights[None, :]
    return np.clip(output, -1.0, 1.0)


def compose_segment_videos(chain_id: str, accepted: Iterable[Mapping[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Stream-decode segment MP4 files and write exactly one final MP4."""

    entries = sorted((dict(item) for item in accepted), key=lambda item: int(item["segment_index"]))
    if not entries or [int(item["segment_index"]) for item in entries] != list(range(len(entries))):
        raise ValueError("H3 final delivery requires contiguous accepted segment videos")
    paths = [_resolve_segment_video(str(item["video_path"])) for item in entries]

    import av

    with av.open(str(paths[0]), mode="r") as first_source:
        if not first_source.streams.video or not first_source.streams.audio:
            raise ValueError(f"H3 segment is missing video or audio: {paths[0]}")
        video_input = first_source.streams.video[0]
        width, height = int(video_input.width), int(video_input.height)

    first_audio = _decode_audio(paths[0], 32_000)
    if first_audio.shape[1] == 0:
        raise ValueError(f"H3 segment decoded to empty audio: {paths[0]}")
    sample_rate = 32_000

    root = chain_root(chain_id)
    root.mkdir(parents=True, exist_ok=True)
    output_path = root / f"H3_Sequential_{_safe_token(chain_id)[-20:]}_final.mp4"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.", suffix=".mp4.tmp", dir=root
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    encoded_frames = 0
    encoded_samples = 0
    previous_last: np.ndarray | None = None
    try:
        with av.open(str(temporary), mode="w", format="mp4") as output:
            video_stream = output.add_stream("libx264", rate=Fraction(FPS, 1))
            video_stream.width = width
            video_stream.height = height
            video_stream.pix_fmt = "yuv420p"
            video_stream.options = {"crf": "18", "preset": "medium"}
            audio_stream = output.add_stream("aac", rate=sample_rate, layout="stereo")

            for path in paths:
                with av.open(str(path), mode="r") as source:
                    if not source.streams.video:
                        raise ValueError(f"H3 segment has no video stream: {path}")
                    stream = source.streams.video[0]
                    if int(stream.width) != width or int(stream.height) != height:
                        raise ValueError("H3 segments do not share one video resolution")
                    for decoded in source.decode(stream):
                        frame = av.VideoFrame.from_ndarray(decoded.to_ndarray(format="rgb24"), format="rgb24")
                        output.mux(video_stream.encode(frame))
                        encoded_frames += 1
            output.mux(video_stream.encode(None))

            for path in paths:
                audio = _decode_audio(path, sample_rate)
                if audio.shape[1] == 0:
                    raise ValueError(f"H3 segment decoded to empty audio: {path}")
                if previous_last is not None:
                    audio = _bridge_audio(previous_last, audio, sample_rate)
                previous_last = audio[:, -1].copy()
                frame = av.AudioFrame.from_ndarray(audio, format="fltp", layout="stereo")
                frame.sample_rate = sample_rate
                frame.pts = encoded_samples
                frame.time_base = Fraction(1, sample_rate)
                output.mux(audio_stream.encode(frame))
                encoded_samples += int(audio.shape[1])
            output.mux(audio_stream.encode(None))
        with temporary.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    report = {
        "schema": DELIVERY_SCHEMA,
        "chain_id": str(chain_id),
        "segment_count": len(entries),
        "output_path": str(output_path),
        "output_sha256": _sha256_file(output_path),
        "fps": FPS,
        "frame_count": encoded_frames,
        "sample_rate": sample_rate,
        "audio_samples": encoded_samples,
        "audio_seam_policy": "5ms_cosine_bridge",
        "latent_files_created": False,
    }
    return str(output_path), report
