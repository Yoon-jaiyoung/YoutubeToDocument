"""외부 MCP 서버 관리 (추가/삭제/도구 조회/실행)"""
import json
import os

MCP_SERVERS_FILE = "mcp_servers.json"


def load_servers() -> list:
    if not os.path.exists(MCP_SERVERS_FILE):
        return []
    with open(MCP_SERVERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_servers(servers: list):
    with open(MCP_SERVERS_FILE, "w", encoding="utf-8") as f:
        json.dump(servers, f, ensure_ascii=False, indent=2)


async def list_tools(server_name: str) -> list:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    servers = load_servers()
    server  = next((s for s in servers if s["name"] == server_name), None)
    if not server:
        raise ValueError(f"서버 '{server_name}'를 찾을 수 없습니다.")

    env    = {**os.environ, **(server.get("env") or {})}
    params = StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema,
                    "server": server_name,
                    "server_label": server.get("label", server_name),
                }
                for t in result.tools
            ]


async def call_tool(server_name: str, tool_name: str, args: dict, queue) -> None:
    """MCP 서버 도구 실행 — 결과를 asyncio Queue에 push"""
    import asyncio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    servers = load_servers()
    server  = next((s for s in servers if s["name"] == server_name), None)
    if not server:
        await queue.put({"type": "error", "message": f"서버 '{server_name}'를 찾을 수 없습니다."})
        return

    env    = {**os.environ, **(server.get("env") or {})}
    params = StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        env=env,
    )
    try:
        await queue.put({"type": "log", "text": f"MCP 서버 '{server['label']}' 연결 중..."})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await queue.put({"type": "log", "text": f"도구 '{tool_name}' 실행 중..."})
                result = await session.call_tool(tool_name, args)
                text_result = "\n".join(
                    block.text for block in result.content if hasattr(block, "text")
                )
                await queue.put({
                    "type": "result",
                    "data": {
                        "type": "mcp_result",
                        "content": text_result,
                        "server": server_name,
                        "tool": tool_name,
                    },
                })
    except Exception as e:
        await queue.put({"type": "error", "message": str(e)})
