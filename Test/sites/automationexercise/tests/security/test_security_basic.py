# -*- coding: utf-8 -*-
"""
基础安全测试

★ 为什么不用 Burp Suite ★
    Burp 需要单独安装、配置代理证书，且免费版功能受限。
    本项目用 requests 直接构造恶意请求，本质是一样的：
    Burp 的 Intruder 也就是把 payload 批量塞进参数里发出去。

覆盖 OWASP Top 10 中最常考的几项：
    A03 注入      SQL注入 / 命令注入
    A03 XSS       跨站脚本
    A01 越权      未授权访问敏感接口
    A05 配置错误  敏感信息泄露、错误堆栈外露

面试话术：
    「我在项目里加了一组基础安全用例，用 requests 构造 SQL 注入和 XSS
      的 payload，验证接口是否做了输入过滤，以及异常时会不会泄露
      数据库错误堆栈。这不是专业渗透测试，但能在冒烟阶段拦住低级问题。
      真正的深度扫描要靠 Burp、AWVS 这类 DAST 工具。」

注意：这些用例只做「验证防护是否生效」，不做任何破坏性操作。
"""

import re

import allure
import pytest

from sites.automationexercise.api.user_api import UserApi
from sites.automationexercise.api.product_api import ProductApi
from common.assertions import assert_true, SoftAssert


# 常见 SQL 注入 payload
SQL_PAYLOADS = [
    "' OR '1'='1",
    "admin'--",
    "' OR 1=1--",
    "'; DROP TABLE users;--",
    "1' UNION SELECT NULL,NULL--",
]

# 常见 XSS payload
XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(1)",
    "<svg/onload=alert(1)>",
]

# 数据库错误关键字：出现说明后端把异常直接抛给了前端
DB_ERROR_KEYWORDS = [
    "SQL syntax", "SQLSTATE", "mysql_fetch", "ORA-",
    "Traceback", "psycopg2", "sqlite3", "You have an error in your SQL",
]


@allure.epic("安全测试")
@allure.feature("输入安全")
class TestSecurityBasic:

    @allure.story("SQL注入防护")
    @allure.title("SEC_001 - 登录接口应能抵御SQL注入")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "OWASP A03: Injection\n"
        "验证点：\n"
        "  1. 注入 payload 不能绕过登录\n"
        "  2. 响应中不能出现数据库错误堆栈（信息泄露）"
    )
    @pytest.mark.security
    @pytest.mark.p0
    def test_sql_injection_on_login(self, cfg):
        api = UserApi(cfg)
        sa = SoftAssert()

        for payload in SQL_PAYLOADS:
            with allure.step("注入 payload: %s" % payload):
                resp = api.verify_login(payload, payload)
                code = api.biz_code(resp)
                body = resp.text

                sa.not_equal(code, 200,
                             "SQL注入 %r 不应登录成功" % payload)

                for kw in DB_ERROR_KEYWORDS:
                    sa.not_contains(body, kw,
                                    "响应不应泄露数据库错误 [%s] payload=%r"
                                    % (kw, payload))

        sa.assert_all()

    @allure.story("SQL注入防护")
    @allure.title("SEC_002 - 搜索接口应能抵御SQL注入")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.security
    @pytest.mark.p1
    def test_sql_injection_on_search(self, cfg):
        api = ProductApi(cfg)
        sa = SoftAssert()

        for payload in SQL_PAYLOADS:
            with allure.step("搜索注入: %s" % payload):
                resp = api.search_product(payload)
                sa.true(resp.status_code < 500,
                        "注入不应导致服务端500错误 payload=%r" % payload)
                for kw in DB_ERROR_KEYWORDS:
                    sa.not_contains(resp.text, kw,
                                    "不应泄露数据库错误 [%s]" % kw)

        sa.assert_all()

    @allure.story("XSS防护")
    @allure.title("SEC_003 - 搜索接口应能抵御XSS")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.description(
        "OWASP A03: Cross-Site Scripting\n"
        "验证点：恶意脚本不应被原样回显到响应中"
    )
    @pytest.mark.security
    @pytest.mark.p1
    def test_xss_on_search(self, cfg):
        api = ProductApi(cfg)
        sa = SoftAssert()

        for payload in XSS_PAYLOADS:
            with allure.step("XSS payload: %s" % payload):
                resp = api.search_product(payload)
                sa.true(resp.status_code < 500,
                        "XSS payload 不应导致500 payload=%r" % payload)
                sa.not_contains(resp.text, "<script>alert(1)</script>",
                                "脚本标签不应被原样回显")

        sa.assert_all()

    @allure.story("XSS防护")
    @allure.title("SEC_004 - UI搜索框XSS应不被执行")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.security
    @pytest.mark.ui
    @pytest.mark.p1
    def test_xss_on_ui_search(self, products_page):
        """
        UI 层的 XSS 验证：
            如果脚本被执行，会弹出 alert 弹窗。
            我们监听 dialog 事件，一旦触发就说明存在 XSS 漏洞。
        """
        triggered = {"value": False}

        def on_dialog(dialog):
            triggered["value"] = True
            dialog.dismiss()

        products_page.page.on("dialog", on_dialog)
        products_page.search("<script>alert('xss')</script>")
        products_page.page.wait_for_timeout(2000)

        assert_true(not triggered["value"],
                    "搜索框存在XSS漏洞：注入的脚本被浏览器执行了")

    @allure.story("信息泄露")
    @allure.title("SEC_005 - 响应头不应泄露组件的具体版本号")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "OWASP A05: Security Misconfiguration\n"
        "验证点：响应头里不能出现带版本号的组件标识。\n"
        "只有版本号才算风险 —— Server: cloudflare 没问题，\n"
        "Server: nginx/1.18.0 就有问题：攻击者能直接按版本查已知漏洞。"
    )
    @pytest.mark.security
    @pytest.mark.p2
    @pytest.mark.xfail(
        reason="已知缺陷：被测站点返回 x-powered-by: Phusion Passenger(R) 6.1.8，"
               "泄露了应用服务器的精确版本。属于被测系统的问题，不是用例的问题。",
        strict=False)
    def test_no_version_disclosure(self, cfg):
        """
        ★ 这条用例原来是假的，值得说一下 ★

            原来的写法最后一行是 sa.true(True, ...) —— 永远通过。
            它把风险项收集起来贴进报告，但一个断言都没有。
            报告里它是一条绿色的用例，看的人以为「检查过了，没问题」，
            实际上不管站点烂成什么样它都是绿的。

            一条永远不会失败的用例，比没有这条用例更糟：
            它占着报告里的一格，还给人虚假的安全感。

        ★ 那真断言了会怎样 ★

            这个站点确实泄露了版本号，断言会失败。
            但这是**被测系统的缺陷**，不是用例写错了。
            真实项目里这种情况的标准做法是：
                1. 提一个 bug 单
                2. 用例保持真实断言，加 xfail 标记并写明原因
                3. 报告里显示为 xfailed（已知缺陷），构建不会变红
                4. 哪天开发修好了，用例会 XPASS，提醒你把标记摘掉

            这样「已知缺陷」是被跟踪的，而不是被假装成通过的。
        """
        api = ProductApi(cfg)
        resp = api.get_all_products()

        headers = dict(resp.headers)
        allure.attach("\n".join("%s: %s" % (k, v) for k, v in headers.items()),
                      name="响应头", attachment_type=allure.attachment_type.TEXT)

        # 大小写不敏感：HTTP 头名本来就不区分大小写，
        # 写死 "X-Powered-By" 会漏掉返回小写头名的服务器
        lower = {k.lower(): v for k, v in headers.items()}
        risky = {
            "server": "暴露服务器软件及版本",
            "x-powered-by": "暴露后端技术栈",
            "x-aspnet-version": "暴露框架版本",
            "x-generator": "暴露生成器版本",
        }

        sa = SoftAssert()
        for header, why in risky.items():
            value = lower.get(header)
            if not value:
                continue
            has_version = bool(re.search(r"\d+\.\d+", value))
            sa.true(not has_version,
                    "%s 不应带版本号（%s）：实际值 %r" % (header, why, value))
        sa.assert_all()

    @allure.story("越权访问")
    @allure.title("SEC_006 - 未提供凭证时不应能删除他人账号")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description("OWASP A01: Broken Access Control")
    @pytest.mark.security
    @pytest.mark.p0
    def test_unauthorized_delete(self, cfg, temp_user):
        api = UserApi(cfg)

        # 用错误的密码尝试删除别人的账号
        resp = api.delete_account(temp_user["email"], "wrong_password_12345")
        code = api.biz_code(resp)

        allure.attach("业务码: %s\n提示: %s" % (code, api.biz_message(resp)),
                      name="越权删除的响应",
                      attachment_type=allure.attachment_type.TEXT)

        assert_true(code != 200,
                    "密码错误时不应允许删除账号，实际返回 %s" % code)
