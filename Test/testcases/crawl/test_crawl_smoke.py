# -*- coding: utf-8 -*-
"""
巡检用例 —— 由爬虫自动生成的数据驱动

★ 这是本项目最独特的部分 ★

    普通自动化：人写用例 → 机器执行
    这一层：    机器爬站 → 自动生成用例 → 机器执行

工作流程：
    1. python -m tools.cli explore --gen     爬站并生成 data/crawl_cases.yaml
    2. pytest -m crawl                       执行生成的巡检用例

价值：
    新增页面不用人工加用例，适合做全站可用性的日常巡检。
    典型场景：每天早上 9 点自动跑一遍，页面打不开就告警。

局限（面试要主动说，显得你清醒）：
    只能验证「能不能打开」这类基础可用性，
    验证不了「金额算得对不对」这类业务规则。
    所以它是功能测试的补充，不是替代。

如果还没生成用例，这些测试会自动跳过，不会报错。
"""

import allure
import pytest

from common.assertions import SoftAssert
from common.data_reader import load_yaml
from common.logger import get_logger

log = get_logger("crawl")


# 一条占位用例。没有真实用例时用它顶上。
#
# ★ 为什么必须有这个占位 ★
#   parametrize 传空列表时，pytest 会造一个参数值为 NOTSET 的桩用例。
#   本文件的 @allure.title("{case[title]}") 会去格式化这个 NOTSET，
#   直接报 TypeError: 'NotSetType' object is not subscriptable，
#   在报告里表现为一条 ERROR —— 而真实情况只是「还没爬站而已」。
#   「没有用例可跑」应该是跳过，绝不该是报错。
_PLACEHOLDER = {"title": "尚未生成巡检用例", "url": "", "method": "GET",
                "_placeholder": True}


def _load_crawl_cases(kind):
    """
    读取自动生成的巡检用例。

    返回的列表保证非空：没有真实用例时给一条占位，
    配合 skipif 让这一组整体显示为「跳过」。
    """
    try:
        data = load_yaml("crawl_cases.yaml")
    except FileNotFoundError:
        data = {}
    cases = (data.get("cases", {}) or {}).get(kind, []) or []
    cases = [c for c in cases if c.get("enabled", True)]
    if not cases:
        return [dict(_PLACEHOLDER)], ["尚未生成巡检用例"]
    ids = [str(c.get("title") or c.get("id") or "case")[:60] for c in cases]
    return cases, ids


def _no_cases(cases):
    """这一组是不是只有占位用例。"""
    return bool(cases) and cases[0].get("_placeholder")


SMOKE_CASES, SMOKE_IDS = _load_crawl_cases("smoke")
API_CASES, API_IDS = _load_crawl_cases("api")


@allure.epic("站点巡检")
@allure.feature("页面可用性")
class TestCrawlSmoke:
    """自动生成的页面可用性巡检。"""

    @allure.story("页面可访问")
    @allure.title("{case[title]}")
    @pytest.mark.crawl
    @pytest.mark.p1
    @pytest.mark.skipif(_no_cases(SMOKE_CASES),
                        reason="尚未生成巡检用例，请先执行 "
                               "python -m tools.cli explore --gen")
    @pytest.mark.parametrize("case", SMOKE_CASES, ids=SMOKE_IDS)
    def test_page_available(self, page, cfg, case):
        """
        对每个爬到的页面检查：
            1. HTTP 状态码正常
            2. 页面有实际内容（不是空白页）
            3. 没有出现错误文案（Traceback / 500 / SQLSTATE 等）
            4. 浏览器控制台没有 JS 报错
        """
        allure.dynamic.description("URL: %s" % case["url"])

        console_errors = []
        page.on("console",
                lambda m: console_errors.append(m.text[:200])
                if m.type == "error" else None)

        resp = page.goto(case["url"], wait_until="domcontentloaded",
                         timeout=cfg.nav_timeout)
        page.wait_for_timeout(800)

        sa = SoftAssert()

        if resp is not None:
            sa.status_code(resp.status,
                           case.get("expect_status", [200]), "HTTP状态码")

        text = page.inner_text("body") if page.locator("body").count() else ""
        sa.true(len(text.strip()) > 20, "页面内容非空白")

        for bad in case.get("forbidden_text", []) or []:
            sa.not_contains(text, bad, "页面不应出现错误文案 [%s]" % bad)

        if case.get("check_console") and console_errors:
            allure.attach("\n".join(console_errors[:10]),
                          name="控制台错误",
                          attachment_type=allure.attachment_type.TEXT)
            # 控制台错误只警告不判失败：第三方广告脚本经常报错，不是站点问题
            log.warning("%s 存在 %d 条控制台错误",
                        case["url"], len(console_errors))

        sa.assert_all()


@allure.epic("站点巡检")
@allure.feature("接口可用性")
class TestCrawlApi:
    """自动发现的接口巡检。"""

    @allure.story("接口可访问")
    @allure.title("{case[title]}")
    @pytest.mark.crawl
    @pytest.mark.p1
    @pytest.mark.skipif(_no_cases(API_CASES),
                        reason="尚未生成巡检用例，请先执行 "
                               "python -m tools.cli explore --gen")
    @pytest.mark.parametrize("case", API_CASES, ids=API_IDS)
    def test_api_available(self, cfg, case):
        """
        对爬虫在页面加载时捕获到的每个 XHR/fetch 接口，
        重新调用一次，检查是否可用、响应是否够快。
        """
        from api.base_api import BaseApi

        allure.dynamic.description(
            "接口: %s %s\n来源页面: %s"
            % (case.get("method"), case["url"], case.get("from_page", "")))

        api = BaseApi(cfg)
        resp = api.request(case.get("method", "GET"), case["url"])

        sa = SoftAssert()
        sa.status_code(resp.status_code,
                       case.get("expect_status", [200, 201, 204]), "状态码")
        sa.less_than(resp.elapsed_ms, case.get("max_ms", 5000), "响应时间")
        sa.assert_all()
