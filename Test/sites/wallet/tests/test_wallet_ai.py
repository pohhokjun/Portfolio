# -*- coding: utf-8 -*-
"""
执行 AI 生成、人工审核过的钱包用例

    data/wallet_requirement.md  →  python -m tools.cli ai  →  data/ai_cases_wallet.yaml
                                   （Claude 生成 + 机器校验）   （人工审核后 reviewed: true）
                                                            →  本文件逐条执行

没审核的草稿不会被执行，整个模块跳过并写明原因。
审核后如果被改坏（编造字段、接口不存在），直接报错，不会悄悄跑。
"""

import allure
import pytest

from sites.wallet import DATA
from tools.ai_case_gen import load_reviewed

pytestmark = [pytest.mark.api, pytest.mark.wallet]

try:
    CASES = load_reviewed(DATA / "ai_cases_wallet.yaml")
except (PermissionError, FileNotFoundError) as exc:
    pytest.skip(str(exc), allow_module_level=True)


@allure.epic("接口自动化")
@allure.feature("资金链路（AI 生成用例）")
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_ai_case(wallet, case):
    allure.dynamic.title("%s - %s" % (case["id"], case["title"]))
    allure.dynamic.description("设计方法：%s\n理由：%s" % (case["method"], case.get("why", "")))
    if case.get("setup_deposit"):
        assert wallet.deposit(case["setup_deposit"]).get("responseCode") == 200, "前置充值失败"
    kind = case["api"].rsplit("/", 1)[-1]
    body = wallet.call(kind, case["amount"])
    assert body.get("responseCode") == case["expect_code"], (
        "%s 金额 %r：期望 %s，实际 %s" % (kind, case["amount"], case["expect_code"], body))
