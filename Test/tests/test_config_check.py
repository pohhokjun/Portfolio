# -*- coding: utf-8 -*-
"""
配置表检查器的自测：每条检查喂一张坏表，必须报出来。

真实配置表是好的，所以 sites/game_config 那边永远是绿的 ——
绿本身证明不了检查有效，得靠这里的坏表做对照。
"""

import copy

import pytest

from common.config_check import CHECKS
from common.data_reader import load_yaml
from sites.game_config import DATA

GOOD = load_yaml(DATA / "game_config.yaml")


def _break(fn):
    cfg = copy.deepcopy(GOOD)
    fn(cfg)
    return cfg


def test_真实配置表全部通过():
    assert {k: f(GOOD) for k, f in CHECKS.items() if f(GOOD)} == {}


@pytest.mark.parametrize("name,mutate,keyword", [
    ("ID唯一", lambda c: c["rewards"].append(dict(c["rewards"][0])), "重复"),
    ("概率合计", lambda c: c["gacha"]["pool"][0].update(prob="59.9"), "99.9"),
    ("概率合计", lambda c: c["gacha"]["pool"][0].update(prob="0"), "≤ 0"),
    # 0.1 + 0.2 用浮点数加不等于 0.3，Decimal 才能判对
    ("概率合计", lambda c: c["gacha"].update(pool=[
        {"reward_id": 2001, "prob": "99.7"}, {"reward_id": 2002, "prob": "0.1"},
        {"reward_id": 2003, "prob": "0.2"}]), None),
    ("数值平衡", lambda c: c["gacha"]["pool"][3].update(prob="15"), "期望回报"),
    ("经验曲线", lambda c: c["levels"][3].update(exp=250), "没有高于"),
    ("经验曲线", lambda c: c["levels"].pop(2), "连续"),
    ("升星倍率", lambda c: c["star_growth"].__setitem__(3, 1.5), "没有高于"),
    ("引用完整", lambda c: c["events"][0].update(reward_id=9999), "9999"),
    ("活动时间", lambda c: c["events"][1].update(start="2026-10-07 23:59"), "重叠"),
    ("活动时间", lambda c: c["events"][0].update(end="2026-10-01 00:00"), "不早于"),
    ("活动时间", lambda c: c["events"][0].update(start="2026/10/01"), "格式"),
])
def test_坏表必须被抓到(name, mutate, keyword):
    problems = CHECKS[name](_break(mutate))
    if keyword is None:                    # 这一条是反过来：合法的表不能误报
        assert problems == []
    else:
        assert any(keyword in p for p in problems), problems


def test_首尾相接的活动不算重叠():
    """左闭右开：10-08 00:00 结束，下一个 10-08 00:00 开始，是合法的。"""
    cfg = _break(lambda c: c["events"][1].update(start="2026-10-08 00:00"))
    assert CHECKS["活动时间"](cfg) == []
