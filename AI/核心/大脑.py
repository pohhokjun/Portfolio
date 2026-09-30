"""全项目唯一跑模型的地方（claude_agent_sdk）。

框架就是 Claude Code 的框架：循环、内置工具、上下文压缩、session、子 agent 都由它管。
换大脑只是换请求发去哪：本机登录 / Anthropic API / OpenAI 兼容网关，见 环境.大脑。
一单崩了（进程挂、网络断）同一大脑重试 环境.重试 次，再按 环境.备用大脑 顺序换；
轮数/预算到顶这种不是故障，不重试。
"""
import asyncio
import json
import os
import re
import time

from claude_agent_sdk import ClaudeAgentOptions, query

import 环境
from 核心 import 业务, 安全, 审批, 工具, 监控, 轨迹, 闸门, 附件 as 附件库
from 核心 import 缓存 as 缓存库

_会话文件 = 环境.记忆 / "会话.json"


class 配置错(Exception):
    pass


def _子环境(脑: str) -> dict:
    env = dict(环境.子环境)
    if 脑 == "本机":
        if os.environ.get("ANTHROPIC_API_KEY"):
            env["ANTHROPIC_API_KEY"] = ""          # 别让外面的 Key 把订阅登录顶掉
    elif 脑 == "api":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise 配置错("大脑=api 要设 ANTHROPIC_API_KEY")
        env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
    elif 脑 == "兼容":
        if not 环境.兼容["密钥"]:
            raise 配置错("大脑=兼容 要设 COMPAT_API_KEY（以及 COMPAT_BASE_URL / COMPAT_MODEL）")
        from 核心 import 网关
        网关.起来()
        env.update(ANTHROPIC_BASE_URL=f"http://127.0.0.1:{环境.兼容['端口']}", ANTHROPIC_API_KEY="gateway")
    else:
        raise 配置错(f"不认识的大脑：{脑}（本机 / api / 兼容）")
    return env


def 格式问题(schema) -> str:
    """结构化输出在 SDK 里是当工具实现的，字段名只能是英文/数字/_.-（中文会让整单 400）。→ 问题描述，空 = 没问题"""
    if not isinstance(schema, dict):
        return "输出格式要是 JSON schema 对象"
    坏 = []

    def 走(s):
        if isinstance(s, dict):
            坏.extend(k for k in (s.get("properties") or {}) if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", k))
            for v in s.values():
                走(v)
        elif isinstance(s, list):
            for v in s:
                走(v)
    走(schema)
    return f"输出格式的字段名要用英文（字母数字 _ . -），这些不行：{'、'.join(坏)}" if 坏 else ""


def _cli():
    return 环境.CLI if 环境.CLI.exists() else None     # 没装本机 Claude Code 就用 SDK 自带的


def _读会话() -> dict:
    try:
        return json.loads(_会话文件.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def _跑(脑: str, 单: dict, 接上: str | None) -> dict:
    r = {"编号": 单["编号"], "回复": "", "session": None, "轮数": 0, "花费": 0.0, "出错": None, "不重试": False, "模型": "",
         "大脑": 脑, "结构化": None}
    try:
        外部 = 业务.外部mcp()
        选项 = ClaudeAgentOptions(
            cli_path=_cli(), model=环境.模型, system_prompt=业务.人设(), allowed_tools=环境.工具 + [f"mcp__{n}" for n in 外部],
            permission_mode=环境.权限模式, mcp_servers={"biz": 工具.服务(单), **外部}, strict_mcp_config=True,
            hooks=闸门.钩子(单), agents=业务.团队(), effort=环境.档位["effort"], max_turns=环境.档位["max_turns"],
            max_budget_usd=环境.单笔上限, resume=接上, cwd=str(环境.工作区),
            output_format={"type": "json_schema", "schema": 单["输出格式"]} if 单.get("输出格式") else None,
            setting_sources=[],            # 不读任何 CLAUDE.md / 全局设置，框架自成一体，别人改设置不影响它
            env=_子环境(脑))
        async with asyncio.timeout(环境.单笔超时):
            async for 消息 in query(prompt=附件库.提问(单["需求"], 单["附件"]), options=选项):
                名 = type(消息).__name__
                if 名 == "AssistantMessage":
                    r["轮数"] += 1
                    r["模型"] = getattr(消息, "model", "") or r["模型"]
                    动作, 说明 = "说", ""
                    for 块 in 消息.content:
                        种 = type(块).__name__
                        if 种 == "TextBlock":
                            说明 = 块.text[:200]
                        elif 种 == "ToolUseBlock":
                            动作, 说明 = 块.name, json.dumps(块.input, ensure_ascii=False)[:200]
                            单["工具"].append(块.name)
                    轨迹.记(单["编号"], "一轮", 轮=r["轮数"], 动作=动作, 说明=说明, 子=bool(getattr(消息, "parent_tool_use_id", None)))
                    轨迹.心跳(忙着=True, 编号=单["编号"], 需求=单["需求"][:120], 开工=单["开工"], 花费=r["花费"])
                elif 名 == "ResultMessage":
                    r["回复"] = 消息.result or ""
                    r["session"] = 消息.session_id
                    r["花费"] = 消息.total_cost_usd or 0.0
                    r["结构化"] = 消息.structured_output
                    if 消息.is_error:
                        r["出错"] = {"error_max_turns": "轮数到上限", "error_max_budget_usd": "这单花费到上限",
                                   "error_max_structured_output_retries": "结构化输出几次都不合格"}.get(
                            消息.subtype, f"{消息.subtype}: {'; '.join(消息.errors or [])[:300]}")
                        r["不重试"] = 消息.subtype in ("error_max_turns", "error_max_budget_usd")
    except TimeoutError:
        r["出错"], r["不重试"] = f"超时（超过 {环境.单笔超时} 秒，到上限）", True
    except 配置错 as e:
        r["出错"], r["不重试"] = str(e), True
    except Exception as e:
        r["出错"] = f"{type(e).__name__}: {e}"[:500]
        r["不重试"] = "API Error: 400" in str(e)       # 请求本身不合法，重试换大脑都没用
    return r


async def 跑一单(需求: str, 会话: str | None = None, 来源: str = "命令行", 编号: str | None = None,
              输出格式: dict | None = None, 缓存: bool = False, 附件: list[str] | None = None) -> dict:
    """跑完一单。→ 结果 dict（含 交付、结构化）
    会话：同一个人/群的键，带上就接着上次的对话做。输出格式：JSON schema，要业务系统直接用的结构化结果时给。
    缓存：纯问答可以用上次几乎一样问题的答案（见 核心/缓存.py）。附件：已存盘的文件路径，图片直接给模型看（见 核心/附件.py）。"""
    编号 = 编号 or 轨迹.下一号()
    单 = {"编号": 编号, "需求": 需求, "来源": 来源, "会话": 会话, "交付": [], "工具": [], "开工": time.time(), "输出格式": 输出格式,
          "附件": 附件 or []}
    业务.模块()
    轨迹.记(编号, "开工", 需求=需求[:500], 大脑=环境.大脑, 来源=来源, 会话=会话 or "", 人设=业务.人设版本(),
           附件=[p.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for p in 单["附件"]])
    轨迹.心跳(忙着=True, 编号=编号, 需求=需求[:120], 开工=单["开工"])
    if 片段 := 安全.疑似注入(需求):
        轨迹.记(编号, "疑似注入", 位置="需求", 片段=片段)
        await 监控.告警("安全", f"{编号} 需求里疑似提示词注入：「{片段}」（来源 {来源}）")
    底 = {"编号": 编号, "回复": "", "session": None, "轮数": 0, "花费": 0.0, "大脑": 环境.大脑, "模型": "", "出错": None, "结构化": None}
    重试 = False

    if 缓存 and not 输出格式 and not 附件 and (命中 := 缓存库.查(需求)):
        r = {**底, "回复": 命中["回复"], "缓存": 命中["来自"]}
        单["交付"] = 命中["交付"]
        轨迹.记(编号, "缓存命中", 来自=命中["来自"], 相似=命中["相似"])
    elif 输出格式 and (问题 := 格式问题(输出格式)):
        r = {**底, "出错": 问题}
    elif (已花 := 轨迹.今日花费()) >= 环境.每日上限:
        r = {**底, "出错": f"今天已花 ${已花:.2f}，到每日上限 ${环境.每日上限}，不接新单"}
    else:
        会话表 = _读会话()
        上次 = 会话表.get(会话) if 会话 else None
        for 脑 in [环境.大脑, *[b for b in 环境.备用大脑 if b != 环境.大脑]]:
            接上 = 上次["session"] if 上次 and 上次.get("大脑") == 脑 else None   # session 不跨大脑
            for 次 in range(环境.重试 + 1):
                r = await _跑(脑, 单, 接上)
                if not r["出错"] or r["不重试"]:
                    break
                重试 = True
                轨迹.记(编号, "重试", 大脑=脑, 次=次 + 1, 出错=r["出错"])
                接上 = None                     # 接回可能就是出错原因，重试开新对话
            if not r["出错"] or "上限" in r["出错"]:
                break
            重试 = True
            轨迹.记(编号, "换大脑", 从=脑, 出错=r["出错"])
        if 会话 and r["session"]:
            会话表 = _读会话()                  # 重读：并发时别的单可能刚写过，整表写回会冲掉它
            会话表[会话] = {"session": r["session"], "大脑": r["大脑"], "时间": time.strftime("%Y-%m-%d %H:%M")}
            _会话文件.write_text(json.dumps(会话表, ensure_ascii=False, indent=1), encoding="utf-8")

    r["交付"], r["工具"] = 单["交付"], sorted(set(单["工具"]))
    r.update(审批.统计.pop(编号, {}))
    if 缓存 and not 附件 and not r.get("缓存"):
        缓存库.存(需求, r)
    耗时 = round(time.time() - 单["开工"])
    轨迹.记(编号, "崩" if r["出错"] else "收尾", 轮数=r["轮数"], 耗时=耗时, 花费=r["花费"], 模型=r.get("模型", ""),
           出错=r["出错"] or "", 原因=(r["出错"] or r["回复"])[:200])
    轨迹.存档(编号, 需求=需求[:500], 日期=time.strftime("%Y-%m-%d"), 时间=time.strftime("%H:%M:%S"), 来源=来源,
            大脑=r.get("大脑"), 模型=r.get("模型", ""), 人设=业务.人设版本(), 轮数=r["轮数"], 耗时=耗时, 花费=r["花费"],
            session=r["session"] or "", 结果="出错" if r["出错"] else "成", 出错=r["出错"] or "", 交付=r["交付"], 工具=r["工具"],
            回复=r["回复"][:2000], 结构化=r.get("结构化"), 重试=重试, 缓存=r.get("缓存", ""),
            **{k: r.get(k, 0) for k in ("人工次数", "审批次数", "审批通过")})
    轨迹.心跳(忙着=False)
    await 监控.单后检查(r)
    return r


async def 问一句(提示: str, 系统: str = "只按要求输出，别的不要写。") -> str:
    """不带工具的单轮问答：压缩记忆、评测打分这类小活用。"""
    选项 = ClaudeAgentOptions(cli_path=_cli(), model=环境.模型, system_prompt=系统, allowed_tools=[], tools=[],
                          permission_mode=环境.权限模式, max_turns=1, setting_sources=[], strict_mcp_config=True,
                          cwd=str(环境.临时), env=_子环境(环境.大脑))
    答 = ""
    async for 消息 in query(prompt=提示, options=选项):
        if type(消息).__name__ == "ResultMessage":
            答 = 消息.result or ""
    return 答
