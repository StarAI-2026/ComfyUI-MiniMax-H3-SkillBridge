from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .h3_chain_runtime import (
    NODE_CLASS_MAPPINGS as _H3_RUNTIME_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _H3_RUNTIME_DISPLAY_NAME_MAPPINGS,
)

NODE_CLASS_MAPPINGS.update(_H3_RUNTIME_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(_H3_RUNTIME_DISPLAY_NAME_MAPPINGS)


def _install_h3_chain_runtime() -> None:
    try:
        from server import PromptServer
        from .h3_graph_injection import inject_h3_chain
        from .h3_routes import register_routes

        server = getattr(PromptServer, "instance", None)
        if server is None:
            return

        def on_prompt(json_data):
            prompt = json_data.get("prompt") if isinstance(json_data, dict) else None
            if not isinstance(prompt, dict):
                return json_data
            client_id = json_data.get("client_id")
            json_data = dict(json_data)
            json_data["prompt"] = inject_h3_chain(prompt, str(client_id) if client_id else None)
            return json_data

        if not getattr(server, "_stariai_h3_chain_prompt_handler", False):
            server.add_on_prompt_handler(on_prompt)
            server._stariai_h3_chain_prompt_handler = True
        register_routes()
    except Exception as error:
        # ComfyUI can import custom nodes before its HTTP server exists. The
        # node classes remain available; the next restart installs the handler.
        print(f"[SkillBridge] H3 chain runtime unavailable during startup: {error}")


_install_h3_chain_runtime()

WEB_DIRECTORY = "./web"
__version__ = "1.3.0"
__author__ = "StarAI"
__author_id__ = "StariAI"
__author_site__ = "https://staraigc.top"
__author_bilibili__ = "https://space.bilibili.com/495356821"
__author_youtube__ = "https://www.youtube.com/@StarAIGC"
__author_qq_group__ = "https://qm.qq.com/q/lge501JeLY"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
    "__version__",
    "__author__",
    "__author_id__",
    "__author_site__",
    "__author_bilibili__",
    "__author_youtube__",
    "__author_qq_group__",
]
