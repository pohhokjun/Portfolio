"""把这个业务开放成 MCP 服务（stdio）：Claude Code / Claude Desktop / 别的 agent 能直接用。
`python Work.py mcp` 起；客户端配置：{"command": "python", "args": ["<路径>/Work.py", "mcp"], "env": {"BIZ": "示例"}}

开放：只读工具（查知识库、看表、读网页…）+ run_task（整单交给这个业务 agent 做）+ run_flow（跑固定流程）。
不开放：高风险工具、要「当前这单」上下文的工具（deliver、ask_human、schedule…）——那些只在 agent 自己的单里用。
"""
import inspect

from mcp.server.mcpserver import MCPServer

import 环境
from 核心 import 业务, 大脑, 审批, 工具, 流程

业务.模块()
server = MCPServer(f"biz-{环境.业务名}", instructions=f"「{环境.业务名}」业务 agent：查资料、做单、跑流程。")

for 名, 项 in 工具.注册表.items():
    if not 项["高风险"] and "单" not in inspect.signature(项["fn"]).parameters and 名 not in ("remember", "cancel_schedule"):   # 会改数据的不开放
        server.tool(name=名, description=项["描述"])(项["fn"])


@server.tool(name="run_task", description=f"把一件事整单交给「{环境.业务名}」业务 agent 做，返回交付的文字和文件路径。会花模型额度。")
async def 做单(task: str) -> dict:
    审批.自动 = {"批": False, "答": ""}     # MCP 调用方没法回审批，高风险一律拒，agent 会说明
    try:
        r = await 大脑.跑一单(task, 来源="MCP")
    finally:
        审批.自动 = None
    return {"编号": r["编号"], "出错": r["出错"], "交付": r["交付"], "回复": r["回复"][:4000]}


@server.tool(name="run_flow", description="跑一个固定流程。flows 看有哪些；inputs 是流程要的输入。审批步骤会被拒绝。")
async def 跑流程(name: str, inputs: dict | None = None) -> dict:
    审批.自动 = {"批": False, "答": ""}
    try:
        return await 流程.跑(name, inputs or {}, 来源="MCP")
    finally:
        审批.自动 = None


@server.tool(name="flows", description="列出这个业务有哪些固定流程。")
def 列流程() -> dict:
    return 业务.流程()
