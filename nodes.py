from __future__ import annotations

import json
from typing import Any

from .cloud_client import CloudError, chat_cloud
from .media import collect_images, collect_video_frames
from .skill_catalog import discover_skills, load_skill


class StariAI_MiniMaxH3_Skill:
    CATEGORY = "StariAI-MiniMaxH3-Skill"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("视觉分析", "最终提示词", "运行状态", "模型信息")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        skills = discover_skills() or ["(没有发现 skill)"]
        return {
            "required": {
                "skill": (skills, {"default": skills[0], "display_name": "技能"}),
                "user_prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "根据参考素材和当前 skill 生成完整视频提示词。",
                        "display_name": "用户要求",
                    },
                ),
                "api_base": (
                    "STRING",
                    {
                        "default": "https://api.openai.com/v1",
                        "multiline": False,
                        "display_name": "API 地址",
                    },
                ),
                "model": (
                    "STRING",
                    {"default": "gpt-5.6-luna", "multiline": False, "display_name": "云端模型"},
                ),
                "api_key": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "display_name": "API 密钥（一次性，不随工作流保存）",
                    },
                ),
            },
            "optional": {
                **{f"image_{index}": ("IMAGE",) for index in range(1, 65)},
                "images": ("IMAGE", {"display_name": "多图输入"}),
                "video": ("IMAGE", {"display_name": "视频输入"}),
            },
        }

    @staticmethod
    def _system(skill_name: str, instructions: str) -> str:
        return (
            "你是严格遵循本地 skill 的视频提示词工程师。\n"
            f"当前 skill：{skill_name}\n\n{instructions}\n\n"
            "先分析所有参考图与视频帧中的主体、场景、构图、镜头、动作、时间顺序、"
            "光线、材质、风格和一致性；再结合用户要求和 skill 生成最终结果。\n"
            "输出格式必须分为两段：\n"
            "[视觉分析]\n简明归纳参考素材。\n"
            "[最终视频提示词]\n仅输出可直接交给视频模型的完整提示词。"
        )

    @staticmethod
    def _split_result(result: str) -> tuple[str, str]:
        marker = "[最终视频提示词]"
        if marker not in result:
            return "", result
        analysis, prompt = result.split(marker, 1)
        return analysis.replace("[视觉分析]", "").strip(), prompt.strip()

    def run(
        self,
        skill: str,
        user_prompt: str,
        api_base: str,
        model: str,
        api_key: str = "",
        image_1: Any = None,
        image_2: Any = None,
        image_3: Any = None,
        image_4: Any = None,
        images: Any = None,
        video: Any = None,
        **kwargs: Any,
    ):
        try:
            skill_name, instructions = load_skill(skill)
            direct_images = [image_1, image_2, image_3, image_4]
            dynamic_images = [value for name, value in kwargs.items() if name.startswith("image_")]
            references = collect_images(*direct_images, images, *dynamic_images, max_image_side=1024)
            frames = collect_video_frames(video, frame_count=8, sample_interval=1, max_image_side=1024)
            raw = chat_cloud(
                api_base,
                model,
                self._system(skill_name, instructions),
                user_prompt,
                references,
                frames,
                temperature=0.0,
                top_p=0.9,
                max_tokens=2048,
                repetition_penalty=1.05,
                api_key=api_key,
                proxy_url="",
                timeout=120,
            )
            analysis, result = self._split_result(raw)
            status = {"ok": True, "mode": "cloud", "skill": skill_name, "images": len(references), "video_frames": len(frames)}
            model_info = {"mode": "cloud", "model": model, "api_base": api_base.rstrip("/")}
            return analysis, result, json.dumps(status, ensure_ascii=False), json.dumps(model_info, ensure_ascii=False)
        except (ValueError, CloudError) as exc:
            raise RuntimeError(f"StariAI-MiniMaxH3-Skill：{exc}") from exc


NODE_CLASS_MAPPINGS = {"StariAI-MiniMaxH3-Skill": StariAI_MiniMaxH3_Skill}
NODE_DISPLAY_NAME_MAPPINGS = {"StariAI-MiniMaxH3-Skill": "StariAI-MiniMaxH3-Skill"}
