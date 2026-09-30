import asyncio
import json
from datetime import datetime

import httpx
import pytest
from starlette.testclient import TestClient

import 环境
from 核心 import 业务, 大脑, 定时, 知识库, 网关, 记忆, 调度, 评测, 轨迹
from 通道 import 电报, 网页


# ── 知识库 ──
def test_知识库带出处():
    r = 知识库.查("退货算不算订单")
    assert r and r[0]["出处"].startswith("口径.md#") and "订单" in r[0]["文本"]


def test_知识库改了自动重建(tmp_path, monkeypatch):
    monkeypatch.setattr(知识库, "目录", tmp_path)
    (tmp_path / "a.md").write_text("报销上限是每月三千元。", encoding="utf-8")
    assert "三千" in 知识库.查("报销上限")[0]["文本"]
    (tmp_path / "a.md").write_text("报销上限是每月五千元。", encoding="utf-8")
    assert "五千" in 知识库.查("报销上限")[0]["文本"]
    monkeypatch.undo()
    知识库.重建()


def test_切块不丢内容():
    文 = "\n\n".join(f"第{i}条规则，" + "内容" * 40 for i in range(20))
    块 = 知识库._切(文)
    assert len(块) > 1 and all(f"第{i}条" in "".join(块) for i in range(20))


# ── 记忆 ──
def test_记忆去重和注入():
    assert "记住" in asyncio.run(记忆.记住("金额保留两位小数"))
    assert asyncio.run(记忆.记住("金额保留两位小数")) == "已经记过了"
    assert "金额保留两位小数" in 业务.人设()


def test_记忆超限压缩(monkeypatch):
    async def 假压(提示, 系统=""):
        return "\n".join(f"- 合并后{i}" for i in range(5))
    monkeypatch.setattr(大脑, "问一句", 假压)
    for i in range(记忆.上限 + 1):
        asyncio.run(记忆.记住(f"要求第{i}号"))
    条 = 记忆.读()
    assert 条[:5] == [f"合并后{i}" for i in range(5)] and len(条) < 记忆.上限


# ── 定时 ──
def test_时间解析():
    现 = datetime(2026, 9, 29, 10, 0)
    assert 定时.解析("+30m", 现) == datetime(2026, 9, 29, 10, 30)
    assert 定时.解析("09:00", 现) == datetime(2026, 9, 30, 9, 0)
    assert 定时.解析("11:00", 现) == datetime(2026, 9, 29, 11, 0)
    assert 定时.解析("2026-10-01 09:00", 现) == datetime(2026, 10, 1, 9, 0)
    with pytest.raises(ValueError):
        定时.解析("明天早上", 现)


def test_待办到期与周期(monkeypatch, tmp_path):
    条 = 定时.加("+1m", "出日报")
    assert not any(x["id"] == 条["id"] for x in 定时.到期())
    assert any(x["id"] == 条["id"] for x in 定时.到期(datetime.now().replace(year=2030)))
    定时.删(条["id"])
    周 = tmp_path / "定时.json"
    周.write_text(json.dumps([{"时间": "09:00", "需求": "晨报"}], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(定时, "周期文件", 周)
    早 = datetime.now().replace(hour=8, minute=0)
    晚 = datetime.now().replace(hour=9, minute=5)
    assert not [x for x in 定时.到期(早) if x["来源"] == "周期"]
    assert [x for x in 定时.到期(晚) if x["来源"] == "周期"]
    assert not [x for x in 定时.到期(晚) if x["来源"] == "周期"]     # 同一天只跑一次


# ── 业务加载 ──
def test_团队子agent():
    团 = 业务.团队()
    assert "reviewer" in 团 and "mcp__biz__search_kb" in 团["reviewer"].tools and "复核" in 团["reviewer"].prompt


# ── 大脑：重试、换大脑、每日上限、会话接续 ──
def _假跑(结果表):
    调用 = []

    async def 跑(脑, 单, 接上):
        调用.append((脑, 接上))
        r = {"编号": 单["编号"], "回复": "ok", "session": f"s-{脑}", "轮数": 1, "花费": 0.01, "出错": None, "不重试": False,
             "模型": "m", "大脑": 脑}
        r.update(结果表.pop(0) if 结果表 else {})
        return r
    return 跑, 调用


def test_重试后换备用大脑(monkeypatch):
    跑, 调用 = _假跑([{"出错": "崩了"}, {"出错": "又崩"}, {}])
    monkeypatch.setattr(大脑, "_跑", 跑)
    monkeypatch.setattr(环境, "备用大脑", ["api"])
    r = asyncio.run(大脑.跑一单("x"))
    assert [c[0] for c in 调用] == ["本机", "本机", "api"] and not r["出错"] and r["大脑"] == "api"
    assert 轨迹.读台账()["单"][r["编号"]]["结果"] == "成"


def test_到上限不重试(monkeypatch):
    跑, 调用 = _假跑([{"出错": "轮数到上限", "不重试": True}])
    monkeypatch.setattr(大脑, "_跑", 跑)
    monkeypatch.setattr(环境, "备用大脑", ["api"])
    assert asyncio.run(大脑.跑一单("x"))["出错"] == "轮数到上限" and len(调用) == 1


def test_会话接续(monkeypatch):
    跑, 调用 = _假跑([])
    monkeypatch.setattr(大脑, "_跑", 跑)
    asyncio.run(大脑.跑一单("第一句", 会话="张三"))
    asyncio.run(大脑.跑一单("第二句", 会话="张三"))
    assert 调用 == [("本机", None), ("本机", "s-本机")]


def test_每日上限(monkeypatch):
    跑, 调用 = _假跑([])
    monkeypatch.setattr(大脑, "_跑", 跑)
    monkeypatch.setattr(环境, "每日上限", 0)
    assert "每日上限" in asyncio.run(大脑.跑一单("x"))["出错"] and not 调用


def test_大脑配置错():
    with pytest.raises(大脑.配置错):
        大脑._子环境("兼容") if not 环境.兼容["密钥"] else 大脑._子环境("不存在")


# ── 兼容网关：Anthropic ⇄ OpenAI ──
def test_网关转请求():
    体 = {"system": [{"type": "text", "text": "x-anthropic-billing-header"}, {"type": "text", "text": "你是助理"}],
         "max_tokens": 32000, "tools": [{"name": "Bash", "description": "跑命令", "input_schema": {"type": "object"}}],
         "messages": [{"role": "user", "content": "列文件"},
                      {"role": "assistant", "content": [{"type": "text", "text": "好"},
                                                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}]},
                      {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "a.txt"}]},
                                                   {"type": "text", "text": "继续"}]}]}
    o = 网关.转请求(体)
    assert o["messages"][0] == {"role": "system", "content": "你是助理"} and o["max_tokens"] == 8192
    assert o["messages"][2]["tool_calls"][0]["function"] == {"name": "Bash", "arguments": '{"command": "ls"}'}
    assert o["messages"][3] == {"role": "tool", "tool_call_id": "t1", "content": "a.txt"}
    assert o["messages"][4] == {"role": "user", "content": "继续"} and o["tools"][0]["function"]["name"] == "Bash"


def test_网关转回答与流():
    块, 停, 量 = 网关.转回答({"choices": [{"finish_reason": "tool_calls", "message": {"content": "查一下", "tool_calls": [
        {"id": "c1", "function": {"name": "Read", "arguments": '{"file_path": "a"}'}}]}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}})
    assert 停 == "tool_use" and 块[1] == {"type": "tool_use", "id": "c1", "name": "Read", "input": {"file_path": "a"}}
    事件 = b"".join(网关._流(块, 停, 量, "m")).decode()
    assert 事件.count("event: content_block_start") == 2 and "input_json_delta" in 事件 and 事件.rstrip().endswith('{"type": "message_stop"}')


def test_网关端到端(monkeypatch):
    async def 假发(请求):
        assert 请求["messages"][-1]["content"] == "你好"
        return {"choices": [{"finish_reason": "stop", "message": {"content": "你好呀"}}], "usage": {}}
    monkeypatch.setattr(网关, "发", 假发)
    c = TestClient(网关.app)
    r = c.post("/v1/messages", json={"messages": [{"role": "user", "content": "你好"}], "max_tokens": 10})
    assert r.json()["content"] == [{"type": "text", "text": "你好呀"}] and r.json()["stop_reason"] == "end_turn"
    assert "text_delta" in c.post("/v1/messages", json={"stream": True, "messages": [{"role": "user", "content": "你好"}]}).text


# ── 网页 API ──
def test_网页api(monkeypatch):
    async def 假跑一单(需求, 会话=None, 来源="", 编号=None, **_):
        轨迹.存档(编号, 需求=需求, 结果="成", 轮数=2, 花费=0.1, 日期="x", 交付=[{"文本": "好了", "文件": []}])
        return {"编号": 编号, "出错": None, "交付": [], "回复": "好了"}
    monkeypatch.setattr(调度.大脑, "跑一单", 假跑一单)
    with TestClient(网页.app) as c:
        async def 起():
            await 调度.开()
        c.portal.call(起)
        assert c.post("/api/task", json={}).status_code == 400
        编号 = c.post("/api/task", json={"task": "出日报"}).json()["编号"]
        c.portal.call(lambda: 调度.队列.join())
        u = c.get(f"/api/task/{编号}").json()
        assert u["结果"] == "成" and u["交付"][0]["文本"] == "好了"
        s = c.get("/api/status").json()
        assert s["业务"] == "示例" and s["统计"]["总单数"] >= 1
        assert c.post("/api/approve/A999", json={"ok": True}).status_code == 404
        assert c.get("/").status_code == 200


def test_网页令牌(monkeypatch):
    monkeypatch.setattr(环境, "HTTP令牌", "k")
    c = TestClient(网页.app)
    assert c.get("/api/status").status_code == 401


def test_tg指令():
    assert 电报.解析指令("批 A3") == ("A3", True, "")
    assert 电报.解析指令("拒A3 先别发") == ("A3", False, "先别发")
    assert 电报.解析指令("答 A4 按月") == ("A4", True, "按月")
    assert 电报.解析指令("帮我出个表") is None


# ── 评测判分 ──
def test_评测判分(monkeypatch):
    async def 假评(提示, 系统=""):
        return "不通过：没说地区"
    monkeypatch.setattr(大脑, "问一句", 假评)
    r = {"回复": "做好了", "交付": [{"文本": "总额 100", "文件": []}], "出错": None, "工具": ["mcp__biz__deliver"], "轮数": 50}
    错 = asyncio.run(评测.判({"需求": "x", "包含": ["总额"], "不含": ["报错"], "文件": ["*.nothing"], "工具": ["deliver", "search_kb"],
                           "最多轮": 40, "评审": "要说地区"}, r, 0))
    assert 错 == ["没生成 *.nothing", "没调 search_kb", "轮数 50 > 40", "评审：不通过：没说地区"]


def test_停机续做(monkeypatch):
    做了 = []

    async def 假跑一单(需求, 会话=None, 来源="", 编号=None, **_):
        做了.append((编号, 需求, 会话))
        轨迹.存档(编号, 结果="成")
        return {"编号": 编号, "出错": None, "交付": [], "回复": ""}
    monkeypatch.setattr(调度.大脑, "跑一单", 假跑一单)

    async def 场景():
        await 调度.开()
        编号 = await 调度.提交("没做完的单", 会话="李四")
        任务 = await 调度.开()          # 模拟重启：新队列里应该把它重新排上
        await 调度.队列.join()
        for t in 任务:
            t.cancel()
        return 编号
    编号 = asyncio.run(场景())
    assert (编号, "没做完的单", "李四") in 做了
