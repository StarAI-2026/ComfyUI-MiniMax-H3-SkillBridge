from __future__ import annotations

import json
import re
from typing import Any

from .cloud_client import CloudError, chat_cloud
from .media import collect_images, collect_video_frames
from .skill_catalog import discover_skills, load_skill


CUT_COUNT_OPTIONS = ["不切镜", "自动", *[f"切镜{index}" for index in range(1, 16)]]


def parse_shot_plan(video_duration: int, cut_count: str) -> dict[str, Any]:
    try:
        duration = int(video_duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("视频时长必须是 5 到 15 之间的整数秒") from exc
    if not 5 <= duration <= 15:
        raise ValueError("视频时长必须在 5 到 15 秒之间")

    selection = str(cut_count or "自动").strip()
    if selection == "不切镜":
        return {
            "duration_seconds": duration,
            "cut_mode": "none",
            "cut_count": 0,
            "shot_count": 1,
            "selection": selection,
        }
    if selection == "自动":
        return {
            "duration_seconds": duration,
            "cut_mode": "auto",
            "cut_count": None,
            "shot_count": None,
            "selection": selection,
        }

    match = re.fullmatch(r"切镜(\d+)", selection)
    if not match or not 1 <= int(match.group(1)) <= 15:
        raise ValueError("切镜数量必须选择「不切镜」「自动」或「切镜1」到「切镜15」")
    cuts = int(match.group(1))
    return {
        "duration_seconds": duration,
        "cut_mode": "fixed",
        "cut_count": cuts,
        "shot_count": cuts + 1,
        "selection": selection,
    }


def shot_plan_instruction(plan: dict[str, Any]) -> str:
    duration = plan["duration_seconds"]
    selection = plan["selection"]
    if plan["cut_mode"] == "none":
        rule = (
            "不切镜：必须一镜到底，只输出一个连续镜头段，整个视频过程中不得发生镜头切换。"
        )
    elif plan["cut_mode"] == "auto":
        rule = (
            "自动：根据用户描述、参考素材和视频总时长自行判断合理的切镜次数；"
            "必须在最终提示词中明确写出实际镜头段数量、每段时间范围和切换点。"
        )
    else:
        cuts = plan["cut_count"]
        shots = plan["shot_count"]
        rule = (
            f"{selection}：必须恰好发生 {cuts} 次镜头切换，生成 {shots} 个连续镜头段。"
            "不得少切或多切；每个镜头段都要写明时间范围、画面内容、主体动作、"
            "景别/构图、运镜和与下一镜头的切换方式。"
        )
    return (
        "【视频时长与切镜要求】\n"
        f"- 视频总时长必须严格为 {duration} 秒，时间线必须从 0 秒覆盖到 {duration} 秒。\n"
        f"- 当前切镜选择：{selection}。\n"
        f"- {rule}\n"
        "- 所有镜头时间范围必须连续、不重叠、不留空白，且切镜数量必须符合上述要求。\n"
        "- 最终视频提示词应按镜头顺序输出，使用清晰的时间标记，例如 [0-3s]、[3-7s]。"
    )


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
                "video_duration": (
                    "INT",
                    {
                        "default": 10,
                        "min": 5,
                        "max": 15,
                        "step": 1,
                        "display_name": "视频时长（秒）",
                    },
                ),
                "cut_count": (
                    CUT_COUNT_OPTIONS,
                    {"default": "自动", "display_name": "切镜数量"},
                ),
                **{f"image_{index}": ("IMAGE",) for index in range(1, 7)},
                "images": ("IMAGE", {"display_name": "多图输入"}),
                "video": ("IMAGE", {"display_name": "视频输入"}),
            },
        }

    @staticmethod
    def _system(skill_name: str, instructions: str, shot_plan: dict[str, Any]) -> str:
        return (
            "你是严格遵循本地 skill 的视频提示词工程师。\n"
            f"当前 skill：{skill_name}\n\n{instructions}\n\n"
            f"{shot_plan_instruction(shot_plan)}\n\n"
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
        video_duration: int = 10,
        cut_count: str = "自动",
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
            shot_plan = parse_shot_plan(video_duration, cut_count)
            direct_images = [image_1, image_2, image_3, image_4]
            dynamic_images = [value for name, value in kwargs.items() if name.startswith("image_")]
            references = collect_images(*direct_images, images, *dynamic_images, max_image_side=1024)
            frames = collect_video_frames(video, frame_count=8, sample_interval=1, max_image_side=1024)
            raw = chat_cloud(
                api_base,
                model,
                self._system(skill_name, instructions, shot_plan),
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
            status = {
                "ok": True,
                "mode": "cloud",
                "skill": skill_name,
                "video_duration": shot_plan["duration_seconds"],
                "cut_selection": shot_plan["selection"],
                "cut_count": shot_plan["cut_count"],
                "shot_count": shot_plan["shot_count"],
                "images": len(references),
                "video_frames": len(frames),
            }
            model_info = {"mode": "cloud", "model": model, "api_base": api_base.rstrip("/")}
            return analysis, result, json.dumps(status, ensure_ascii=False), json.dumps(model_info, ensure_ascii=False)
        except (ValueError, CloudError) as exc:
            raise RuntimeError(f"StariAI-MiniMaxH3-Skill：{exc}") from exc


class StariAI_MiniMaxH3_Chat(StariAI_MiniMaxH3_Skill):
    CATEGORY = "StariAI-MiniMaxH3-Skill"
    RETURN_TYPES = (
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
    )
    RETURN_NAMES = (
        "视觉分析",
        "当前结果",
        "最终提示词",
        "对话历史",
        "运行状态",
        "模型信息",
    )
    FUNCTION = "run_chat"
    OUTPUT_NODE = True
    MAX_TURNS = 12
    MODES = ["一次性输出", "多轮对话"]
    ACTIONS = ["继续对话", "确认并生成", "清空对话"]

    @classmethod
    def INPUT_TYPES(cls):
        inputs = super().INPUT_TYPES()
        required = inputs["required"]
        inputs["required"] = {
            "run_mode": (cls.MODES, {"default": "多轮对话", "display_name": "运行模式"}),
            "conversation_action": (
                cls.ACTIONS,
                {"default": "继续对话", "display_name": "对话操作"},
            ),
            **required,
            "conversation_state": (
                "STRING",
                {"default": "{}", "multiline": False, "display_name": "会话状态（自动保存）"},
            ),
        }
        return inputs

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "version": 1,
            "turns": [],
            "last_prompt": "",
            "confirmed_prompt": "",
            "confirmed": False,
            "shot_plan": None,
        }

    @classmethod
    def _load_state(cls, raw_state: str) -> dict[str, Any]:
        try:
            state = json.loads(raw_state or "{}")
        except (TypeError, ValueError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        turns = state.get("turns")
        if not isinstance(turns, list):
            turns = []

        state = {
            "version": 1,
            "turns": [turn for turn in turns if isinstance(turn, dict)][-cls.MAX_TURNS:],
            "last_prompt": str(state.get("last_prompt") or ""),
            "confirmed_prompt": str(state.get("confirmed_prompt") or ""),
            "confirmed": bool(state.get("confirmed", False)),
            "shot_plan": state.get("shot_plan") if isinstance(state.get("shot_plan"), dict) else None,
        }
        return state

    @staticmethod
    def _history_messages(state: dict[str, Any]) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        for turn in state["turns"]:
            user = str(turn.get("user") or "").strip()
            assistant = str(turn.get("assistant") or "").strip()
            if user:
                history.append({"role": "user", "content": user})
            if assistant:
                history.append({"role": "assistant", "content": assistant})
        return history

    @staticmethod
    def _history_text(state: dict[str, Any]) -> str:
        if not state["turns"]:
            return ""
        parts: list[str] = []
        for index, turn in enumerate(state["turns"], 1):
            parts.append(
                f"第 {index} 轮\n"
                f"用户：{turn.get('user', '')}\n"
                f"助手：{turn.get('assistant', '')}"
            )
        return "\n\n".join(parts)

    @staticmethod
    def _state_json(state: dict[str, Any]) -> str:
        return json.dumps(state, ensure_ascii=False, separators=(",", ":"))

    def _result(
        self,
        analysis: str,
        current_result: str,
        final_prompt: str,
        state: dict[str, Any],
        status: dict[str, Any],
        model_info: dict[str, Any],
    ) -> dict[str, Any]:
        state_json = self._state_json(state)
        history_text = self._history_text(state)
        view = {
            "analysis": analysis,
            "current_result": current_result,
            "final_prompt": final_prompt,
            "history": history_text,
            "status": status,
        }
        return {
            "result": (
                analysis,
                current_result,
                final_prompt,
                history_text,
                json.dumps(status, ensure_ascii=False),
                json.dumps(model_info, ensure_ascii=False),
            ),
            "ui": {
                "conversation_state": [state_json],
                "conversation_view": [json.dumps(view, ensure_ascii=False)],
            },
        }

    def run_chat(
        self,
        run_mode: str,
        conversation_action: str,
        skill: str,
        user_prompt: str,
        api_base: str,
        model: str,
        api_key: str = "",
        conversation_state: str = "{}",
        video_duration: int = 10,
        cut_count: str = "自动",
        image_1: Any = None,
        image_2: Any = None,
        image_3: Any = None,
        image_4: Any = None,
        images: Any = None,
        video: Any = None,
        **kwargs: Any,
    ):
        try:
            state = self._load_state(conversation_state)
            skill_name, instructions = load_skill(skill)
            shot_plan = parse_shot_plan(video_duration, cut_count)
            if run_mode == "一次性输出":
                conversation_action = "继续对话"

            if conversation_action == "清空对话":
                status = {
                    "ok": True,
                    "mode": run_mode,
                    "phase": "cleared",
                    "turns": 0,
                    "video_duration": shot_plan["duration_seconds"],
                    "cut_selection": shot_plan["selection"],
                    "cut_count": shot_plan["cut_count"],
                    "shot_count": shot_plan["shot_count"],
                }
                return self._result("", "", "", self._empty_state(), status, {"mode": "cloud", "model": model, "api_base": api_base.rstrip("/")})

            if conversation_action == "确认并生成":
                if not state["last_prompt"]:
                    raise ValueError("还没有可确认的提示词，请先执行一次「继续对话」")
                if state["shot_plan"] and state["shot_plan"] != shot_plan:
                    raise ValueError("视频时长或切镜数量已改变，请先点击「继续对话」重新生成后再确认")
                state["confirmed"] = True
                state["confirmed_prompt"] = state["last_prompt"]
                status = {
                    "ok": True,
                    "mode": run_mode,
                    "phase": "confirmed",
                    "turns": len(state["turns"]),
                    "confirmed": True,
                    "video_duration": shot_plan["duration_seconds"],
                    "cut_selection": shot_plan["selection"],
                    "cut_count": shot_plan["cut_count"],
                    "shot_count": shot_plan["shot_count"],
                }
                return self._result("", state["last_prompt"], state["confirmed_prompt"], state, status, {"mode": "cloud", "model": model, "api_base": api_base.rstrip("/")})

            direct_images = [image_1, image_2, image_3, image_4]
            dynamic_images = [value for name, value in kwargs.items() if name.startswith("image_")]
            references = collect_images(*direct_images, images, *dynamic_images, max_image_side=1024)
            frames = collect_video_frames(video, frame_count=8, sample_interval=1, max_image_side=1024)
            raw = chat_cloud(
                api_base,
                model,
                self._system(skill_name, instructions, shot_plan),
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
                history=[] if run_mode == "一次性输出" else self._history_messages(state),
            )
            analysis, result = self._split_result(raw)
            if run_mode == "一次性输出":
                state = self._empty_state()
                final_prompt = result
                phase = "single"
            else:
                state["confirmed"] = False
                state["confirmed_prompt"] = ""
                state["last_prompt"] = result
                state["shot_plan"] = shot_plan
                state["turns"].append({"user": user_prompt, "assistant": raw, "analysis": analysis, "prompt": result})
                state["turns"] = state["turns"][-self.MAX_TURNS:]
                final_prompt = ""
                phase = "conversation"
            status = {
                "ok": True,
                "mode": run_mode,
                "phase": phase,
                "skill": skill_name,
                "turns": len(state["turns"]),
                "confirmed": state["confirmed"],
                "video_duration": shot_plan["duration_seconds"],
                "cut_selection": shot_plan["selection"],
                "cut_count": shot_plan["cut_count"],
                "shot_count": shot_plan["shot_count"],
            }
            model_info = {"mode": "cloud", "model": model, "api_base": api_base.rstrip("/")}
            return self._result(analysis, result, final_prompt, state, status, model_info)
        except (ValueError, CloudError) as exc:
            raise RuntimeError(f"StariAI-MiniMaxH3-Chat：{exc}") from exc


NODE_CLASS_MAPPINGS = {
    "StariAI-MiniMaxH3-Skill": StariAI_MiniMaxH3_Skill,
    "StariAI-MiniMaxH3-Chat": StariAI_MiniMaxH3_Chat,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "StariAI-MiniMaxH3-Skill": "StariAI-MiniMaxH3-Skill",
    "StariAI-MiniMaxH3-Chat": "StariAI-MiniMaxH3-Chat",
}
