# -*- coding: utf-8 -*-
"""
故障注入测试（需要 --mock）

★ 这一组用例测的不是被测系统，是「我们自己的框架够不够抗造」★

    真站点永远返回正常数据，下面这些场景在它身上一条都造不出来：
        服务端 500、响应超时、返回半截 JSON、连续限流之后恢复。

    但线上事故恰恰集中在这里。测试框架碰到这些情况应该：
        - 该重试的重试（限流），不该重试的别浪费时间（500、404）
        - 解析失败要能兜住，不能一个畸形响应把整轮用例带崩
        - 超时要按超时报，别悄悄挂死

    所以用 mock 把故障造出来，把框架的容错分支一条条验过去。
    面试问「你怎么保证框架本身可靠」，这一组就是答案的一半，
    另一半是 tests/ 里的 459 条离线自测。

跑法：
    pytest testcases/api/test_fault_injection.py --mock -v

不加 --mock 会整组跳过 —— 因为这些路由只有假服务才有。
"""

import allure
import pytest
import requests

from api.base_api import BaseApi
from common.assertions import assert_equal, assert_true


@pytest.fixture(autouse=True)
def _need_mock(request):
    if not request.config.getoption("--mock"):
        pytest.skip("本组用例需要 --mock：真站点造不出 500/超时/畸形JSON")


@pytest.fixture(scope="module")
def api(cfg):
    """默认配置的客户端。故障路由是 mock 骨架自带的，和哪个站无关，所以不用站点的接口封装。"""
    return BaseApi(cfg)


@pytest.fixture
def fast_api(cfg):
    """一个超时短、重试少的客户端。默认配置要等 20 秒，测超时太慢。"""
    client = BaseApi(cfg, min_interval=0)
    client.timeout = 1
    client.MAX_RETRY = 2
    return client


@allure.epic("接口自动化")
@allure.feature("故障注入（框架容错）")
class TestFaultTolerance:

    @allure.story("服务端错误")
    @allure.title("FI_001 - 服务端 500 应如实返回，不做无谓重试")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.description(
        "500 是服务端自己的问题，重试大概率还是 500。\n"
        "只有限流（403/429）和拦截页才值得退避重试 —— 那些是暂时的。\n"
        "分不清这两者的框架，会把一次故障放大成 4 倍请求量。")
    @pytest.mark.api
    @pytest.mark.mock
    @pytest.mark.p0
    def test_server_error_not_retried(self, api):
        resp = api.get("/_fault/status?code=500")
        assert_equal(resp.status_code, 500, "HTTP 状态码应如实透传")
        assert_equal(api.biz_code(resp), 500, "业务码")

    @allure.story("响应体异常")
    @allure.title("FI_002 - 返回半截 JSON 时应兜住，不能抛异常")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.description(
        "网关截断、编码错乱都会产生半截 JSON。\n"
        "json_of() 的约定是解析失败返回空字典，让用例断言失败而不是报错 ——\n"
        "断言失败能看到是哪条用例、期望什么；抛异常只能看到一行堆栈。")
    @pytest.mark.api
    @pytest.mark.mock
    @pytest.mark.p0
    def test_malformed_json_does_not_crash(self, api):
        resp = api.get("/_fault/badjson")
        assert_equal(api.json_of(resp), {}, "解析失败应返回空字典")
        assert_equal(api.biz_code(resp), 200, "取不到业务码时退回HTTP码")

    @allure.story("限流")
    @allure.title("FI_003 - 连续限流后恢复，退避重试应能救回来")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "这条正是本项目踩过的坑：批量跑用例时站点限流，"
        "一半用例随机失败。\n"
        "解法是识别限流 + 指数退避重试。这里用 mock 把当时的场景固化下来，"
        "变成一条能随时回归的用例 —— 修完 bug 补一条用例，是基本功。")
    @pytest.mark.api
    @pytest.mark.mock
    @pytest.mark.p0
    def test_recovers_from_rate_limit(self, api):
        api.post("/_fault/reset")

        resp = api.get("/_fault/flaky?fail=2&key=recover")
        body = api.json_of(resp)

        assert_equal(resp.status_code, 200, "退避重试后最终应成功")
        assert_true(body.get("attempts", 0) >= 3,
                    "应该真的重试过，实际请求次数: %s" % body.get("attempts"))

    @allure.story("限流")
    @allure.title("FI_004 - 一直被拦截页挡住时，重试应有上限")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "重试必须封顶。没有上限的重试在站点真的挂掉时会把用例卡到超时，"
        "一轮跑几小时还出不了报告。")
    @pytest.mark.api
    @pytest.mark.mock
    @pytest.mark.p1
    def test_retry_has_upper_bound(self, fast_api):
        resp = fast_api.get("/_fault/blocked")
        assert_true(BaseApi._is_blocked(resp), "mock 应持续返回拦截页")
        assert_equal(fast_api.json_of(resp), {}, "拦截页不是JSON，应兜成空字典")

    @allure.story("超时")
    @allure.title("FI_005 - 服务端不响应时应按超时抛出，不能挂死")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.mock
    @pytest.mark.p1
    def test_timeout_raises(self, fast_api):
        with pytest.raises(requests.RequestException):
            fast_api.get("/_fault/slow?ms=3000")
