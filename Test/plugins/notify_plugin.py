# -*- coding: utf-8 -*-
"""
测试结果通知插件

【来源】原 17_测试/core/notify.py，改造成 pytest hook。

工作方式：
    通过 pytest 的 terminal reporter 拿到最终统计，
    在 pytest_sessionfinish 时推送通知。

默认关闭，在 config/defaults.yaml 的 notify 段开启。
命令行强制发送： pytest --notify
"""

import time

from common.notify import Notifier
from common.logger import get_logger

log = get_logger("notify.plugin")

_START_TIME = {"t": 0.0}
_FAILED_TESTS = []


def pytest_addoption(parser):
    parser.addoption("--notify", action="store_true", default=False,
                     help="不论结果都发送通知（默认只在失败时发）")


def pytest_sessionstart(session):
    _START_TIME["t"] = time.time()
    _FAILED_TESTS.clear()


def pytest_runtest_logreport(report):
    if report.when == "call" and report.failed:
        _FAILED_TESTS.append(report.nodeid)


def pytest_sessionfinish(session, exitstatus):
    """测试全部结束后发送通知。"""
    try:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is None:
            return

        stats = reporter.stats
        summary = {
            "passed": len(stats.get("passed", [])),
            "failed": len(stats.get("failed", [])),
            "error": len(stats.get("error", [])),
            "skipped": len(stats.get("skipped", [])),
        }
        summary["total"] = sum(summary.values())

        if summary["total"] == 0:
            return

        from config.settings import get_config
        cfg = get_config()   # site_plugin 已把 --site/--env 写进环境变量
        notifier = Notifier(cfg)

        meta = {
            "env": cfg.tag,
            "duration": round(time.time() - _START_TIME["t"], 1),
            "failures": list(_FAILED_TESTS),
            "report": "reports/report.html",
        }

        force = session.config.getoption("--notify")
        result = notifier.send(meta, summary, force=force)
        if result.get("sent"):
            log.info("通知已发送: %s", result.get("channels"))
    except Exception as exc:
        log.debug("通知发送跳过: %s", exc)
