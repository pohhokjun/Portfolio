# -*- coding: utf-8 -*-
"""
框架自测的公共 fixture。

★ tests/ 和 testcases/ 的区别，一定要分清 ★

    testcases/   测「被测系统」对不对   —— 要联网、要开浏览器、慢
    tests/       测「这个框架」对不对   —— 不联网、不开浏览器、秒级

    做测试的人最容易忽略的一件事：自动化框架本身也是代码，
    也会有 bug。框架的 bug 比业务 bug 更危险 ——
    它会让所有用例一起给出错误结论。

    这个目录里的用例全部离线运行，任何时候都能跑，
    改完框架先跑它，几秒钟就知道有没有改坏。
"""

from pathlib import Path

import pytest

from config.settings import Config


@pytest.fixture
def make_cfg():
    """
    造一个假的配置对象。

    不读 config/defaults.yaml 和 sites/*/site.yaml，避免自测结果被真实配置影响 ——
    「测试要可重复」这条规矩，对框架自测同样成立。
    """
    def _make(data=None, env="unittest"):
        return Config(dict(data or {}), env)
    return _make


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """
    把所有会往磁盘写东西的模块，重定向到临时目录。

    这些模块都是在 import 时就把 ROOT / DB_PATH 绑进自己的命名空间了，
    所以必须逐个模块 patch，改 config.settings.ROOT 是没用的 ——
    这也是 monkeypatch 最常见的一个坑。
    """
    import common.account_pool
    import common.cleanup
    import common.db_helper
    import tools.sitemap

    (tmp_path / "reports" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(common.account_pool, "ROOT", tmp_path)
    monkeypatch.setattr(common.baseline, "ROOT", tmp_path)
    monkeypatch.setattr(common.cleanup, "ROOT", tmp_path)
    monkeypatch.setattr(tools.sitemap, "ROOT", tmp_path)
    monkeypatch.setattr(common.data_reader, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(tools.case_generator, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(common.db_helper, "DB_PATH", tmp_path / "test_data.db")
    return tmp_path


@pytest.fixture
def png(tmp_path):
    """生成一张纯色 PNG，用来测图像比对。"""
    from PIL import Image

    def _png(name, size=(40, 40), color=(255, 255, 255), boxes=()):
        img = Image.new("RGB", size, color)
        for box, box_color in boxes:
            for x in range(box[0], box[2]):
                for y in range(box[1], box[3]):
                    img.putpixel((x, y), box_color)
        path = tmp_path / ("%s.png" % name)
        img.save(path)
        return str(path)
    return _png


def pytest_collection_modifyitems(items):
    """
    给 tests/ 下的所有用例自动打上 unit 标记。

    这样就有了两条清晰的执行线：
        pytest -m unit        只跑框架自测，几秒钟，不联网
        pytest -m "not unit"  只跑被测系统的用例
    不用在每个文件顶上手写 pytestmark，加文件也不会忘。
    """
    import pytest as _pytest
    here = str(Path(__file__).parent)
    for item in items:
        if str(item.fspath).startswith(here):
            item.add_marker(_pytest.mark.unit)
