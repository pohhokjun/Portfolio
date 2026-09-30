"""「兼容」大脑：本地假装成 Anthropic 的 /v1/messages，翻译成 OpenAI 兼容的 /chat/completions 发出去
（DeepSeek / 通义 / OpenAI / Ollama…），回答再翻回 Anthropic 格式。Claude Code 那一整套照常用。

Claude Code 发 stream:true，所以要吐 SSE，事件顺序少一个对面就卡住。
工具调用两边都是原生的：tool_use ⇄ tool_calls，tool_result ⇄ role=tool。
"""
import json
import threading
import time
import uuid

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

import 环境

_起了 = False


def _文(c) -> str:
    if isinstance(c, str):
        return c
    return "\n".join(b.get("text", "") if b.get("type") == "text" else _文(b.get("content", "")) if b.get("type") == "tool_result"
                     else "" for b in c)


def 转请求(体: dict) -> dict:
    from 核心 import 业务, 安全
    消息 = []
    s = 体.get("system")
    s = "\n\n".join(b.get("text", "") for b in s if not b.get("text", "").startswith("x-anthropic-billing")) if isinstance(s, list) else s
    if s:
        消息.append({"role": "system", "content": s})
    for m in 体.get("messages", []):
        c = m["content"]
        if isinstance(c, str):
            消息.append({"role": m["role"], "content": c})
        elif m["role"] == "assistant":
            调 = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b["input"], ensure_ascii=False)}}
                 for b in c if b.get("type") == "tool_use"]
            消息.append({"role": "assistant", "content": _文([b for b in c if b.get("type") == "text"]) or None,
                       **({"tool_calls": 调} if 调 else {})})
        else:   # OpenAI 要求 tool 消息紧跟在 assistant 的 tool_calls 后面，所以先放工具结果再放文字
            图 = [b for b in c if b.get("type") == "image"]
            for b in c:
                if b.get("type") == "tool_result":
                    内 = b.get("content", "")
                    图 += [x for x in 内 if isinstance(x, dict) and x.get("type") == "image"] if isinstance(内, list) else []
                    消息.append({"role": "tool", "tool_call_id": b["tool_use_id"],
                               "content": (("【报错】" if b.get("is_error") else "") + _文(内)) or "（图片见下一条）"})
            文 = _文([b for b in c if b.get("type") == "text"])
            if 图:   # tool 消息放不了图片（Read 读图的结果也是图片块），统一挪到后面一条 user 消息里
                消息.append({"role": "user", "content": [{"type": "text", "text": 文 or "（图片）"}] + [
                    {"type": "image_url", "image_url": {"url": f"data:{x['source']['media_type']};base64,{x['source']['data']}"}}
                    for x in 图 if x.get("source", {}).get("type") == "base64"]})
            elif 文:
                消息.append({"role": "user", "content": 文})
    工具 = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", "")[:1024],
                                             "parameters": t["input_schema"]}}
          for t in 体.get("tools", []) if "input_schema" in t]
    if 业务.配置()["外发打码"]:          # 第三方模型，个人信息先打码再发（图文混排只打文字部分）
        码 = lambda c: 安全.打码(c) if isinstance(c, str) else [{**p, "text": 安全.打码(p["text"])} if p.get("type") == "text" else p for p in c] if isinstance(c, list) else c  # noqa: E731
        消息 = [{**m, "content": 码(m["content"])} for m in 消息]
    return {"model": 环境.兼容["模型"], "messages": 消息, "max_tokens": min(int(体.get("max_tokens", 4096)), 8192),
            **({"tools": 工具} if 工具 else {})}


def 转回答(j: dict) -> tuple[list, str, dict]:
    选 = j["choices"][0]
    m = 选["message"]
    块 = [{"type": "text", "text": m["content"]}] if m.get("content") else []
    for tc in m.get("tool_calls") or []:
        try:
            参 = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            参 = {}
        块.append({"type": "tool_use", "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:20]}", "name": tc["function"]["name"], "input": 参})
    停 = "tool_use" if m.get("tool_calls") else "max_tokens" if 选.get("finish_reason") == "length" else "end_turn"
    u = j.get("usage") or {}
    return 块 or [{"type": "text", "text": ""}], 停, {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)}


def _sse(事件, 数据):
    return f"event: {事件}\ndata: {json.dumps(数据, ensure_ascii=False)}\n\n".encode()


def _流(块表, 停, 用量, 模型):
    yield _sse("message_start", {"type": "message_start", "message": {
        "id": f"msg_{uuid.uuid4().hex[:24]}", "type": "message", "role": "assistant", "model": 模型, "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 用量["input_tokens"], "output_tokens": 1}}})
    for i, b in enumerate(块表):
        if b["type"] == "text":
            yield _sse("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}})
            yield _sse("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": b["text"]}})
        else:   # tool_use 的 input 要走 input_json_delta，不能直接塞进 start
            yield _sse("content_block_start", {"type": "content_block_start", "index": i,
                                               "content_block": {"type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}})
            yield _sse("content_block_delta", {"type": "content_block_delta", "index": i,
                                               "delta": {"type": "input_json_delta", "partial_json": json.dumps(b["input"], ensure_ascii=False)}})
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": i})
    yield _sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": 停, "stop_sequence": None},
                                 "usage": {"output_tokens": 用量["output_tokens"]}})
    yield _sse("message_stop", {"type": "message_stop"})


async def 发(请求: dict) -> dict:
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(环境.兼容["地址"].rstrip("/") + "/chat/completions", json=请求,
                         headers={"Authorization": f"Bearer {环境.兼容['密钥']}"})
        r.raise_for_status()
        return r.json()


async def _messages(request):
    体 = json.loads(await request.body())
    try:
        块表, 停, 用量 = 转回答(await 发(转请求(体)))
    except httpx.HTTPStatusError as e:
        return JSONResponse({"type": "error", "error": {"type": "api_error", "message": e.response.text[:500]}}, e.response.status_code)
    模型 = 环境.兼容["模型"]
    if not 体.get("stream"):
        return JSONResponse({"id": f"msg_{uuid.uuid4().hex[:24]}", "type": "message", "role": "assistant", "model": 模型,
                             "content": 块表, "stop_reason": 停, "stop_sequence": None, "usage": 用量})
    return StreamingResponse(_流(块表, 停, 用量, 模型), media_type="text/event-stream")


async def _数token(request):
    体 = json.loads(await request.body())
    return JSONResponse({"input_tokens": len(json.dumps(体, ensure_ascii=False)) // 3})


async def _随便(request):
    return JSONResponse({"ok": True})


app = Starlette(routes=[Route("/v1/messages", _messages, methods=["POST"]),
                        Route("/v1/messages/count_tokens", _数token, methods=["POST"]),
                        Route("/{path:path}", _随便, methods=["GET", "HEAD", "POST"])])


def 起来():
    """后台线程起网关，只起一次。"""
    global _起了
    if _起了:
        return
    _起了 = True
    threading.Thread(target=uvicorn.run, args=(app,), daemon=True,
                     kwargs={"host": "127.0.0.1", "port": 环境.兼容["端口"], "log_level": "error"}).start()
    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{环境.兼容['端口']}/", timeout=0.5)
            return
        except httpx.HTTPError:
            time.sleep(0.1)
