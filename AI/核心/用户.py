"""多用户：每个用户一个 API 令牌，带权限和各自的每日花费上限。多个人/多个系统调同一套 API，互不串。

存 记忆/<业务>/用户.json（令牌是密钥，不放业务模板里）。`python Work.py 用户 …` 管理。
权限：派活（提交单）、流程（跑流程）、批准（批准/拒绝/回答）、查看（状态、单、指标）、管理（重建知识库等）。
没有任何用户、也没设 API_TOKEN = 本机单人模式，不查令牌；设了 API_TOKEN 的那个令牌 = 管理员，全部权限。
每个用户的单：来源记「网页:名字」，会话默认按人分开（张三的「接着聊」不会接到李四的对话）。
"""
import json
import secrets
import time

import 环境
from 核心 import 轨迹

文件 = 环境.记忆 / "用户.json"
全部权限 = ["派活", "流程", "批准", "查看", "管理"]


def _读() -> dict:
    try:
        return json.loads(文件.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _写(d: dict):
    文件.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def 加(名: str, 权限: list[str], 每日上限: float = 0) -> str:
    if 坏 := [p for p in 权限 if p not in 全部权限]:
        raise ValueError(f"不认识的权限：{'、'.join(坏)}（可选：{'、'.join(全部权限)}）")
    d = {k: v for k, v in _读().items() if v["名"] != 名}
    令牌 = secrets.token_urlsafe(24)
    d[令牌] = {"名": 名, "权限": 权限, "每日上限": 每日上限, "建于": time.strftime("%Y-%m-%d %H:%M")}
    _写(d)
    return 令牌


def 删(名: str) -> bool:
    d = _读()
    新 = {k: v for k, v in d.items() if v["名"] != 名}
    _写(新)
    return len(新) < len(d)


def 列表() -> list[dict]:
    return [{**v, "令牌": k[:4] + "…"} for k, v in _读().items()]


def 开放模式() -> bool:
    return not 环境.HTTP令牌 and not _读()


def 认(令牌: str | None) -> dict | None:
    """→ 用户（名、权限、每日上限），认不出 None。"""
    if 开放模式():
        return {"名": "本机", "权限": 全部权限, "每日上限": 0}
    if 令牌 and 环境.HTTP令牌 and secrets.compare_digest(令牌, 环境.HTTP令牌):
        return {"名": "管理员", "权限": 全部权限, "每日上限": 0}
    return _读().get(令牌 or "")


def 今日花费(名: str) -> float:
    今 = time.strftime("%Y-%m-%d")
    return sum(float(u.get("花费") or 0) for u in 轨迹.读台账().get("单", {}).values()
               if u.get("日期") == 今 and u.get("来源") == f"网页:{名}")
