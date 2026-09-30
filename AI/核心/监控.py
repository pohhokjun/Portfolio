"""效果指标 + 告警。

指标：从台账算——成功率、一次做成率（没重试没换大脑）、人工接管率（要人批准/回答过的单占比）、审批通过率、
      缓存命中率、平均轮数/耗时/花费、省下工时（成功单数 × 业务配置的 人工分钟 − 人工介入花的时间按每次 2 分钟估）。
告警：单子出错、连续失败 N 单、今日花费过 80%、疑似注入 → 记 记忆/<业务>/告警.jsonl，推给已注册的通道（TG 主人），
      设了 ALERT_WEBHOOK 再 POST 一份（钉钉/飞书/企业微信群机器人这类通用 webhook，不用注册账号）。
"""
import json
import os
import time

import 环境
from 核心 import 轨迹

告警文件 = 环境.记忆 / "告警.jsonl"
通知: list = []          # 通道注册：async f(文本)
_已报: set = set()       # 同一件事一天只报一次


async def 告警(级别: str, 文本: str, 键: str = ""):
    if 键:
        键 = f"{time.strftime('%Y-%m-%d')}|{键}"
        if 键 in _已报:
            return
        _已报.add(键)
    行 = {"时间": time.strftime("%Y-%m-%d %H:%M:%S"), "级别": 级别, "文本": 文本}
    with 告警文件.open("a", encoding="utf-8") as f:
        f.write(json.dumps(行, ensure_ascii=False) + "\n")
    for f in 通知:
        try:
            await f(f"【{级别}】{环境.业务名}：{文本}")
        except Exception:
            pass
    if url := os.environ.get("ALERT_WEBHOOK"):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(url, json={"msgtype": "text", "text": {"content": f"【{级别}】{环境.业务名}：{文本}"}})
        except Exception:
            pass


def 最近告警(n=20) -> list:
    if not 告警文件.exists():
        return []
    return [json.loads(l) for l in 告警文件.read_text(encoding="utf-8").splitlines()[-n:]][::-1]


async def 单后检查(r: dict):
    """每单收尾调：出错 / 连续失败 / 花费过线。"""
    from 核心 import 业务
    if r.get("出错"):
        await 告警("错误", f"{r['编号']} 失败：{r['出错'][:200]}")
    完 = [u for u in sorted(轨迹.读台账().get("单", {}).values(), key=lambda u: u["编号"]) if u.get("结果") in ("成", "出错")]
    n = 业务.配置()["连续失败告警"]
    if len(完) >= n and all(u["结果"] == "出错" for u in 完[-n:]):
        await 告警("严重", f"连续 {n} 单失败，最近：{完[-1].get('出错', '')[:120]}", 键=f"连败{完[-1]['编号']}")
    if (花 := 轨迹.今日花费()) >= 环境.每日上限 * 0.8:
        await 告警("提醒", f"今天已花 ${花:.2f}，到每日上限 ${环境.每日上限} 的 80%", 键="花费80")


def 指标() -> dict:
    from 核心 import 业务
    单 = [u for u in 轨迹.读台账().get("单", {}).values() if u.get("结果") in ("成", "出错") and u.get("来源") != "评测"]
    n = len(单) or 1
    成 = [u for u in 单 if u["结果"] == "成"]
    人工 = [u for u in 单 if u.get("人工次数")]
    批 = sum(u.get("审批次数", 0) for u in 单)
    人工分 = 业务.配置()["人工分钟"]
    省 = len(成) * 人工分 - sum(u.get("人工次数", 0) for u in 单) * 2
    return {"单数": len(单), "成功率": f"{len(成) / n:.0%}", "一次做成率": f"{sum(not u.get('重试') for u in 成) / n:.0%}",
            "人工接管率": f"{len(人工) / n:.0%}", "审批通过率": f"{sum(u.get('审批通过', 0) for u in 单) / 批:.0%}" if 批 else "-",
            "缓存命中率": f"{sum(bool(u.get('缓存')) for u in 单) / n:.0%}",
            "平均轮数": round(sum(u.get("轮数", 0) for u in 单) / n, 1), "平均耗时秒": round(sum(u.get("耗时", 0) for u in 单) / n),
            "平均花费": round(sum(float(u.get("花费") or 0) for u in 单) / n, 4), "总花费": round(sum(float(u.get("花费") or 0) for u in 单), 4),
            "省下工时": round(max(省, 0) / 60, 1), "人工分钟/单": 人工分}
