import importlib.util
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "starai_skillbridge_media_test",
    ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
package = importlib.util.module_from_spec(spec)
sys.modules["starai_skillbridge_media_test"] = package
assert spec.loader is not None
spec.loader.exec_module(package)
media = sys.modules["starai_skillbridge_media_test.media"]


def test_collect_images_expands_batch():
    assert len(media.collect_images(torch.zeros((3, 16, 16, 3)), max_image_side=512)) == 3


def test_collect_video_frames_samples_evenly():
    frames = media.collect_video_frames(torch.zeros((20, 16, 16, 3)), frame_count=8, sample_interval=2)
    assert len(frames) == 8
