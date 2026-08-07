from __future__ import annotations

import base64
from typing import Any

import requests
from PIL import Image

from .media import image_bytes
from .secrets import get_api_key


class CloudError(RuntimeError):
    pass


def _image_part(image: Image.Image, label: str) -> list[dict[str, Any]]:
    encoded = base64.b64encode(image_bytes(image)).decode("ascii")
    return [
        {"type": "text", "text": label},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
    ]


def chat_cloud(api_base: str, model: str, system: str, prompt: str,
               images: list[Image.Image], video_frames: list[Image.Image],
               temperature: float, top_p: float, max_tokens: int,
               repetition_penalty: float, api_key: str = "",
               proxy_url: str = "", timeout: int = 120) -> str:
    key = (api_key or "").strip() or get_api_key()
    if not key:
        raise CloudError(
            "API Key 未配置。请在节点「API 密钥」输入框填入密钥（一次性，不会随工作流保存），"
            "或设置环境变量 SKILLBRIDGE_API_KEY / 插件目录 .env（见 README）。"
        )
    if not api_base.strip() or not model.strip():
        raise CloudError("云端模式必须填写 api_base 和 model")

    content: list[dict[str, Any]] = []
    for index, image in enumerate(images, 1):
        content.extend(_image_part(image, f"参考图 {index}："))
    for index, frame in enumerate(video_frames, 1):
        content.extend(_image_part(frame, f"视频帧 {index}："))
    content.append({"type": "text", "text": prompt})

    endpoint = api_base.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    payload = {
        "model": model.strip(),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "temperature": float(temperature),
        "top_p": float(top_p),
        "max_tokens": int(max_tokens),
        "repetition_penalty": float(repetition_penalty),
    }
    session = requests.Session()
    session.trust_env = False
    proxies = {"http": proxy_url.strip(), "https": proxy_url.strip()} if proxy_url.strip() else None
    try:
        response = session.post(
            endpoint,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            json=payload,
            proxies=proxies,
            timeout=max(5, int(timeout)),
        )
    except requests.Timeout as exc:
        raise CloudError(f"API 请求超时（{timeout} 秒）") from exc
    except requests.RequestException as exc:
        raise CloudError(f"API 网络错误：{exc}") from exc
    if response.status_code >= 400:
        raise CloudError(f"API 返回 HTTP {response.status_code}：{response.text[:500].replace(key, '[REDACTED]')}")
    try:
        result = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise CloudError("API 返回格式不是 OpenAI Chat Completions 格式") from exc
    if not isinstance(result, str) or not result.strip():
        raise CloudError("API 返回了空内容")
    return result.strip()
