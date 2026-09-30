# -*- coding: utf-8 -*-
"""
资金链路测试：充值 / 提现 / 余额 / 流水

★ 为什么单独做一组 ★

    游戏、电商、支付公司招测试，JD 里反复出现「资金测试」「支付测试」——
    说白了就是**会测钱**。钱的 bug 和别的 bug 不一样：
    按钮错位是体验问题，多加一次余额是资损，直接赔钱。

    资金系统最常出事的四个地方，这里各有一条检查：
        幂等   同一笔订单请求两次，钱只能动一次
        并发   20 个提现同时打进来，余额不能扣成负数
        精度   0.1 + 0.2 必须等于 0.30，不能是 0.30000000000000004
        对账   余额必须等于流水之和，差一分钱都不行

★ 对照实验（和 quality/test_seeded_defects.py 同一个思路）★

    检查写出来一直是绿的，不代表它有用 —— 可能它根本抓不到问题。
    所以每条检查都要打两次：
        打正常钱包         → 必须通过
        打埋了对应缺陷的钱包 → 必须报出问题
    第二步不红，说明这条检查是摆设。

被测对象是 tools/mock_server.py 里的钱包，用例自己起服务，不依赖外网。

跑法：
    pytest sites/wallet -v
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import allure
import pytest

from sites.wallet.api.wallet_api import WalletApi
from common.assertions import assert_equal
from sites.wallet.mock import BUGS as WALLET_BUGS, Routes
from tools.mock_server import MockServer

pytestmark = [pytest.mark.api, pytest.mark.wallet]


# ---------------------------------------------------------------
# 四条检查。返回空字符串 = 没问题，否则返回问题描述。
# 写成函数而不是直接写在用例里，是为了正常版和埋 bug 版复用同一份逻辑 ——
# 对照实验的前提是「只有被测对象不同，检查完全相同」。
# ---------------------------------------------------------------
def check_idempotent(w):
    w.deposit("100", order="dup-1")
    w.deposit("100", order="dup-1")      # 模拟客户端超时重试
    bal = w.balance()
    return "" if bal == "100.00" else "同一订单充值两次，余额变成 %s" % bal


def check_concurrency(w):
    w.deposit("100")
    # 20 个提现同时打进来，每笔 10 元。余额只够 10 笔。
    with ThreadPoolExecutor(20) as pool:
        results = list(pool.map(lambda _: w.withdraw("10", client=w.client()),
                                range(20)))
    ok = sum(r.get("responseCode") == 200 for r in results)
    bal = w.balance()
    if ok == 10 and bal == "0.00":
        return ""
    return "并发提现成功 %d 笔（应为 10），余额 %s（应为 0.00）" % (ok, bal)


def check_precision(w):
    w.deposit("0.1")
    w.deposit("0.2")
    bal = w.balance()
    return "" if bal == "0.30" else "0.1 + 0.2 得到 %s" % bal


def check_reconcile(w):
    w.deposit("100")
    w.withdraw("30")
    w.withdraw("20.5")
    bal = Decimal(w.balance())
    total = sum(Decimal(x["amount"]) for x in w.ledger())
    return "" if bal == total else "余额 %s ≠ 流水合计 %s" % (bal, total)


CHECKS = {
    "no_idem": ("幂等", check_idempotent),
    "race": ("并发", check_concurrency),
    "float": ("精度", check_precision),
    "ledger_gap": ("对账", check_reconcile),
}


@allure.epic("接口自动化")
@allure.feature("资金链路")
class TestWalletRules:

    @allure.title("WL_{bug} - {bug} 检查：正常钱包必须通过")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.p0
    @pytest.mark.parametrize("bug", list(CHECKS),
                             ids=[v[0] for v in CHECKS.values()])
    def test_rule_holds(self, wallet, bug):
        name, check = CHECKS[bug]
        assert_equal(check(wallet), "", "%s检查应无问题" % name)


@allure.epic("接口自动化")
@allure.feature("资金链路（对照实验）")
class TestWalletSeeded:
    """同一条检查打有缺陷的钱包，必须报出问题 —— 证明检查不是摆设。"""

    @allure.title("WS_{bug} - 埋入缺陷后检查必须报警")
    @pytest.mark.seeded
    @pytest.mark.parametrize("bug", list(CHECKS),
                             ids=[v[0] for v in CHECKS.values()])
    def test_check_catches_bug(self, cfg, bug):
        name, check = CHECKS[bug]
        with MockServer(Routes, bugs=[bug]) as srv:
            problem = check(WalletApi(cfg, srv.url))
        allure.attach(problem or "(没报出来)", name="检查结果")
        assert problem, "埋了「%s」，%s检查却没报警" % (WALLET_BUGS[bug], name)


@allure.epic("接口自动化")
@allure.feature("资金链路（入参校验）")
class TestWalletAmount:

    @allure.title("WA - 金额 {amount!r} → 业务码 {code}")
    @allure.description(
        "边界值 + 等价类：\n"
        "  有效：最小 0.01、上限 50000.00\n"
        "  无效：0、负数、三位小数、超上限 1 分、非数字、NaN")
    @pytest.mark.negative
    @pytest.mark.parametrize("amount,code", [
        ("0.01", 200),          # 最小有效值
        ("50000", 200),         # 上限，恰好等于
        ("50000.01", 400),      # 上限 + 1 分
        ("0", 400),
        ("-1", 400),
        ("0.001", 400),         # 不能悄悄四舍五入成 0.00
        ("abc", 400),
        ("NaN", 400),
    ])
    def test_amount_boundary(self, wallet, amount, code):
        assert_equal(wallet.deposit(amount).get("responseCode"), code,
                     "金额 %r 的业务码" % amount)

    @allure.title("WA - 余额不足时提现失败，余额不变")
    @pytest.mark.negative
    @pytest.mark.p0
    def test_insufficient_balance(self, wallet):
        wallet.deposit("50")
        body = wallet.withdraw("50.01")
        assert_equal(body.get("responseCode"), 400, "业务码")
        assert_equal(wallet.balance(), "50.00", "失败的提现不能动余额")
