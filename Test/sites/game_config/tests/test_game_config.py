# -*- coding: utf-8 -*-
"""
游戏配置表测试

★ 为什么要测配置表 ★

    游戏公司 QA 的 JD 原话：「对配置表、数值逻辑、状态流转、奖励发放规则进行验证，
    发现逻辑异常、边界问题和配置问题」。

    游戏的大部分玩法是配出来的，不是写出来的。代码没改，策划改了一行表，
    SSR 概率就可能从 1.5% 变成 15%。这类错误功能测试点一遍发现不了，
    上线后玩家比你先发现，所以要把表当成被测对象，每次改表都跑一遍。

    检查器本身对不对，由 tests/test_config_check.py 用坏表做对照实验来保证。

跑法：
    pytest -m gameconfig -v
"""

import allure
import pytest

from sites.game_config import DATA

from common.config_check import CHECKS
from common.data_reader import load_yaml

pytestmark = pytest.mark.gameconfig


@pytest.fixture(scope="module")
def game_cfg():
    return load_yaml(DATA / "game_config.yaml")


@allure.epic("游戏配置")
@allure.feature("配置表校验")
@allure.title("GC - {name}")
@pytest.mark.parametrize("name", list(CHECKS))
def test_config(game_cfg, name):
    problems = CHECKS[name](game_cfg)
    allure.attach("\n".join(problems) or "无", name="问题清单")
    assert not problems, "\n".join(problems)
