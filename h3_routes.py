"""Small control plane for the existing Skill/Chat nodes' hidden H3 chains."""

from __future__ import annotations

from aiohttp import web

from .h3_chain_runtime import (
    CHAINS,
    control_cancel_chain,
    control_pause_chain,
    queue_resumed_chain,
)


def _payload_status(chain_id: str) -> web.Response:
    return web.json_response(CHAINS.status_or_detached(chain_id))


def register_routes() -> None:
    try:
        from server import PromptServer
    except ImportError:
        return
    server = getattr(PromptServer, "instance", None)
    if server is None or getattr(server, "_stariai_h3_chain_routes", False):
        return

    @server.routes.get("/stariai/h3-chain/{chain_id}")
    async def status(request):
        try:
            return _payload_status(request.match_info["chain_id"])
        except Exception as error:
            return web.json_response({"error": str(error)}, status=404)

    @server.routes.post("/stariai/h3-chain/{chain_id}/pause")
    async def pause(request):
        try:
            return web.json_response(control_pause_chain(request.match_info["chain_id"]))
        except Exception as error:
            return web.json_response({"error": str(error)}, status=400)

    @server.routes.post("/stariai/h3-chain/{chain_id}/resume")
    async def resume(request):
        try:
            return web.json_response(queue_resumed_chain(request.match_info["chain_id"]))
        except Exception as error:
            return web.json_response({"error": str(error)}, status=400)

    @server.routes.post("/stariai/h3-chain/{chain_id}/cancel")
    async def cancel(request):
        try:
            return web.json_response(control_cancel_chain(request.match_info["chain_id"]))
        except Exception as error:
            return web.json_response({"error": str(error)}, status=400)

    server._stariai_h3_chain_routes = True
