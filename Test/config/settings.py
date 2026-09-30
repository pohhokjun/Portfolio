# -*- coding: utf-8 -*-
"""
配置中心

设计说明：
    整个项目只有这一个地方读取配置文件，其余模块通过 get_config() 拿数据。
    好处是换环境只改一处，不用满项目搜索硬编码的网址。

    面试话术：这叫「配置与代码分离」，是自动化框架的基本要求。

★ 三层合并（后面的盖前面的）★
    config/defaults.yaml        框架默认：浏览器、超时、视口、预算、通知……对哪个站都一样
    sites/<站>/site.yaml        这个被测系统自己的：网址、账号、选择器、预算
    site.yaml 里的 envs.<环境>   同一个站的 test / prod 差异（只写不一样的几行）

    这样加一个被测系统只要写它和默认值不同的部分，
    不会像以前一样每套环境把几十行浏览器配置复制一遍。
"""

import os
from pathlib import Path

import yaml

# 项目根目录（本文件在 config/ 下，所以要往上一层）
ROOT = Path(__file__).resolve().parent.parent

# 常用目录，统一在这里定义，避免各模块自己拼路径
SITES_DIR = ROOT / "sites"
RULES_DIR = ROOT / "rules"
REPORT_DIR = ROOT / "reports"
LOG_DIR = ROOT / "reports" / "logs"
SCREENSHOT_DIR = ROOT / "reports" / "screenshots"
BASELINE_DIR = ROOT / "reports" / "baseline"
STATE_DIR = ROOT / "reports" / "state"
SITEMAP_DIR = ROOT / "reports" / "sitemaps"
TRACE_DIR = ROOT / "reports" / "traces"
DB_PATH = ROOT / "reports" / "test_data.db"

for _d in (REPORT_DIR, LOG_DIR, SCREENSHOT_DIR,
           BASELINE_DIR, STATE_DIR, SITEMAP_DIR, TRACE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_CACHE = {}


class Config:
    """把 yaml 字典包一层，提供点号访问和默认值。"""

    def __init__(self, data: dict, env_name: str, site=None):
        self._data = data
        self.env = env_name
        self.site = site

    @property
    def tag(self):
        """站点_环境。基线、账号状态、站点地图按它分文件，不同站互不覆盖。"""
        return "%s_%s" % (self.site, self.env) if self.site else self.env

    @property
    def dir(self):
        return SITES_DIR / self.site if self.site else ROOT

    @property
    def data_dir(self):
        return self.dir / "data"

    def get(self, path, default=None):
        """支持 cfg.get('viewport.width') 这种写法。"""
        cur = self._data
        for part in str(path).split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    # ---- 高频配置做成属性，调用处更干净 ----
    @property
    def base_url(self):
        return self.get("base_url")

    @property
    def api_url(self):
        return self.get("api_url")

    @property
    def timeout(self):
        return int(self.get("timeout", 30000))

    @property
    def nav_timeout(self):
        return int(self.get("nav_timeout", 60000))

    @property
    def api_timeout(self):
        return int(self.get("api_timeout", 20))

    @property
    def headless(self):
        return bool(self.get("headless", True))

    @property
    def account(self):
        return self.get("account", {}) or {}

    def __repr__(self):
        return "<Config site=%s env=%s base_url=%s>" % (self.site, self.env, self.base_url)


def _yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _merge(base, over):
    """深合并：字典逐层合，其余直接覆盖。"""
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def list_sites():
    """有 site.yaml 的目录才算站点；_ 开头的是模板。"""
    return sorted(p.parent.name for p in SITES_DIR.glob("*/site.yaml")
                  if not p.parent.name.startswith("_"))


def get_config(site=None, env=None) -> Config:
    """
    读取配置。优先级：
        函数参数 > 环境变量 TEST_SITE / TEST_ENV > defaults.yaml 的 default_site / test
    """
    defaults = _yaml(ROOT / "config" / "defaults.yaml")
    site = site or os.environ.get("TEST_SITE") or defaults.get("default_site")
    env = env or os.environ.get("TEST_ENV") or "test"

    if (site, env) in _CACHE:
        return _CACHE[(site, env)]

    path = SITES_DIR / site / "site.yaml"
    if not path.exists():
        raise KeyError("未定义的站点: %s，可选: %s" % (site, list_sites()))
    raw = _yaml(path)
    envs = raw.pop("envs", None) or {}
    # 静默兜底最坑：你以为在测 prod，其实一直在测 test，所以没配的环境直接报错
    if env != "test" and env not in envs:
        raise KeyError("未定义的环境: %s，站点 %s 可选: %s" % (env, site, ["test", *envs]))

    data = _merge(_merge({k: v for k, v in defaults.items() if k != "default_site"}, raw), envs.get(env))
    cfg = Config(data, env, site)
    _CACHE[(site, env)] = cfg
    return cfg


def load_rules(name):
    """
    读取 rules/ 下的规则文件。

    规则文件和配置文件的区别：
        sites/*/site.yaml 站点相关（网址、超时、账号）
        rules/*.yaml     策略相关（爬虫边界、危险词黑名单、断言规则）

    分开的好处：换环境只改 config，测试策略不用动。
    """
    path = RULES_DIR / ("%s.yaml" % name)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
