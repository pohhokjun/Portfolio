"""服务模式的调度：单子排队，环境.并发 个工人同时跑；同一会话加锁一单接一单（并发续同一 session 上下文会乱）。
定时到点开单、每 15 秒心跳。
跑完按 来源 前缀投递回去（tg:… 由电报通道注册投递函数；网页的自己来查）。
"""
import asyncio
import contextlib
import time

import 环境
from 核心 import 大脑, 定时, 流程, 轨迹

队列: asyncio.Queue = None
结果: dict[str, dict] = {}        # 编号 → 跑完的结果（网页查）
在跑: dict[str, str] = {}         # 编号 → 需求
投递: dict = {}                   # 来源前缀 → async f(来源, 结果)
_已排定时: set = set()
_会话锁: dict[str, asyncio.Lock] = {}


async def 提交(需求: str, 会话: str | None = None, 来源: str = "网页", 定时id: str = "",
             输出格式: dict | None = None, 缓存: bool = False, 附件: list[str] | None = None) -> str:
    编号 = 轨迹.下一号()
    选项 = {"会话": 会话, "定时id": 定时id, "输出格式": 输出格式, "缓存": 缓存, "附件": 附件 or []}
    轨迹.存档(编号, 需求=需求[:500], 日期=time.strftime("%Y-%m-%d"), 时间=time.strftime("%H:%M:%S"), 来源=来源, 结果="排队",
            续做={"需求": 需求, **选项})   # 停机了重启按它接着做
    await 队列.put((编号, 需求, 来源, 选项))
    return 编号


async def 跑流程(名: str, 输入: dict, 来源: str, 号: str | None = None) -> dict:
    """流程不排队（步骤里的 agent 各自花钱各自记），但算进「在跑」，看板和 SSE 才认得。"""
    号 = 号 or 轨迹.下一号("F")
    在跑[号] = f"流程 {名}"
    try:
        return await 流程.跑(名, 输入, 来源=来源, 号=号)
    finally:
        在跑.pop(号, None)


async def 等(编号: str, 超时: float) -> dict | None:
    """同步调用用：等这单跑完拿结果，超时回 None（单子照样在跑）。"""
    for _ in range(int(超时 * 2)):
        if 编号 in 结果:
            return 结果[编号]
        await asyncio.sleep(0.5)
    return None


async def _工人():
    while True:
        编号, 需求, 来源, 选项 = await 队列.get()
        定时id = 选项.get("定时id", "")
        在跑[编号] = 需求
        会话 = 选项.get("会话")
        try:
            async with _会话锁.setdefault(会话, asyncio.Lock()) if 会话 else contextlib.nullcontext():
                r = await 大脑.跑一单(需求, 会话=会话, 来源=来源, 编号=编号,
                                  输出格式=选项.get("输出格式"), 缓存=bool(选项.get("缓存")), 附件=选项.get("附件"))
            结果[编号] = r
            if 定时id and not r["出错"]:
                定时.删(定时id)
            if f := 投递.get(来源.split(":")[0]):
                await f(来源, r)
        except Exception as e:
            轨迹.记(编号, "崩", 出错=f"调度：{type(e).__name__}: {e}")
        finally:
            在跑.pop(编号, None)
            _已排定时.discard(定时id)
            队列.task_done()


async def _定时():
    while True:
        for x in 定时.到期():
            if x.get("流程"):
                asyncio.create_task(跑流程(x["流程"], x.get("输入") or {}, 来源="定时"))
                continue
            if x["id"] and x["id"] in _已排定时:
                continue
            _已排定时.add(x["id"])
            await 提交(f"到点了，之前安排的：{x['需求']}", 会话=x.get("来源") or None,
                     来源=x.get("来源") or "定时", 定时id=x["id"])
        await asyncio.sleep(30)


async def _心跳():
    while True:
        编号 = next(iter(在跑), "")
        轨迹.心跳(忙着=bool(在跑), 编号=编号, 需求=在跑.get(编号, "")[:120], 队列=队列.qsize(), 在跑=list(在跑))
        await asyncio.sleep(15)


async def 开():
    """起工人、定时、心跳；上次停机时排着队或做到一半的单（台账里还是「排队」）重新排上。"""
    global 队列
    队列 = asyncio.Queue()
    for 编号, u in sorted(轨迹.读台账().get("单", {}).items()):
        if u.get("结果") == "排队" and not u.get("续做"):          # 流程这类没法续的，标成中断，别一直显示排队
            轨迹.存档(编号, 结果="出错", 出错="停机中断")
        elif u.get("结果") == "排队" and (续 := u.get("续做")):
            轨迹.记(编号, "续做")
            await 队列.put((编号, 续.pop("需求"), u.get("来源", "网页"), 续))
            if 续.get("定时id"):
                _已排定时.add(续["定时id"])
    return [asyncio.create_task(c) for c in [_工人() for _ in range(环境.并发)] + [_定时(), _心跳()]]
