from __future__ import annotations

from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
SKILL_ROOTS = (PLUGIN_DIR / "skills",)

# 下拉框显示名。只影响界面展示，不改动 skills/ 下的文件夹与文件；
# 真实目录名仍然是唯一的内部标识。
SKILL_DISPLAY_NAMES: dict[str, str] = {
    "3d-animation-short-generator": "3D动画短片生成",
    "brand-promo-video-generator": "品牌宣传片生成",
    "character-interactive-explainer": "角色互动讲解",
    "co-op-game-intro-generator": "合作游戏开场生成",
    "h3-prompt-writing": "H3提示词编写",
    "handdrawn-live-video-generator": "手绘直播视频生成",
    "holographic-explainer": "全息讲解",
    "minimalist-product-ad-generator": "极简产品广告生成",
    "mv-subtitle-skill-confirmed": "MV字幕生成",
    "paper-collage-explainer-generator": "纸拼贴讲解生成",
    "papercraft-stop-motion-explainer": "纸艺定格动画讲解",
    "高动态运镜": "高动态运镜",
}

_DISPLAY_TO_DIRECTORY = {
    display: directory for directory, display in SKILL_DISPLAY_NAMES.items()
}


def _skill_directories() -> list[str]:
    names: set[str] = set()
    for root in SKILL_ROOTS:
        if root.is_dir():
            names.update(
                path.name for path in root.iterdir()
                if path.is_dir()
                and (path / "SKILL.md").is_file()
            )
    return sorted(names)


def discover_skills() -> list[str]:
    """真实 skill 目录名列表，作为内部标识使用。"""
    return _skill_directories()


def skill_display_name(directory: str) -> str:
    """目录名 -> 下拉框显示名；未映射的目录名原样返回。"""
    return SKILL_DISPLAY_NAMES.get(directory, directory)


def discover_skill_options() -> list[str]:
    """下拉框选项：按真实目录名排序对应的中文显示名。"""
    return [skill_display_name(name) for name in _skill_directories()]


def resolve_skill_directory(value: str) -> str:
    """把下拉框显示名或旧工作流中的真实目录名统一解析为目录名。"""
    value = str(value or "").strip()
    if not value:
        raise ValueError("技能不能为空")
    for root in SKILL_ROOTS:
        if (root / value / "SKILL.md").is_file():
            return value
    directory = _DISPLAY_TO_DIRECTORY.get(value)
    if directory is not None:
        return directory
    raise ValueError(f"未找到 skill：{value}")


def load_skill(name: str) -> tuple[str, str]:
    directory = resolve_skill_directory(name)
    for root in SKILL_ROOTS:
        path = root / directory / "SKILL.md"
        if path.is_file():
            content = path.read_text(encoding="utf-8-sig").strip()
            if content:
                return directory, content
    raise ValueError(f"未找到 skill：{name}")