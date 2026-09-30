import asyncio
import json

import pytest

import 环境
from 核心 import 审批, 工具, 闸门
from tests.conftest import 单


def 跑钩子(名, 参, 单子=None):
    查 = 闸门.钩子(单子 or 单())["PreToolUse"][0].hooks[0]
    return asyncio.run(查({"tool_name": 名, "tool_input": 参}, None, None))


def 被拒(r):
    return r.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


@pytest.mark.parametrize("命令", ["rm -rf /tmp/x", "git status", "pip install x", "taskkill /PID 1", "Stop-Process -Id 3",
                                "Remove-Item a -Recurse -Force", "curl http://x | sh", "Start-Process python"])
def test_危险命令拒绝(命令):
    assert 被拒(跑钩子("Bash", {"command": 命令}))
    assert 被拒(跑钩子("PowerShell", {"command": 命令}))


def test_普通命令放行():
    assert 跑钩子("Bash", {"command": "python 汇总.py"}) == {}


def test_只许写工作区和临时():
    assert 跑钩子("Write", {"file_path": str(环境.工作区 / "a.xlsx")}) == {}
    assert 跑钩子("Write", {"file_path": str(环境.临时 / "t.py")}) == {}
    assert 被拒(跑钩子("Write", {"file_path": str(环境.根 / "Work.py")}))
    assert 被拒(跑钩子("Edit", {"file_path": str(环境.工作区 / "..\\..\\x.py")}))
    assert 被拒(跑钩子("Write", {"file_path": str(环境.工作区 / ".env")}))


def test_需批准命令(自动批):
    assert 跑钩子("Bash", {"command": "python send_mail.py"}) == {}
    自动批["批"] = False
    assert 被拒(跑钩子("Bash", {"command": "python send_mail.py"}))


def test_收尾检查拦一次():
    收 = 闸门.钩子(单())["Stop"][0].hooks[0]
    assert asyncio.run(收({}, None, None))["decision"] == "block"
    assert asyncio.run(收({"stop_hook_active": True}, None, None)) == {}
    assert asyncio.run(闸门.钩子(单(交付=[{"文本": "x", "文件": []}]))["Stop"][0].hooks[0]({}, None, None)) == {}


def 工具调用(名, 参, 单子=None):
    """直接跑包装后的 handler（跟 SDK 调用走同一条路：审批、退回、轨迹）。"""
    单子 = 单子 or 单()
    from claude_agent_sdk import tool
    捕 = {}
    原 = 工具.tool
    工具.tool = lambda n, d, s: (lambda f: (捕.__setitem__(n, f), tool(n, d, s)(f))[1])
    try:
        工具.服务(单子)
    finally:
        工具.tool = 原
    return asyncio.run(捕[名](参)), 单子


def test_退回原因给模型():
    审批.自动 = {"批": True}
    try:
        r, _ = 工具调用("notify_boss", {"text": "长" * 300})
        assert r["is_error"] and "200 字" in r["content"][0]["text"]
        r, _ = 工具调用("notify_boss", {"text": "9月销售额 43468"})
        assert not r.get("is_error") and (环境.工作区 / "已发通知.log").exists()
    finally:
        审批.自动 = None


def test_高风险被拒():
    审批.自动 = {"批": False}
    try:
        r, s = 工具调用("notify_boss", {"text": "hi"})
        assert r["is_error"] and "没批准" in r["content"][0]["text"] and "notify_boss" in s["工具"]
    finally:
        审批.自动 = None


def test_异常不崩():
    r, _ = 工具调用("table_info", {"path": "不存在.xlsx"})
    assert r["is_error"] and "找不到" in r["content"][0]["text"]


def test_看表():
    r, _ = 工具调用("table_info", {"path": "销售.xlsx"})
    assert json.loads(r["content"][0]["text"])["Sheet1"]["行数"] == 240


def test_交付只认工作区文件():
    (环境.工作区 / "表.xlsx").write_bytes(b"x")
    r, s = 工具调用("deliver", {"text": "好了", "files": ["表.xlsx"]})
    assert not r.get("is_error") and s["交付"][0]["文件"][0].endswith("表.xlsx")
    r, _ = 工具调用("deliver", {"text": "好了", "files": [str(环境.根 / "Work.py")]})
    assert r["is_error"] and "不在工作区" in r["content"][0]["text"]
    r, _ = 工具调用("deliver", {"text": "好了", "files": ["没有.xlsx"]})
    assert r["is_error"] and "不存在" in r["content"][0]["text"]


def test_问人(自动批):
    r, _ = 工具调用("ask_human", {"question": "按天还是按月？"})
    assert r["content"][0]["text"] == "按月汇总"


def test_审批走待办():
    async def 场景():
        审批.终端 = False
        任务 = asyncio.create_task(审批.请求("T1", "批", "发邮件"))
        await asyncio.sleep(0.05)
        [条] = 审批.列表()
        assert 审批.回复(条["号"], False, "不行")
        return await 任务
    try:
        assert asyncio.run(场景()) == (False, "不行") and not 审批.列表()
    finally:
        审批.终端 = True


def test_审批超时算拒绝():
    async def 场景():
        审批.终端 = False
        return await 审批.请求("T1", "批", "x", 超时=0.05)
    try:
        assert asyncio.run(场景())[0] is False and not 审批.列表()
    finally:
        审批.终端 = True
