"""HTTP API + 看板。业务系统要接 agent 就调这里。

POST /api/task              {"需求"/"task", "会话"/"session", "输出格式"/"schema": JSON schema, "缓存"/"cache": bool,
                             "附件"/"files": [{"名"/"name", "数据"/"data": base64}]}（图片模型直接看）
                            → {"编号"}；带 ?wait=秒 就等做完直接回结果（超时回编号，单子照样跑）
GET  /api/task/{编号}        结果、交付、结构化结果、每一步轨迹
GET  /api/task/{编号}/stream SSE 实时推每一步，做完推「完成」
GET  /api/flows              有哪些固定流程
POST /api/flow/{名}          {"输入"/"inputs": {...}} → {"编号"}（F 开头，同样用 /api/task/{编号} 查）
POST /api/approve/{号}       {"通过"/"ok": true/false, "文本"/"text": "理由或答案"}
GET  /api/status             心跳、队列、待批、定时、统计、评测
GET  /api/metrics            效果指标 + 最近告警
POST /api/kb/rebuild
路径和路由参数名用英文：别的系统直接发 UTF-8 中文路径会 404，Starlette 也不认中文参数名。
多用户：每人一个令牌（请求头 X-Token，或 ?token=，SSE 只能用后者），按权限放行，见 核心/用户.py。
提交类接口按令牌/IP 每分钟限 环境.限流 次；用户设了每日上限就按人封顶。
"""
import asyncio
import json
import time
from collections import defaultdict, deque
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

import 环境
from 核心 import 业务, 大脑, 审批, 定时, 用户, 知识库, 监控, 调度, 轨迹
from 核心 import 附件 as 附件库


def 要的权限(方法: str, 路径: str) -> str:
    if 方法 == "POST":
        for 前缀, 权限 in (("/api/task", "派活"), ("/api/flow", "流程"), ("/api/approve", "批准")):
            if 路径.startswith(前缀):
                return 权限
        return "管理"
    return "查看"


class 守门(BaseHTTPMiddleware):
    """认人 + 查权限 + 限流（只限会花钱的提交类接口）。"""
    记录 = defaultdict(deque)

    async def dispatch(self, req, nxt):
        if req.url.path.startswith("/api"):
            人 = 用户.认(req.headers.get("x-token") or req.query_params.get("token"))
            if not 人:
                return JSONResponse({"错": "令牌不对"}, 401)
            if (权限 := 要的权限(req.method, req.url.path)) not in 人["权限"]:
                return JSONResponse({"错": f"{人['名']} 没有「{权限}」权限"}, 403)
            req.state.人 = 人
        if req.method == "POST" and req.url.path.startswith(("/api/task", "/api/flow")):
            q, 现 = self.记录[req.headers.get("x-token") or (req.client.host if req.client else "-")], time.time()
            while q and q[0] < 现 - 60:
                q.popleft()
            if len(q) >= 环境.限流:
                return JSONResponse({"错": f"太频繁了，每分钟最多 {环境.限流} 次"}, 429)
            q.append(现)
        return await nxt(req)


async def _体(req) -> dict:
    try:
        b = await req.json()
        return b if isinstance(b, dict) else {}
    except json.JSONDecodeError:
        return {}


def _单(编号: str) -> dict | None:
    账 = 轨迹.读台账().get("单", {}).get(编号)
    return {**账, "在跑": 编号 in 调度.在跑, "轨迹": 轨迹.读(编号)} if 账 else None


async def 首页(req):
    return FileResponse(Path(__file__).with_name("看板.html"))


async def 提交(req):
    b = await _体(req)
    需求 = str(b.get("需求") or b.get("task") or "").strip()
    if not 需求:
        return JSONResponse({"错": "缺 需求"}, 400)
    格式 = b.get("输出格式") or b.get("schema")
    if 格式 is not None and (问题 := 大脑.格式问题(格式)):
        return JSONResponse({"错": 问题}, 400)
    try:
        附件 = 附件库.存base64(b.get("附件") or b.get("files") or [])
    except ValueError as e:
        return JSONResponse({"错": str(e)}, 400)
    人 = req.state.人
    if 人["每日上限"] and (花 := 用户.今日花费(人["名"])) >= 人["每日上限"]:
        return JSONResponse({"错": f"{人['名']} 今天已花 ${花:.2f}，到个人上限 ${人['每日上限']}"}, 429)
    会话 = b.get("会话") or b.get("session")
    编号 = await 调度.提交(需求[:20000], 会话=f"{人['名']}:{会话}" if 会话 else None, 来源=f"网页:{人['名']}",   # 会话按人隔开
                       输出格式=格式, 缓存=bool(b.get("缓存", b.get("cache"))), 附件=附件)
    if 等 := float(req.query_params.get("wait", 0)):
        if await 调度.等(编号, min(等, 环境.单笔超时)):
            return JSONResponse(_单(编号))
    return JSONResponse({"编号": 编号})


async def 查单(req):
    u = _单(req.path_params["id"])
    return JSONResponse(u) if u else JSONResponse({"错": f"没有 {req.path_params['id']}"}, 404)


async def 流(req):
    编号 = req.path_params["id"]
    if not 轨迹.读台账().get("单", {}).get(编号):
        return JSONResponse({"错": f"没有 {编号}"}, 404)

    async def 推():
        已发, 起 = 0, time.time()
        while time.time() - 起 < 环境.单笔超时:
            新 = 轨迹.读(编号)[已发:]
            for x in 新:
                yield f"event: 步骤\ndata: {json.dumps(x, ensure_ascii=False)}\n\n"
            已发 += len(新)
            u = 轨迹.读台账()["单"][编号]
            if u.get("结果") in ("成", "出错") and 编号 not in 调度.在跑:
                yield f"event: 完成\ndata: {json.dumps(u, ensure_ascii=False, default=str)}\n\n"
                return
            await asyncio.sleep(0.5)
    return StreamingResponse(推(), media_type="text/event-stream")


async def 流程列表(req):
    return JSONResponse(业务.流程())


async def 跑流程(req):
    名 = req.path_params["name"]
    try:
        业务.流程(名)
    except FileNotFoundError as e:
        return JSONResponse({"错": str(e)}, 404)
    b = await _体(req)
    号 = 轨迹.下一号("F")
    轨迹.存档(号, 需求=f"流程 {名}", 日期=time.strftime("%Y-%m-%d"), 时间=time.strftime("%H:%M:%S"), 来源="网页", 结果="排队")
    asyncio.create_task(调度.跑流程(名, b.get("输入") or b.get("inputs") or {}, 来源=f"网页:{req.state.人['名']}", 号=号))
    return JSONResponse({"编号": 号})


def _统计(单: list) -> dict:
    完 = [u for u in 单 if u.get("结果") in ("成", "出错")]
    今 = time.strftime("%Y-%m-%d")
    return {"总单数": len(完), "成功率": f"{sum(u['结果'] == '成' for u in 完) / len(完):.0%}" if 完 else "-",
            "今日单数": sum(u.get("日期") == 今 for u in 完), "今日花费": round(轨迹.今日花费(), 4), "每日上限": 环境.每日上限,
            "平均轮数": round(sum(u.get("轮数", 0) for u in 完) / len(完), 1) if 完 else 0,
            "总花费": round(sum(float(u.get("花费") or 0) for u in 完), 4)}


async def 状态(req):
    单 = list(轨迹.读台账().get("单", {}).values())
    try:
        心跳 = json.loads((环境.记忆 / "心跳.json").read_text(encoding="utf-8"))
    except Exception:
        心跳 = {}
    f = 环境.记忆 / "评测报告.json"
    return JSONResponse({"业务": 环境.业务名, "大脑": 环境.大脑, "我": req.state.人, "备用": 环境.备用大脑, "人设": 业务.人设版本(), "心跳": 心跳,
                         "在跑": 调度.在跑, "排队": 调度.队列.qsize() if 调度.队列 else 0, "待批": 审批.列表(),
                         "定时": 定时.列表(), "流程": 业务.流程(), "统计": _统计(单),
                         "最近": sorted(单, key=lambda u: u.get("时间", "") + u["编号"])[-30:][::-1],
                         "评测": json.loads(f.read_text(encoding="utf-8")) if f.exists() else None})


async def 指标(req):
    return JSONResponse({"指标": 监控.指标(), "告警": 监控.最近告警()})


async def 回待批(req):
    b = await _体(req)
    号, 通过, 文本 = req.path_params["id"], bool(b.get("通过", b.get("ok"))), str(b.get("文本") or b.get("text") or "")
    if 条 := 审批.待办.get(号):
        轨迹.记(条["编号"], "批复", 号=号, 人=req.state.人["名"], 通过=通过, 文本=文本[:300])   # 谁批的留痕
    ok = 审批.回复(号, 通过, 文本)
    return JSONResponse({"ok": ok}, 200 if ok else 404)


async def 重建知识(req):
    return JSONResponse({"块数": 知识库.重建()})


app = Starlette(routes=[
    Route("/", 首页), Route("/api/task", 提交, methods=["POST"]), Route("/api/task/{id}", 查单),
    Route("/api/task/{id}/stream", 流), Route("/api/flows", 流程列表), Route("/api/flow/{name}", 跑流程, methods=["POST"]),
    Route("/api/status", 状态), Route("/api/metrics", 指标), Route("/api/approve/{id}", 回待批, methods=["POST"]),
    Route("/api/kb/rebuild", 重建知识, methods=["POST"]),
], middleware=[Middleware(守门)])


async def 开():
    import uvicorn
    await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=环境.HTTP端口, log_level="warning")).serve()
