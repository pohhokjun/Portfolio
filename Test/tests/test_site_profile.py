# -*- coding: utf-8 -*-
"""
站点适配器的自测。

适配器错了不会报错，只会让质量属性用例悄悄测空 ——
选择器写错，`page.locator(...).count()` 返回 0，
断言「不该有溢出元素」照样通过，因为根本没扫到任何元素。
这就是典型的假阴性，必须在这一层挡住。
"""

import pytest

from config.settings import Config
from config.site_profile import (PROFILE_DEFAULT, PROFILES, pick_profile,
                                 profile_for)

# 每个适配器都必须提供的字段。少一个，某一类检查就会静默失效。
REQUIRED_KEYS = ["name", "domains", "pages", "product_card", "product_image"]


class TestPickProfile:

    def test_按域名命中(self):
        assert pick_profile("https://automationexercise.com/products")["name"] \
            == "AutomationExercise"
        assert pick_profile("https://www.saucedemo.com/inventory.html")["name"] \
            == "SauceDemo"

    def test_带端口和路径也能命中(self):
        assert pick_profile("http://www.saucedemo.com:8080/a/b")["name"] == "SauceDemo"

    def test_命中不了走通用兜底(self):
        assert pick_profile("https://从来没见过的站.com") is PROFILE_DEFAULT

    def test_空值不崩(self):
        assert pick_profile("") is PROFILE_DEFAULT
        assert pick_profile(None) is PROFILE_DEFAULT

    def test_从配置对象取(self):
        cfg = Config({"base_url": "https://www.saucedemo.com"}, "x")
        assert profile_for(cfg)["name"] == "SauceDemo"


class TestProfileIntegrity:
    """每份适配器的结构完整性。写漏一个字段，对应的检查就静默失效。"""

    @pytest.mark.parametrize("profile", PROFILES,
                             ids=[p["name"] for p in PROFILES])
    def test_必填字段齐全(self, profile):
        missing = [k for k in REQUIRED_KEYS if not profile.get(k)]
        assert not missing, "%s 缺字段: %s" % (profile["name"], missing)

    @pytest.mark.parametrize("profile", PROFILES,
                             ids=[p["name"] for p in PROFILES])
    def test_域名不能为空(self, profile):
        assert profile["domains"], "%s 没配域名，永远命中不了" % profile["name"]

    @pytest.mark.parametrize("profile", PROFILES,
                             ids=[p["name"] for p in PROFILES])
    def test_页面清单格式正确(self, profile):
        for item in profile["pages"]:
            assert len(item) == 2, "%s 的页面项应是 (名称, 路径)" % profile["name"]
            name, path = item
            assert name and path.startswith("/"), \
                "%s 的路径应以 / 开头: %r" % (profile["name"], path)

    @pytest.mark.parametrize("profile", PROFILES,
                             ids=[p["name"] for p in PROFILES])
    def test_登录规格要么不写要么写全(self, profile):
        spec = profile.get("login")
        if spec is None:
            return
        need = {"path", "username_input", "password_input", "submit", "success_url"}
        assert need <= set(spec), \
            "%s 的登录规格缺: %s" % (profile["name"], need - set(spec))

    @pytest.mark.parametrize("profile", PROFILES,
                             ids=[p["name"] for p in PROFILES])
    def test_第三方域名要写成通配模式(self, profile):
        # page.route 用的是 glob，忘了写 ** 就一个都拦不住，
        # 而容错用例照样会「通过」—— 因为它压根没注入故障
        for pattern in profile.get("third_party") or []:
            assert "*" in pattern, \
                "%s 的第三方模式 %r 没有通配符，route 匹配不到" % (profile["name"], pattern)

    @pytest.mark.parametrize("profile", PROFILES,
                             ids=[p["name"] for p in PROFILES])
    def test_已知缺陷登记必须写清原因(self, profile):
        # 只写一句「已知问题」等于把缺陷藏起来。
        # 登记表要能让接手的人看懂是什么问题、违反了什么标准。
        for key, reason in (profile.get("known_defects") or {}).items():
            assert len(reason) > 30, "%s 的已知缺陷 %s 说明太简略" % (profile["name"], key)
            assert "WCAG" in reason or "违反" in reason or "复核" in reason, \
                "%s 的已知缺陷 %s 应写明依据" % (profile["name"], key)

    def test_域名之间不能互相覆盖(self):
        # 两份适配器配了同一个域名的话，pick 到哪个全看谁排在前面，
        # 这种问题排查起来非常费劲
        seen = {}
        for p in PROFILES:
            for d in p["domains"]:
                assert d not in seen, "域名 %s 同时被 %s 和 %s 占用" % (d, seen[d], p["name"])
                seen[d] = p["name"]


class TestDefaultProfile:

    def test_通用兜底不会让用例崩(self):
        # 命中兜底时，用例应该是「跳过」或「测不到东西」，
        # 而不是 KeyError 直接把整个 session 带崩
        for key in REQUIRED_KEYS:
            assert key in PROFILE_DEFAULT

    def test_兜底不带登录规格(self):
        assert PROFILE_DEFAULT.get("login") is None

    def test_兜底不带第三方域名(self):
        assert not PROFILE_DEFAULT.get("third_party")
