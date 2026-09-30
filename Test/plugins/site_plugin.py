# -*- coding: utf-8 -*-
"""
被测系统插件：框架和站点的接线口

★ 为什么 cfg 要按目录走 ★
    一次 pytest 可能同时跑好几个站的用例（pytest -m api 会跑到
    AutomationExercise、restful-booker、钱包）。如果全局只有一个 cfg，
    就只能一个站一个站地跑，或者在用例里写死网址 —— 又绕回去了。

    做法：sites/<站>/conftest.py 里一行 `cfg = site_cfg("<站>")`，
    pytest 的 fixture 就近覆盖规则会让这个目录下的用例拿到本站配置；
    testcases/ 下的通用用例拿到的是 --site 选的那个站。
    用例、页面对象、接口封装一个字都不用知道自己在测哪个站。
"""

import os

import pytest

from common.logger import get_logger
from config.settings import Config, get_config

log = get_logger("site")


def pytest_configure(config):
    # 写进环境变量：模块导入时就要读配置的地方（参数化、插件）也能拿到同一个站
    for opt, var in (("--site", "TEST_SITE"), ("--env", "TEST_ENV")):
        if config.getoption(opt):
            os.environ[var] = config.getoption(opt)


def build_cfg(request, site=None):
    c = get_config(site, request.config.getoption("--env"))

    # --mock：把 api_url 指到本站的假服务（site.yaml 的 mock）。
    # 为什么改在 cfg 这一层而不是另写一个 fixture ——
    # 所有接口客户端都是从 cfg 拿地址的，在源头换掉，
    # 上层用例、api 封装、可达性探测一个字都不用改。
    # 复制一份再改：缓存里的原件还要给不带 mock 的地方用。
    if request.config.getoption("--mock") and c.get("mock"):
        from tools.mock_server import MockServer, load_routes
        server = MockServer(load_routes(c.get("mock")))
        request.addfinalizer(server.stop)
        c = Config(dict(c._data, api_url=server.start()), c.env, c.site)
        log.info("已启用本地 mock 接口服务: %s", c.api_url)

    log.info("=" * 60)
    log.info("被测系统: %s  环境: %s", c.site, c.env)
    log.info("被测地址: %s", c.base_url)
    log.info("=" * 60)
    return c


def site_cfg(name):
    """给 sites/<站>/conftest.py 用：返回一个绑死本站的 cfg fixture。"""
    @pytest.fixture(scope="session")
    def cfg(request):
        return build_cfg(request, name)
    return cfg


@pytest.fixture(scope="session")
def cfg(request):
    """通用用例（testcases/）用的配置：--site 选哪个站就是哪个。"""
    return build_cfg(request)


def probe(cfg, path=""):
    """
    环境可用性前置检查。站点不可用时整组 SKIP 而不是 FAIL。

    ★ 为什么要有这个（面试可讲）★
      被测站点有机器人防护，跑得太频繁会把 IP 临时封掉，返回 403。
      不做这个检查，几十条用例会全部失败，报告里一片红，
      看报告的人会以为系统崩了，实际只是自动化机器被拦了。
      框架的责任是区分「产品缺陷」和「环境问题」。
    """
    from api.base_api import BaseApi
    api = BaseApi(cfg)
    api.MAX_RETRY = 2
    try:
        # 没给接口路径就直接取首页：BaseApi 把「200 + HTML」当限流页重试，
        # 对接口是对的，对网页首页就是误判（白等 5 秒还报「限流」）
        resp = api.get(path) if path else api.session.get(cfg.base_url, timeout=cfg.api_timeout)
    except Exception as exc:
        pytest.skip("被测站点不可访问：%s\n请检查网络后重试。" % exc,
                    allow_module_level=True)
        return

    if BaseApi.is_ip_banned(resp):
        pytest.skip(
            "\n" + "=" * 66 + "\n"
            "  当前 IP 已被站点的机器人防护临时封禁\n"
            "  这是环境问题，不是被测系统或本框架的缺陷\n"
            "\n"
            "  处理办法（任选其一）：\n"
            "    1. 等待 15-60 分钟后重试（封禁会自动解除）\n"
            "    2. 换个网络环境，比如切换到手机热点\n"
            "    3. 降低执行频率：用 pytest -m smoke 只跑核心用例\n"
            "\n"
            "  真实项目中的解法：让运维把自动化机器 IP 加入白名单\n"
            + "=" * 66,
            allow_module_level=True)
