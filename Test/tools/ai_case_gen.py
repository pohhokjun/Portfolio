# -*- coding: utf-8 -*-
"""
AI 生成测试用例：需求文档 → Claude → 机器校验 → 人工审核 → 执行

★ 为什么不是「让 AI 写完直接跑」★

    AI 写用例快，但会一本正经地编：编一个不存在的接口、编一个多余的字段、
    把期望结果写反。直接跑，轻则用例报错，重则把错的期望当成标准，
    真 bug 反而被判成通过。所以中间加两道闸：

        1. 机器校验（validate_cases）
           字段齐不齐、有没有编造字段、接口是不是真的存在、
           设计方法和期望码在不在允许范围、金额是不是字符串
        2. 人工审核
           草稿落盘时 reviewed: false，执行器只认 reviewed: true。
           人看过、改过、把它改成 true，用例才会被执行。

    AI 负责量，人负责对。这就是招聘里「AI 提效但必须人工把关」的具体做法。

★ 为什么调 claude 命令行而不是 API ★

    本机装了 Claude Code 并已登录，直接 claude -p 就能调，不用单独申请 API key。
    调用方式做成可注入的参数（runner），自测时换成假函数，不联网、不花额度。

用法：
    python -m tools.cli ai                              默认读钱包需求，写草稿
    python -m tools.ai_case_gen 需求.md 输出.yaml
"""

import re
import shutil
import subprocess
import sys

import yaml

from sites.wallet import DATA as DATA_DIR   # 默认拿钱包的需求文档做示范

REQUIRED = ("id", "title", "method", "api", "amount", "expect_code")
OPTIONAL = ("setup_deposit", "why")
KNOWN_APIS = ("/wallet/deposit", "/wallet/withdraw")
METHODS = ("等价类", "边界值", "判定表", "场景法", "错误推测")

PROMPT = """你是资深测试工程师。根据下面的需求，用等价类/边界值等方法设计接口测试用例。
只输出一个 YAML 列表，不要任何解释。每条用例只能有这些字段：
  id: 形如 AI_001
  title: 一句话标题
  method: 只能是 {methods} 之一
  api: 只能是 {apis} 之一
  setup_deposit: （可选）执行前先充值的金额，字符串
  amount: 本次请求金额，必须用引号写成字符串
  expect_code: 200 或 400
  why: 为什么这么设计，一句话
写 10 到 15 条，覆盖有效/无效等价类和上下边界。

需求：
{req}
"""


def extract_yaml(text):
    """模型经常自作主张包一层 ```yaml ... ```，剥掉再解析。"""
    m = re.search(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.S)
    return yaml.safe_load(m.group(1) if m else text) or []


def validate_cases(cases):
    """返回问题清单。空列表 = 机器校验通过（还需要人工审核）。"""
    if not isinstance(cases, list):
        return ["顶层不是列表"]
    out, seen = [], set()
    for i, c in enumerate(cases, 1):
        tag = "第 %d 条(%s)" % (i, c.get("id", "?") if isinstance(c, dict) else "?")
        if not isinstance(c, dict):
            out.append(tag + " 不是字典")
            continue
        out += ["%s 缺字段 %s" % (tag, f) for f in REQUIRED if f not in c]
        out += ["%s 编造了字段 %s" % (tag, f) for f in c if f not in REQUIRED + OPTIONAL]
        if c.get("api") not in KNOWN_APIS:
            out.append("%s 接口 %s 不存在" % (tag, c.get("api")))
        if c.get("method") not in METHODS:
            out.append("%s 设计方法 %s 不在允许范围" % (tag, c.get("method")))
        if c.get("expect_code") not in (200, 400):
            out.append("%s 期望码 %s 不合法" % (tag, c.get("expect_code")))
        # YAML 会把 0.1 读成浮点数，0.10 和 0.1 就分不清了 —— 钱必须是字符串
        for f in ("amount", "setup_deposit"):
            if f in c and not isinstance(c[f], str):
                out.append("%s %s 必须是字符串，得到 %r" % (tag, f, c[f]))
        if c.get("id") in seen:
            out.append("%s id 重复" % tag)
        seen.add(c.get("id"))
    return out


def _claude(prompt):
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("没找到 claude 命令行，先安装并登录 Claude Code")
    r = subprocess.run([exe, "-p", prompt], capture_output=True, text=True,
                       encoding="utf-8", timeout=600)
    if r.returncode != 0:
        raise RuntimeError("claude 调用失败: %s" % (r.stderr or r.stdout)[:500])
    return r.stdout


def generate(req_text, runner=_claude):
    """需求 → (用例, 问题清单)。解析失败也返回问题清单，不抛异常。"""
    raw = runner(PROMPT.format(methods="/".join(METHODS),
                               apis="/".join(KNOWN_APIS), req=req_text))
    try:
        cases = extract_yaml(raw)
    except yaml.YAMLError as exc:
        return [], ["模型输出不是合法 YAML: %s" % exc]
    return cases, validate_cases(cases)


def save_draft(path, cases, problems):
    doc = {"reviewed": False, "reviewer": "", "machine_check": problems or "通过",
           "cases": cases}
    with open(path, "w", encoding="utf-8") as f:
        f.write("# AI 生成的草稿。人工逐条看过、改好，再把 reviewed 改成 true 才会被执行。\n")
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)


def load_reviewed(path):
    """执行器入口：没审核、或者审核后改坏了，都拒绝。"""
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    if doc.get("reviewed") is not True:
        raise PermissionError("%s 还没人工审核（reviewed 不是 true），拒绝执行" % path)
    problems = validate_cases(doc.get("cases"))
    if problems:
        raise ValueError("审核后的用例仍有问题:\n" + "\n".join(problems))
    return doc["cases"]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    src = argv[0] if argv else str(DATA_DIR / "wallet_requirement.md")
    dst = argv[1] if len(argv) > 1 else str(DATA_DIR / "ai_cases_wallet.yaml")
    with open(src, encoding="utf-8") as f:
        cases, problems = generate(f.read())
    save_draft(dst, cases, problems)
    print("生成 %d 条，机器校验%s → %s" % (
        len(cases), "通过" if not problems else "发现 %d 个问题" % len(problems), dst))
    for p in problems:
        print("  - " + p)
    print("下一步：人工审核，把 reviewed 改成 true")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
