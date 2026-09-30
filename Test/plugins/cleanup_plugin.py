# -*- coding: utf-8 -*-
"""
测试数据清理插件

【来源】原 17_测试/core/cleanup.py 的能力，改造成 pytest fixture + hook。

用法：
    def test_create_order(self, api, cleanup):
        order = api.create_order(...)
        cleanup.track("order", order["id"],
                      remover=lambda: api.delete_order(order["id"]))
        # 用例结束后自动删除，即使用例失败也会执行

设计要点：
    session 级的 registry 统一收集，测试全部结束后逆序清理。
    台账立即落盘，进程被强杀也能查到残留数据。
"""

import pytest

from common.cleanup import CleanupRegistry
from common.logger import get_logger

log = get_logger("cleanup.plugin")


@pytest.fixture(scope="session")
def cleanup_registry(cfg, run_id):
    """全局清理台账。整个测试会话共用一份。"""
    registry = CleanupRegistry(cfg, run_id)
    yield registry

    result = registry.run()
    if result["total"]:
        log.info("测试数据清理：共 %d 条，成功 %d，失败 %d，遗留 %d",
                 result["total"], result["done"],
                 result["failed"], result["skipped"])


@pytest.fixture
def cleanup(cleanup_registry):
    """用例里直接用的清理登记器。"""
    return cleanup_registry
