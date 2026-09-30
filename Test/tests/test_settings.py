# -*- coding: utf-8 -*-
"""配置中心 config/settings.py 的自测。"""

import os

import pytest

from config import settings
from config.settings import Config, get_config, load_rules


class TestConfigGet:
    """Config.get 的点号路径取值。"""

    def test_取一层(self, make_cfg):
        assert make_cfg({"a": 1}).get("a") == 1

    def test_取多层(self, make_cfg):
        cfg = make_cfg({"viewport": {"width": 1440}})
        assert cfg.get("viewport.width") == 1440

    def test_路径不存在返回默认值(self, make_cfg):
        assert make_cfg({}).get("no.such.key", "兜底") == "兜底"

    def test_中途撞上非字典也要安全返回(self, make_cfg):
        # a 是个整数，再往下取 a.b 不能抛异常
        assert make_cfg({"a": 1}).get("a.b", "兜底") == "兜底"

    def test_取到的值是None时返回None而不是默认值(self, make_cfg):
        # 配置里写了 key: 就是显式的 None，和「没写这个 key」是两回事
        assert make_cfg({"a": None}).get("a", "兜底") is None

    def test_空路径不崩(self, make_cfg):
        assert make_cfg({"a": 1}).get("", "兜底") == "兜底"


class TestConfigProperties:
    """高频配置的属性访问，重点是类型转换和缺省值。"""

    def test_全部缺省时用默认值(self, make_cfg):
        cfg = make_cfg({})
        assert cfg.timeout == 30000
        assert cfg.nav_timeout == 60000
        assert cfg.api_timeout == 20
        assert cfg.headless is True
        assert cfg.account == {}
        assert cfg.base_url is None

    def test_yaml里写成字符串也要转成数字(self, make_cfg):
        # yaml 里 timeout: "5000" 是很常见的手滑，不该让用例挂在类型上
        cfg = make_cfg({"timeout": "5000", "api_timeout": "8"})
        assert cfg.timeout == 5000
        assert cfg.api_timeout == 8

    def test_headless为假值时是False(self, make_cfg):
        assert make_cfg({"headless": False}).headless is False

    def test_account为None时给空字典(self, make_cfg):
        assert make_cfg({"account": None}).account == {}

    def test_repr带环境和地址(self, make_cfg):
        cfg = make_cfg({"base_url": "http://x"}, env="test")
        assert "test" in repr(cfg) and "http://x" in repr(cfg)


class TestGetConfig:
    """选站和环境的优先级：函数参数 > 环境变量 > defaults.yaml 的默认值。"""

    def setup_method(self):
        settings._CACHE.clear()

    def teardown_method(self):
        settings._CACHE.clear()
        os.environ.pop("TEST_ENV", None)
        os.environ.pop("TEST_SITE", None)

    def test_默认环境是test(self):
        assert get_config().env == "test"

    def test_函数参数优先级最高(self):
        os.environ["TEST_ENV"] = "test"
        assert get_config(env="prod").env == "prod"

    def test_环境变量次之(self):
        os.environ["TEST_ENV"] = "prod"
        assert get_config().env == "prod"

    def test_未定义的环境要直接报错而不是静默兜底(self):
        # 静默兜底最坑：你以为在测 prod，其实一直在测 test
        with pytest.raises(KeyError) as e:
            get_config(env="不存在的环境")
        assert "不存在的环境" in str(e.value)

    def test_同一环境重复取拿到同一个对象(self):
        assert get_config(env="test") is get_config(env="test")

    def test_两个环境的配置确实不同(self):
        # prod 只在 site.yaml 的 envs 里写了差异，其余继承默认值
        assert get_config(env="test").get("viewport.width") == 1440
        assert get_config(env="prod").get("viewport.width") == 1920


class TestLoadRules:
    def test_规则文件不存在时返回空字典(self):
        assert load_rules("根本没有这个规则文件") == {}

    def test_读得到爬虫规则(self):
        rules = load_rules("explore_rules")
        assert "danger_keywords" in rules

    def test_危险词黑名单必须包含删除类关键词(self):
        # 这是安全底线，掉了就是爬虫在生产环境删数据
        danger = load_rules("explore_rules")["danger_keywords"]
        for word in ("delete", "remove", "删除"):
            assert word in danger


def test_目录常量在导入时就已创建():
    for d in (settings.REPORT_DIR, settings.LOG_DIR, settings.SCREENSHOT_DIR,
              settings.BASELINE_DIR, settings.STATE_DIR, settings.SITEMAP_DIR):
        assert d.is_dir()
