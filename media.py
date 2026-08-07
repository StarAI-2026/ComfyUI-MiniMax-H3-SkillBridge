from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image


def _to_pil(value: Any, max_image_side: int) -> Image.Image | None:
    if value is None:
        return None
    if isinstance(value, Image.Image):
        image = value.convert("RGB")
    else:
        tensor = value.detach().cpu() if hasattr(value, "detach") else value
        array = tensor.numpy() if hasattr(tensor, "numpy") else np.asarray(tensor)
        if array.ndim == 4:
            array = array[0]
        if array.ndim != 3 or array.shape[-1] < 3:
            raise ValueError("图片数据必须是 ComfyUI IMAGE 格式")
        array = np.clip(array[..., :3], 0, 1)
        image = Image.fromarray((array * 255).astype(np.uint8), "RGB")
    if max_image_side and max(image.size) > max_image_side:
        image.thumbnail((max_image_side, max_image_side), Image.Resampling.LANCZOS)
    return image


def collect_images(*values: Any, max_image_side: int = 1024) -> list[Image.Image]:
    images: list[Image.Image] = []
    for value in values:
        if value is None:
            continue
        if hasattr(value, "ndim") and value.ndim == 4:
            for item in value:
                image = _to_pil(item, max_image_side)
                if image is not None:
                    images.append(image)
        elif isinstance(value, (list, tuple)):
            for item in value:
                image = _to_pil(item, max_image_side)
                if image is not None:
                    images.append(image)
        else:
            image = _to_pil(value, max_image_side)
            if image is not None:
                images.append(image)
    return images


def collect_video_frames(video: Any, frame_count: int = 8, sample_interval: int = 1,
                         max_image_side: int = 1024) -> list[Image.Image]:
    if video is None:
        return []
    frames = collect_images(video, max_image_side=max_image_side)
    step = max(1, int(sample_interval))
    sampled = frames[::step]
    if frame_count > 0 and len(sampled) > frame_count:
        indexes = np.linspace(0, len(sampled) - 1, frame_count, dtype=int)
        sampled = [sampled[index] for index in indexes]
    return sampled


def image_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
