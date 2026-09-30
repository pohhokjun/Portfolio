"""人工介入：高风险操作等批准、agent 卡住时问人。两种都挂成「待办」，由通道（网页/TG/终端）回复。

没有通道在听（命令行一单）就直接在终端问。超时算拒绝，理由回喂给模型让它换做法。
"""
import asyncio
import itertools
import time

import 环境
from 核心 import 轨迹

待办: dict[str, dict] = {}
通知: list = []            # 通道注册的回调：async f(条目)，新待办出来就推给人
终端 = True                # 服务模式下由 Work.py 关掉，改走网页/TG
自动: dict | None = None   # 评测/测试用：{"批": True/False, "答": "…"}，不等人
_号 = itertools.count(1)
统计: dict[str, dict] = {}   # 编号 → {人工次数, 审批次数, 审批通过}，单收尾时 大脑 取走记进台账


def _算(编号, 类型, 结果):
    d = 统计.setdefault(编号, {"人工次数": 0, "审批次数": 0, "审批通过": 0})
    d["人工次数"] += 1
    if 类型 == "批":
        d["审批次数"] += 1
        d["审批通过"] += bool(结果[0])
    return 结果


async def 请求(编号: str, 类型: str, 内容: str, 超时: float | None = None) -> tuple[bool, str]:
    """类型：批（要批准）/ 问（要答案）。→ (通过/答了, 备注或答案)"""
    if 自动 is not None:
        结果 = (bool(自动.get("批")), "自动拒绝" if not 自动.get("批") else "") if 类型 == "批" else (bool(自动.get("答")), 自动.get("答", ""))
        轨迹.记(编号, "人工", 种=类型, 内容=内容[:300], 通过=结果[0], 回复=结果[1], 自动=True)
        return _算(编号, 类型, 结果)
    if 终端 and not 通知:
        提示 = f"\n[{编号}] 需要你{'批准' if 类型 == '批' else '回答'}：{内容}\n" + ("批准吗？[y/N] " if 类型 == "批" else "> ")
        答 = (await asyncio.to_thread(input, 提示)).strip()
        结果 = (答.lower() == "y", "") if 类型 == "批" else (bool(答), 答)
        轨迹.记(编号, "人工", 种=类型, 内容=内容[:300], 通过=结果[0], 回复=结果[1][:300])
        return _算(编号, 类型, 结果)

    号 = f"A{next(_号)}"
    条 = 待办[号] = {"号": 号, "编号": 编号, "类型": 类型, "内容": 内容, "时间": time.strftime("%H:%M:%S"),
                   "fut": asyncio.get_running_loop().create_future()}
    try:     # 不管哪步出错，finally 都把待办清掉，别留孤儿
        轨迹.记(编号, "等人", 号=号, 种=类型, 内容=内容[:300])
        for f in 通知:
            try:
                await f(公开(条))
            except Exception as e:
                轨迹.记(编号, "通知失败", 错=str(e)[:200])
        结果 = await asyncio.wait_for(条["fut"], 超时 or 环境.审批超时)
    except asyncio.TimeoutError:
        结果 = (False, "超时没人回，按拒绝处理")
    finally:
        待办.pop(号, None)
    轨迹.记(编号, "人工", 号=号, 种=类型, 通过=结果[0], 回复=结果[1][:300])
    return _算(编号, 类型, 结果)


def 回复(号: str, 通过: bool, 文本: str = "") -> bool:
    条 = 待办.get(号)
    if not 条 or 条["fut"].done():
        return False
    条["fut"].get_loop().call_soon_threadsafe(条["fut"].set_result, (通过, 文本))
    return True


def 公开(条: dict) -> dict:
    return {k: v for k, v in 条.items() if k != "fut"}


def 列表() -> list:
    return [公开(x) for x in 待办.values()]
