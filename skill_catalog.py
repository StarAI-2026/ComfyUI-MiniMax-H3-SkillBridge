from __future__ import annotations

from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
SKILL_ROOTS = (PLUGIN_DIR / "skills",)


def discover_skills() -> list[str]:
    names: set[str] = set()
    for root in SKILL_ROOTS:
        if root.is_dir():
            names.update(
                path.name for path in root.iterdir()
                if path.is_dir() and (path / "SKILL.md").is_file()
            )
    return sorted(names)


def load_skill(name: str) -> tuple[str, str]:
    for root in SKILL_ROOTS:
        path = root / name / "SKILL.md"
        if path.is_file():
            content = path.read_text(encoding="utf-8-sig").strip()
            if content:
                return name, content
    raise ValueError(f"未找到 skill：{name}")
