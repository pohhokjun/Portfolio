# -*- coding: utf-8 -*-
"""
游戏配置表校验。每个函数返回问题清单，空列表 = 没问题。

★ 为什么返回清单而不是直接 assert ★

    一张表可能同时错十处。assert 碰到第一处就停，
    策划改完一处再跑、再停、再改，来回十趟。
    一次列全，一趟改完。
"""

from datetime import datetime
from decimal import Decimal


def check_unique_ids(cfg):
    out = []
    for table in ("rewards", "events"):
        ids = [r["id"] for r in cfg[table]]
        out += ["%s 表 id 重复: %s" % (table, i) for i in sorted(set(ids)) if ids.count(i) > 1]
    return out


def check_gacha_prob(cfg):
    probs = [Decimal(p["prob"]) for p in cfg["gacha"]["pool"]]
    out = ["卡池第 %d 项概率 %s ≤ 0" % (i + 1, p) for i, p in enumerate(probs) if p <= 0]
    if sum(probs) != 100:
        out.append("卡池概率合计 %s%%，应为 100%%" % sum(probs))
    return out


def check_gacha_value(cfg):
    """
    数值平衡：单抽的期望回报不能超过花费的上限比例。
    超了说明玩家抽得越多赚得越多，经济系统会被刷穿。
    """
    g = cfg["gacha"]
    value = {r["id"]: r["value"] for r in cfg["rewards"]}
    ev = sum(Decimal(p["prob"]) / 100 * value.get(p["reward_id"], 0) for p in g["pool"])
    cap = Decimal(str(g["cost"])) * Decimal(str(g["max_return_ratio"]))
    return [] if ev <= cap else ["单抽期望回报 %s > 上限 %s" % (ev, cap)]


def check_levels(cfg):
    lv = cfg["levels"]
    out = []
    if [r["level"] for r in lv] != list(range(1, len(lv) + 1)):
        out.append("等级没有从 1 连续编号")
    out += ["%d 级经验 %d 没有高于 %d 级的 %d" % (b["level"], b["exp"], a["level"], a["exp"])
            for a, b in zip(lv, lv[1:]) if b["exp"] <= a["exp"]]
    return out


def check_star_growth(cfg):
    s = cfg["star_growth"]
    return ["%d 星倍率 %s 没有高于 %d 星的 %s" % (i + 2, b, i + 1, a)
            for i, (a, b) in enumerate(zip(s, s[1:])) if b <= a]


def check_refs(cfg):
    """引用完整性：卡池和活动里的奖励 ID 必须在奖励表里存在，否则发奖时直接报错或发空。"""
    ids = {r["id"] for r in cfg["rewards"]}
    refs = [("卡池", p["reward_id"]) for p in cfg["gacha"]["pool"]]
    refs += [("活动 %s" % e["id"], e["reward_id"]) for e in cfg["events"]]
    return ["%s 引用了不存在的奖励 %s" % (where, rid) for where, rid in refs if rid not in ids]


def _t(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def check_events(cfg):
    """
    时间合法、start < end、同类型不重叠。
    区间是左闭右开 [start, end)：上一个 10-08 00:00 结束、下一个 10-08 00:00 开始
    不算重叠；但只要早一分钟开始就算。这个边界最容易填错。
    """
    out, spans = [], {}
    for e in cfg["events"]:
        try:
            s, t = _t(e["start"]), _t(e["end"])
        except (ValueError, TypeError):
            out.append("活动 %s 时间格式错误" % e["id"])
            continue
        if s >= t:
            out.append("活动 %s 开始时间不早于结束时间" % e["id"])
        spans.setdefault(e["type"], []).append((s, t, e["id"]))
    for typ, lst in spans.items():
        lst.sort()
        out += ["活动 %s 和 %s 时间重叠（类型 %s）" % (a[2], b[2], typ)
                for a, b in zip(lst, lst[1:]) if b[0] < a[1]]
    return out


CHECKS = {
    "ID唯一": check_unique_ids,
    "概率合计": check_gacha_prob,
    "数值平衡": check_gacha_value,
    "经验曲线": check_levels,
    "升星倍率": check_star_growth,
    "引用完整": check_refs,
    "活动时间": check_events,
}
