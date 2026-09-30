"""定时：agent 调 schedule 记「几点做什么」→ 记忆/<业务>/待办.json；业务/<名>/定时.json 写每天固定的活：
  [{"时间": "09:00", "需求": "出日报", "星期": [1,2,3,4,5]}, {"时间": "10:00", "流程": "月报", "输入": {"月份": 9}}]
服务模式的调度循环每 30 秒看一次，到点就开一单。做完才删，停机重启照样补。
"""
import json
import re
import time
from datetime import datetime, timedelta

import 环境

待办文件 = 环境.记忆 / "待办.json"
周期文件 = 环境.业务 / "定时.json"
状态文件 = 环境.记忆 / "定时状态.json"


def 解析(时间: str, 现在: datetime | None = None) -> datetime:
    """支持：2026-10-01 09:00 / 09:00（今天，过了就明天）/ +30m / +2h / +1d"""
    现在 = 现在 or datetime.now()
    s = 时间.strip()
    if m := re.fullmatch(r"\+(\d+)\s*([mhd])", s):
        return 现在 + timedelta(**{{"m": "minutes", "h": "hours", "d": "days"}[m[2]]: int(m[1])})
    if m := re.fullmatch(r"(\d{1,2}):(\d{2})", s):
        t = 现在.replace(hour=int(m[1]), minute=int(m[2]), second=0, microsecond=0)
        return t if t > 现在 else t + timedelta(days=1)
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError(f"时间格式不对：{时间}。要 2026-10-01 09:00、09:00、+30m、+2h、+1d 之一") from None


def _读(f, 默认):
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return 默认


def 加(时间: str, 需求: str, 来源: str = "") -> dict:
    t = 解析(时间)
    if t < datetime.now() - timedelta(minutes=1):
        raise ValueError("这个时间已经过了")
    表 = _读(待办文件, [])
    条 = {"id": f"S{int(time.time() * 1000) % 10 ** 9}", "时间": t.strftime("%Y-%m-%d %H:%M"), "需求": 需求, "来源": 来源}
    表.append(条)
    待办文件.write_text(json.dumps(表, ensure_ascii=False, indent=1), encoding="utf-8")
    return 条


def 列表() -> list:
    return _读(待办文件, [])


def 删(id: str):
    待办文件.write_text(json.dumps([x for x in 列表() if x["id"] != id], ensure_ascii=False, indent=1), encoding="utf-8")


def 到期(现在: datetime | None = None) -> list[dict]:
    """→ 该开单的：一次性待办（不删，做完调 删）+ 今天到点还没跑过的周期任务。"""
    现在 = 现在 or datetime.now()
    出 = [x for x in 列表() if datetime.strptime(x["时间"], "%Y-%m-%d %H:%M") <= 现在]
    状态 = _读(状态文件, {})
    for i, 周 in enumerate(_读(周期文件, [])):
        键, 今 = f"{i}|{周['时间']}|{(周.get('需求') or 周.get('流程', ''))[:20]}", 现在.strftime("%Y-%m-%d")
        星期 = 周.get("星期")   # 1-7，不写就每天
        if 状态.get(键) != 今 and 现在.strftime("%H:%M") >= 周["时间"] and (not 星期 or 现在.isoweekday() in 星期):
            状态[键] = 今
            出.append({"id": "", "时间": 周["时间"], "需求": 周.get("需求", ""), "来源": "周期", "流程": 周.get("流程"), "输入": 周.get("输入")})
    状态文件.write_text(json.dumps(状态, ensure_ascii=False), encoding="utf-8")
    return 出
