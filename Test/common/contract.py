# -*- coding: utf-8 -*-
"""
接口契约校验（JSON Schema）

★ 和 common/baseline.py 的 schema_of 有什么区别（面试会问） ★

    baseline.compare_data   回归比对：「这次和上次比，结构变了没」
    contract.validate       契约校验：「结构符合我们约定的规格吗」

    差别在**参照物**：
        回归的参照物是「上一次的自己」—— 上次就是错的，这次照错不误。
        契约的参照物是「事先写死的规格」—— 错了就是错了。

    举个真实场景：后端把 price 从 int 改成 string。
        · 回归比对：能发现「变了」，但你得人工判断该不该变
        · 契约校验：直接报「price 应为 number，实际 string」，
          而且这份契约是前后端一起定的，谁违约一目了然

    两个都要。回归防「悄悄改」，契约防「改错了」。

★ 为什么契约文件单独放 sites/<站>/data/schemas/ ★

    JSON Schema 是跨语言标准。放成独立文件，
    后端、前端、测试三方看的是同一份东西，可以直接进接口文档。
    写死在 Python 代码里就只有测试能用了。

★ 一个关键实现细节：要收集全部错误 ★

    jsonschema 默认 validate() 遇到第一个错误就抛。
    接口返回 500 条商品，第 3 条和第 47 条都有问题的话，
    你得修一轮跑一轮才能全暴露出来。
    用 iter_errors() 一次拿全，等价于接口层的「软断言」。
"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from config.settings import SITES_DIR
from common.logger import get_logger

log = get_logger("contract")

# 每个站的契约放自己的 data/schemas/，按名字找；契约名全项目唯一
SCHEMA_DIRS = sorted(SITES_DIR.glob("*/data/schemas"))


class ContractError(AssertionError):
    """接口响应不符合契约。继承 AssertionError，pytest 会当成断言失败处理。"""


def load_schema(name):
    """读 sites/*/data/schemas/<name>.json。"""
    path = next((d / ("%s.json" % name) for d in SCHEMA_DIRS
                 if (d / ("%s.json" % name)).exists()), None)
    if path is None:
        raise FileNotFoundError("契约文件不存在: %s.json（找过 %s）" % (name, [str(d) for d in SCHEMA_DIRS]))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_violations(payload, schema):
    """
    返回全部违约项，不是只返回第一条。

    每项形如：
        {"path": "products.3.price", "message": "...", "value": ...}

    path 用点号拼出来，能直接告诉你是第几条数据的哪个字段出的问题 ——
    报告里只写「校验失败」是没法拿去提 bug 的。
    """
    validator = Draft202012Validator(schema)
    out = []
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.absolute_path) or "(根)"
        out.append({
            "path": path,
            "message": err.message,
            "rule": ".".join(str(p) for p in err.absolute_schema_path),
        })
    return out


def validate(payload, schema_name, sample_limit=None):
    """
    按契约校验响应体。不符合就抛 ContractError。

    参数：
        sample_limit  只校验列表里的前 N 条。
                      接口返回 500 条商品时，全量校验又慢又刷屏；
                      抽样能覆盖绝大多数结构问题。传 None 表示全量。
    """
    schema = load_schema(schema_name)
    target = _truncate(payload, sample_limit) if sample_limit else payload

    violations = find_violations(target, schema)
    if not violations:
        log.debug("契约校验通过: %s", schema_name)
        return []

    detail = "\n".join(
        "  %d) %s\n     %s" % (i + 1, v["path"], v["message"])
        for i, v in enumerate(violations[:20]))
    more = ("\n  ... 其余 %d 条见附件" % (len(violations) - 20)
            if len(violations) > 20 else "")
    raise ContractError(
        "接口响应不符合契约 [%s]，共 %d 处违约：\n%s%s"
        % (schema_name, len(violations), detail, more))


def _truncate(payload, limit):
    """把响应体里的列表截断到前 limit 条，用于抽样校验。"""
    if not isinstance(payload, dict):
        return payload
    out = {}
    for k, v in payload.items():
        out[k] = v[:limit] if isinstance(v, list) else v
    return out


def list_schemas():
    """现有的契约文件清单。给 CLI 和自测用。"""
    return sorted(p.stem for d in SCHEMA_DIRS for p in d.glob("*.json"))
