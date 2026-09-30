"""每一步落盘 + 心跳 + 台账。字段名跟 11_本地代理/监控/看板.py 一致，那个看板指到 记忆/<业务> 也能看。

看板认的：时间要完整日期、步数看「一轮」、结束看「收尾」或「崩」、台账看 任务索引.json。
"""
import json
import threading
import time

import 环境

轨迹目录 = 环境.记忆 / "轨迹"
轨迹目录.mkdir(exist_ok=True)
_台账 = 环境.记忆 / "任务索引.json"
_锁 = threading.Lock()


def 记(编号: str, 类型: str, **kw):
    from 核心 import 业务, 安全
    if 业务.配置()["日志打码"]:           # 手机号、身份证、卡号、邮箱不落日志
        kw = {k: 安全.打码(v) for k, v in kw.items()}
    行 = {"时间": time.strftime("%Y-%m-%d %H:%M:%S"), "类型": 类型, **kw}
    with _锁, (轨迹目录 / f"{编号}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(行, ensure_ascii=False, default=str) + "\n")


def 读(编号: str) -> list:
    f = 轨迹目录 / f"{编号}.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l] if f.exists() else []


def 心跳(**kw):
    """看板靠它判断「还开着没」：25 秒没更新就算死了。"""
    底 = {"忙着": False, "编号": "", "需求": "", "队列": 0, "花费": 0, "开工": 0, "模型": 环境.大脑}
    (环境.记忆 / "心跳.json").write_text(json.dumps({**底, **kw, "时间": time.time()}, ensure_ascii=False),
                                       encoding="utf-8")


def 读台账() -> dict:
    try:
        return json.loads(_台账.read_text(encoding="utf-8"))
    except Exception:
        return {"最后单号": 0, "单": {}}


def 下一号(前缀="T") -> str:
    with _锁:
        d = 读台账()
        d["最后单号"] = int(d.get("最后单号") or 0) + 1
        _台账.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"{前缀}{d['最后单号']:04d}"


def 存档(编号: str, **kw):
    with _锁:
        d = 读台账()
        d.setdefault("单", {})[编号] = {**d.get("单", {}).get(编号, {}), "编号": 编号, **kw}
        _台账.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def 今日花费() -> float:
    今 = time.strftime("%Y-%m-%d")
    return sum(float(u.get("花费") or 0) for u in 读台账().get("单", {}).values() if str(u.get("日期", "")) == 今)
