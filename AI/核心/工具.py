"""工具注册：业务写个函数、加 @工具，就成了 agent 能调的工具（mcp__biz__<名>），跟 Claude Code 调 Bash 一样。

- 名字和参数名用英文（MCP 接口不收中文），描述写中文给模型看。
- 能用代码查的规矩（格式、范围、路径、业务规则）在函数里查，不合格 raise 退回("原因")，原因回喂给模型让它改。
- 高风险=True：每次调用先等人批准（网页/TG/终端），拒了模型会收到理由。
- 函数参数里写 单 就会注入当前这单（编号、需求、来源、交付…），不进 schema。
- 同步函数放线程里跑，不卡住其他单。
"""
import asyncio
import inspect
import json
import time
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

import 环境
from 核心 import 业务, 安全, 审批, 定时, 知识库, 记忆, 轨迹


class 退回(Exception):
    """参数或业务规则不对。原因会原样给模型。"""


注册表: dict[str, dict] = {}


def 工具(名: str, 描述: str, 参数: dict | None = None, 高风险: bool = False):
    """参数：{"path": str, "n": int} 简写（全部必填），或完整 JSON schema（要可选参数时用）。"""
    def 装(fn):
        注册表[名] = {"fn": fn, "描述": 描述, "参数": 参数 or {}, "高风险": 高风险}
        return fn
    return 装


def _文(出) -> str:
    return 出 if isinstance(出, str) else json.dumps(出, ensure_ascii=False, default=str)


def 服务(单: dict):
    """给这一单造一个 MCP server：工具闭包里带着 单，审批和轨迹知道是哪单。"""
    def 包(名, 项):
        要单 = "单" in inspect.signature(项["fn"]).parameters

        async def 跑(args):
            t0 = time.time()
            try:
                if 项["高风险"]:
                    ok, 备注 = await 审批.请求(单["编号"], "批", f"{名} {_文(args)[:500]}")
                    if not ok:
                        raise 退回(f"没批准{'：' + 备注 if 备注 else ''}。别重试同样的操作，换做法或用 ask_human 问清楚。")
                kw = {**args, **({"单": 单} if 要单 else {})}
                出 = await 项["fn"](**kw) if inspect.iscoroutinefunction(项["fn"]) else await asyncio.to_thread(项["fn"], **kw)
                文, 错 = _文(出), False
            except 退回 as e:
                文, 错 = str(e), True
            except Exception as e:
                文, 错 = f"{type(e).__name__}: {e}", True
            单.setdefault("工具", []).append(名)
            轨迹.记(单["编号"], "工具", 名=名, 参数=_文(args)[:300], 出错=错, 结果=文[:200], 用时=round(time.time() - t0, 2))
            return {"content": [{"type": "text", "text": 文[:30000]}], **({"is_error": True} if 错 else {})}
        return tool(名, 项["描述"], 项["参数"])(跑)

    return create_sdk_mcp_server("biz", tools=[包(n, x) for n, x in 注册表.items()])


# ── 框架自带的工具，每个业务都有 ─────────────────────────

@工具("search_kb", "查业务知识库（口径、规则、说明、资料）。拿不准的业务定义先查这里，回答里写上出处。",
      {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer", "default": 5}}, "required": ["query"]})
def 查资料(query: str, k: int = 5):
    结果 = 知识库.查(query, min(max(k, 1), 10))
    return 结果 or "知识库里没有相关内容。"


@工具("remember", "记住业务方的长期要求（格式、口径、称呼、习惯），以后每单都会遵守。一次性的事不要记，30 字以内。", {"content": str})
async def 记住(content: str):
    if len(content) > 60:
        raise 退回("太长了，压到 30 字左右，只写要求本身。")
    return await 记忆.记住(content)


@工具("schedule", "定时做一件事：到点自动开一单。time 支持 2026-10-01 09:00、09:00、+30m、+2h、+1d。", {"time": str, "task": str})
def 定时做(time: str, task: str, 单):
    条 = 定时.加(time, task, 来源=单["来源"])
    return f"好，{条['时间']} 做：{task}（编号 {条['id']}）"


@工具("list_schedule", "看还没做的定时任务。", {})
def 看定时():
    return 定时.列表() or "没有待办。"


@工具("cancel_schedule", "取消一个定时任务。", {"id": str})
def 取消定时(id: str):
    if not any(x["id"] == id for x in 定时.列表()):
        raise 退回(f"没有 {id}，先 list_schedule 看编号。")
    定时.删(id)
    return "取消了"


@工具("ask_human", "需求不清楚、缺信息、要人拍板时问人，会等对方回答。能自己查到的别问。", {"question": str})
async def 问人(question: str, 单):
    ok, 答 = await 审批.请求(单["编号"], "问", question)
    if not ok:
        raise 退回("没人回答。按最稳妥的理解做，并在交付时说明你的假设。")
    return 答


@工具("deliver", "交付给提需求的人：text 是要说的话，files 是工作区里要发的文件（相对或绝对路径）。做完一定要调。",
      {"type": "object", "properties": {"text": {"type": "string"}, "files": {"type": "array", "items": {"type": "string"}}},
       "required": ["text"]})
def 交付(text: str, 单, files: list | None = None):
    路径 = []
    for f in files or []:
        p = (环境.工作区 / f).resolve() if not Path(f).is_absolute() else Path(f).resolve()
        if 环境.工作区.resolve() not in p.parents:
            raise 退回(f"{f} 不在工作区里，只能交付工作区的文件。")
        if not p.is_file():
            raise 退回(f"{f} 不存在，先确认文件生成了。")
        路径.append(str(p))
    单.setdefault("交付", []).append({"文本": 安全.打码(text) if 业务.配置()["交付打码"] else text, "文件": 路径})
    return f"已交付（{len(路径)} 个文件）"


from 核心 import 浏览器  # noqa: E402,F401  注册 open_page / browser_run
