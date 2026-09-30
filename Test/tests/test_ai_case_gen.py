# -*- coding: utf-8 -*-
"""
AI 用例生成器的自测。不调真模型，runner 换成假函数 —— 不联网、不花额度、结果固定。

重点测两道闸：机器校验能不能抓住 AI 常见的编造，审核门能不能挡住没审过的草稿。
"""

import pytest
import yaml

from tools import ai_case_gen as g

GOOD = {"id": "AI_001", "title": "t", "method": "边界值", "api": "/wallet/deposit",
        "amount": "0.01", "expect_code": 200}


def _with(**kw):
    c = dict(GOOD)
    c.update(kw)
    return c


def test_合法用例通过():
    assert g.validate_cases([GOOD, _with(id="AI_002", setup_deposit="10", why="x")]) == []


@pytest.mark.parametrize("case,keyword", [
    ({k: v for k, v in GOOD.items() if k != "expect_code"}, "缺字段"),
    (_with(priority="P0"), "编造了字段"),
    (_with(api="/wallet/transfer"), "不存在"),
    (_with(method="随便测测"), "设计方法"),
    (_with(expect_code=500), "期望码"),
    (_with(amount=0.1), "必须是字符串"),        # YAML 里没加引号，被读成浮点数
])
def test_机器校验抓得住编造(case, keyword):
    assert any(keyword in p for p in g.validate_cases([case]))


def test_id重复():
    assert any("重复" in p for p in g.validate_cases([GOOD, GOOD]))


def test_顶层不是列表():
    assert g.validate_cases({"cases": []}) == ["顶层不是列表"]


def test_剥掉代码块围栏():
    text = "好的，用例如下：\n```yaml\n- id: A\n```\n以上。"
    assert g.extract_yaml(text) == [{"id": "A"}]


def test_生成流程_假模型():
    fake = lambda prompt: "```yaml\n" + yaml.safe_dump([GOOD], allow_unicode=True) + "```"
    cases, problems = g.generate("需求", runner=fake)
    assert cases == [GOOD] and problems == []


def test_模型输出不是YAML不抛异常():
    cases, problems = g.generate("需求", runner=lambda p: "- a: [unclosed")
    assert cases == [] and "不是合法 YAML" in problems[0]


def test_草稿默认未审核_执行器拒绝(tmp_path):
    path = tmp_path / "draft.yaml"
    g.save_draft(path, [GOOD], [])
    with pytest.raises(PermissionError):
        g.load_reviewed(path)


def test_审核后才放行(tmp_path):
    path = tmp_path / "draft.yaml"
    g.save_draft(path, [GOOD], [])
    path.write_text(path.read_text(encoding="utf-8").replace("reviewed: false", "reviewed: true"),
                    encoding="utf-8")
    assert g.load_reviewed(path) == [GOOD]


def test_审核后改坏了也拒绝(tmp_path):
    path = tmp_path / "draft.yaml"
    g.save_draft(path, [_with(api="/wallet/hack")], [])
    path.write_text(path.read_text(encoding="utf-8").replace("reviewed: false", "reviewed: true"),
                    encoding="utf-8")
    with pytest.raises(ValueError):
        g.load_reviewed(path)
