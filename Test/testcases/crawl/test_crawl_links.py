# -*- coding: utf-8 -*-
"""
死链检查 —— 由爬虫自动生成

检查页面内所有链接是否可达。
这是 pytest 生态里没有的能力，属于本项目的巡检层。

为什么用浏览器上下文发请求：
    这样能携带登录后的 cookie，
    否则需要登录才能访问的链接会全部报 302/403 假死链。
"""

import allure
import pytest

from common.assertions import SoftAssert
from common.data_reader import load_yaml
from common.logger import get_logger

log = get_logger("crawl.link")

OK_CODES = {200, 201, 204, 301, 302, 303, 304, 307, 308}
MAX_LINKS_PER_CASE = 15      # 每个页面最多检查多少条，避免执行时间过长


def _load():
    """
    同 test_crawl_smoke 里的说明：列表必须非空。
    parametrize 传空列表会造出参数为 NOTSET 的桩用例，
    @allure.title("{case[title]}") 格式化它会直接报 TypeError。
    """
    try:
        data = load_yaml("crawl_cases.yaml")
    except FileNotFoundError:
        data = {}
    cases = (data.get("cases", {}) or {}).get("link", []) or []
    cases = [c for c in cases if c.get("enabled", True)]
    if not cases:
        placeholder = {"title": "尚未生成巡检用例", "links": [],
                       "_placeholder": True}
        return [placeholder], ["尚未生成巡检用例"]
    ids = [str(c.get("title") or c.get("id") or "case")[:60] for c in cases]
    return cases, ids


LINK_CASES, LINK_IDS = _load()
NO_CASES = bool(LINK_CASES) and LINK_CASES[0].get("_placeholder")


@allure.epic("站点巡检")
@allure.feature("链接可用性")
class TestCrawlLinks:

    @allure.story("死链检查")
    @allure.title("{case[title]}")
    @pytest.mark.crawl
    @pytest.mark.p2
    @pytest.mark.skipif(NO_CASES,
                        reason="尚未生成巡检用例，请先执行 "
                               "python -m tools.cli explore --gen")
    @pytest.mark.parametrize("case", LINK_CASES, ids=LINK_IDS)
    def test_links_reachable(self, context, case):
        """用浏览器上下文批量请求链接，携带会话 cookie。"""
        links = (case.get("links") or [])[:MAX_LINKS_PER_CASE]
        if not links:
            pytest.skip("该页面没有可检查的链接")

        broken = []
        checked = 0
        for url in links:
            try:
                resp = context.request.get(url, timeout=15000)
                checked += 1
                if resp.status not in OK_CODES:
                    broken.append("%s -> HTTP %s" % (url[:100], resp.status))
            except Exception as exc:
                checked += 1
                broken.append("%s -> %s" % (url[:100], type(exc).__name__))

        allure.attach("检查 %d 条，异常 %d 条\n\n%s"
                      % (checked, len(broken), "\n".join(broken[:20])),
                      name="链接检查结果",
                      attachment_type=allure.attachment_type.TEXT)

        sa = SoftAssert()
        for item in broken[:20]:
            sa.true(False, "死链: %s" % item)
        sa.true(True, "共检查 %d 条链接" % checked)
        sa.assert_all()
