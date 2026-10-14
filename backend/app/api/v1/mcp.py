import json

from fastapi import APIRouter, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["mcp"])
PROTOCOL = "2025-06-18"
TOOLS = [
    {
        "name": "list_subscriptions",
        "description": "List saved anime subscriptions",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_downloads",
        "description": "List managed download states",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "refresh_feed",
        "description": "Refresh one feed using its saved download rules",
        "inputSchema": {
            "type": "object",
            "properties": {"feed_id": {"type": "integer", "minimum": 1}},
            "required": ["feed_id"],
        },
    },
]


class RpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str = Field(max_length=100)
    params: dict = Field(default_factory=dict)


@router.post("/mcp")
async def mcp(body: RpcRequest, request: Request):
    user = getattr(request.state, "principal", None)
    if (
        not user
        or user.get("kind") != "token"
        or not request.headers.get("Authorization", "").startswith("Bearer ")
    ):
        return JSONResponse(
            {"error": "API token required"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
        )

    def error(code, message):
        return {"jsonrpc": "2.0", "id": body.id, "error": {"code": code, "message": message}}

    if body.jsonrpc != "2.0":
        return error(-32600, "Invalid JSON-RPC version")
    if body.method.startswith("notifications/"):
        return Response(status_code=202)
    service = request.app.state.container.automation_service
    if body.method == "initialize":
        result = {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "CyMediaFlow", "version": "0.2.0"},
        }
    elif body.method == "ping":
        result = {}
    elif body.method == "tools/list":
        result = {"tools": TOOLS}
    elif body.method == "resources/list":
        result = {
            "resources": [
                {
                    "uri": "cymediaflow://calendar",
                    "name": "Subscription calendar",
                    "mimeType": "application/json",
                }
            ]
        }
    elif body.method == "resources/read":
        if body.params.get("uri") != "cymediaflow://calendar":
            return error(-32602, "Unknown resource")
        result = {
            "contents": [
                {
                    "uri": "cymediaflow://calendar",
                    "mimeType": "application/json",
                    "text": json.dumps(
                        request.app.state.container.automation_updates.calendar(),
                        ensure_ascii=False,
                    ),
                }
            ]
        }
    elif body.method == "tools/call":
        name = body.params.get("name")
        if name == "list_subscriptions":
            data = service.list_subscriptions()
        elif name == "list_downloads":
            data = [
                {
                    "id": j.id,
                    "state": j.state,
                    "progress": j.progress,
                    "title": j.naming_json.get("title"),
                }
                for j in service._repo.list_downloads()
            ]
        elif name == "refresh_feed":
            if user["role"] == "viewer" or user["scope"] not in {"all", "automation"}:
                return error(-32602, "Token does not permit downloads")
            arguments = body.params.get("arguments", {})
            if not isinstance(arguments, dict):
                return error(-32602, "arguments must be an object")
            feed_id = arguments.get("feed_id")
            if type(feed_id) is not int or feed_id < 1:
                return error(-32602, "feed_id must be a positive integer")
            try:
                data = await service.refresh_feed(feed_id)
            except Exception:
                result = {
                    "isError": True,
                    "content": [{"type": "text", "text": "Feed refresh failed"}],
                }
                return {"jsonrpc": "2.0", "id": body.id, "result": result}
        else:
            return error(-32602, "Unknown tool")
        result = {
            "content": [
                {"type": "text", "text": json.dumps(jsonable_encoder(data), ensure_ascii=False)}
            ]
        }
    else:
        return error(-32601, "Method not found")
    return {"jsonrpc": "2.0", "id": body.id, "result": result}
