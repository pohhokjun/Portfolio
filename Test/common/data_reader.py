# -*- coding: utf-8 -*-
"""
测试数据读取

为什么数据要从代码里分离出去：
    1. 加用例不用改代码，改 yaml 就行
    2. 不懂编程的测试同事也能维护
    3. 同一份数据可以给不同的用例复用

    面试话术：这叫「数据驱动测试」，配合 pytest 的 parametrize 实现。

文件名怎么找：
    绝对路径直接用（站点用例传 sites/<站>/data/xxx.yaml）；
    相对名从当前被测站点的 data/ 找（通用用例用，比如巡检读 crawl_cases.yaml）。
"""

import json
from pathlib import Path

import yaml

from config.settings import get_config

# None = 当前站点的 data/。框架自测会把它指到临时目录
DATA_DIR = None


def _path(filename):
    return Path(DATA_DIR or get_config().data_dir) / filename


def load_yaml(filename):
    """读取 yaml 测试数据，返回原始结构。"""
    path = _path(filename)
    if not path.exists():
        raise FileNotFoundError("测试数据文件不存在: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_cases(filename, key="cases"):
    """
    读取用例列表，专门配合 pytest.mark.parametrize 使用。

    返回： (参数列表, ID列表)
        参数列表 -> 每条用例的字典
        ID列表   -> 报告里显示的用例名，比 case0/case1 可读得多
    """
    data = load_yaml(filename)
    cases = data.get(key, []) if isinstance(data, dict) else data
    ids = [c.get("title") or c.get("id") or ("case_%d" % i)
           for i, c in enumerate(cases)]
    return cases, ids


def load_json(filename):
    path = _path(filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
