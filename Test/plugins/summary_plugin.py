# -*- coding: utf-8 -*-
"""
测试总结报告插件 —— 每次跑完自动生成，不用手写

★ 它和 report.html 的分工 ★

    reports/report.html   pytest-html 出的**执行明细**：584 条逐条结果，
                          给开发查「第几条为什么红了」
    reports/测试总结.html  本插件出的**结论**：能不能发版、风险在哪，
                          给团队看

    以前这份结论是手写 markdown（docs/04_测试总结报告.md），
    问题是每跑一轮就得手工改数字，改着改着就忘了，
    留下一份数字全是旧的报告 —— 比没有还糟。

    所以改成自动生成：数字永远和最后一次执行一致，不可能对不上。

★ 实现方式：pytest hook ★

    pytest_runtest_logreport   每条用例跑完时被调用，收集结果
    pytest_sessionfinish       整场跑完时被调用，写文件

    写用例的人完全不用管这件事 —— 这就是插件化的意义。
"""

import html
from fnmatch import fnmatch
import platform
import re
import time
from collections import defaultdict

from config.settings import REPORT_DIR
from common.logger import get_logger

log = get_logger("summary")

OUT = REPORT_DIR / "测试总结.html"

# 用例路径 → 中文层名。报告要给不看代码的人看，不能直接甩目录名。
# 站点用例在 sites/<站>/tests/<层>/，用通配符匹配，加新站不用改这里。
LAYERS = [
    (("tests/*",),                        "框架自测",   "测框架本身对不对，离线运行"),
    (("testcases/quality/*",),            "质量属性",   "可访问性/响应式/性能/容错"),
    (("sites/*/tests/ui/*",),             "UI 功能",    "登录/搜索/购物车"),
    (("sites/*/tests/api/*", "testcases/api/*",
      "sites/restful_booker/*", "sites/wallet/*"),
                                          "接口与契约", "接口正反向 + JSON Schema 契约 + 鉴权 + 资金"),
    (("sites/*/tests/perf/*",),           "接口性能",   "并发压测/P95/TPS"),
    (("sites/*/tests/security/*",),       "安全",       "SQL注入/XSS/越权/信息泄露"),
    (("sites/*/tests/visual/*",),         "视觉回归",   "截图基线 + 接口结构基线"),
    (("testcases/crawl/*",),              "站点巡检",   "爬虫自动生成的可用性检查"),
]


def _layer_of(nodeid):
    nid = nodeid.replace("\\", "/")
    for patterns, name, _ in LAYERS:
        if any(fnmatch(nid, p) for p in patterns):
            return name
    return "其他"


def _readable(nodeid):
    """
    把 nodeid 里被转义的中文还原回来。

    pytest 默认会把参数化 id 里的非 ASCII 字符转成 \\uXXXX，
    所以中文用例名在 nodeid 里长这样：
        test_no_critical_violations[\\u5546\\u54c1\\u5217\\u8868]
    报告是给人看的，这样没法读，得还原成「商品列表」。

    （也可以在 pytest.ini 里关掉转义，但那个选项名字叫
      disable_test_id_escaping_and_forfeit_all_rights_to_community_support，
      pytest 官方用这个名字明示「用了出问题别来问」，所以宁可在展示层还原。）
    """
    try:
        return re.sub(r"(?:\\u[0-9a-fA-F]{4})+",
                      lambda m: m.group(0).encode().decode("unicode_escape"),
                      nodeid)
    except Exception:
        return nodeid


class _Collector:
    def __init__(self):
        self.rows = {}          # nodeid -> 结果
        self.start = time.time()

    def record(self, report):
        """
        只认「用例执行阶段」的最终结果。

        一条用例有 setup / call / teardown 三个阶段。
        setup 挂了算 error，call 挂了算 failed —— 两者要分开统计：
        error 通常是环境/前置问题，failed 才是被测系统的问题。
        """
        nid = report.nodeid
        if report.when == "setup":
            if report.failed:
                self.rows[nid] = ("error", report)
            elif report.skipped:
                self.rows[nid] = ("skipped", report)
        elif report.when == "call":
            if report.failed:
                self.rows[nid] = ("xfailed" if hasattr(report, "wasxfail")
                                  else "failed", report)
            elif report.skipped:
                self.rows[nid] = ("xfailed" if hasattr(report, "wasxfail")
                                  else "skipped", report)
            else:
                self.rows[nid] = ("xpassed" if hasattr(report, "wasxfail")
                                  else "passed", report)
        elif report.when == "teardown" and report.failed:
            self.rows.setdefault(nid, ("error", report))


_c = _Collector()


def pytest_runtest_logreport(report):
    _c.record(report)


def pytest_sessionfinish(session, exitstatus):
    try:
        _write(session, exitstatus)
    except Exception as exc:          # 出报告失败绝不能影响测试结果本身
        log.warning("总结报告生成失败: %s", exc)


# ---------------------------------------------------------------
def _write(session, exitstatus):
    rows = _c.rows
    if not rows:
        return

    total = len(rows)
    tally = defaultdict(int)
    for status, _ in rows.values():
        tally[status] += 1

    passed = tally["passed"]
    failed = tally["failed"]
    error = tally["error"]
    skipped = tally["skipped"]
    xfailed = tally["xfailed"]
    xpassed = tally["xpassed"]

    # 通过率的分母不该算上「跳过」和「已知缺陷」——
    # 环境不可用被跳过的用例，既不算通过也不算失败，
    # 把它算进分母会让通过率无缘无故变难看。
    effective = passed + failed + error
    rate = (passed / effective * 100) if effective else 0.0

    # 结论：给不看细节的人一句话
    if failed or error:
        verdict, vclass = "不建议发版", "bad"
        vwhy = "存在 %d 条失败 / %d 条异常，需先定位" % (failed, error)
    elif effective == 0:
        verdict, vclass = "本轮未有效执行", "warn"
        vwhy = "全部用例被跳过，通常是被测环境不可用，不是代码问题"
    elif xfailed:
        verdict, vclass = "可以发版", "ok"
        vwhy = "全部通过；另有 %d 条已知缺陷在跟踪中，不阻断发布" % xfailed
    else:
        verdict, vclass = "可以发版", "ok"
        vwhy = "全部通过，无遗留问题"

    # 分层统计
    layers = defaultdict(lambda: defaultdict(int))
    for nid, (status, _) in rows.items():
        layers[_layer_of(nid)][status] += 1

    order = [n for _, n, _ in LAYERS] + ["其他"]
    desc = {n: d for _, n, d in LAYERS}

    cfg = getattr(session.config, "_qa_cfg", None)
    env_name = "%s / %s" % (session.config.getoption("--site") or "默认站",
                            session.config.getoption("--env") or "test")
    engine = session.config.getoption("--browser-engine", default="chromium")
    marks = session.config.getoption("-m", default="") or "（全部）"
    duration = round(time.time() - _c.start, 1)

    html_out = _render(
        verdict=verdict, vclass=vclass, vwhy=vwhy,
        total=total, passed=passed, failed=failed, error=error,
        skipped=skipped, xfailed=xfailed, xpassed=xpassed,
        rate=rate, effective=effective, duration=duration,
        layers=layers, order=order, desc=desc, rows=rows,
        env_name=env_name, engine=engine, marks=marks,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_out)
    log.info("测试总结已生成: %s", OUT)


def _bar(passed, failed, error, skipped, xfailed):
    """一条横向占比条。比一堆数字直观。"""
    total = max(1, passed + failed + error + skipped + xfailed)
    seg = [("ok", passed), ("bad", failed + error),
           ("warn", xfailed), ("mute", skipped)]
    return "".join(
        '<i class="%s" style="width:%.4f%%"></i>' % (cls, n / total * 100)
        for cls, n in seg if n)


def _fail_list(rows):
    """失败和异常的清单。这是报告里最该被认真看的一块。"""
    items = [(nid, st, rep) for nid, (st, rep) in rows.items()
             if st in ("failed", "error")]
    if not items:
        return '<p class="none">本轮没有失败用例。</p>'
    out = ['<table><thead><tr><th>用例</th><th>类型</th><th>报错</th></tr></thead><tbody>']
    for nid, st, rep in sorted(items):
        msg = ""
        if rep.longrepr is not None:
            msg = str(rep.longrepr).strip().splitlines()[-1][:200]
        out.append(
            '<tr><td class="nid">%s</td><td><b class="bad">%s</b></td>'
            '<td class="msg">%s</td></tr>'
            % (html.escape(_readable(nid)), "失败" if st == "failed" else "异常",
               html.escape(msg)))
    out.append("</tbody></table>")
    return "".join(out)


def _known_list(rows):
    """已知缺陷清单：断言是真的，只是登记过了，所以不阻断发布。"""
    items = [(nid, rep) for nid, (st, rep) in rows.items() if st == "xfailed"]
    if not items:
        return '<p class="none">没有登记在案的已知缺陷。</p>'
    out = ['<table><thead><tr><th>用例</th><th>登记原因</th></tr></thead><tbody>']
    for nid, rep in sorted(items):
        reason = str(getattr(rep, "wasxfail", "") or "").strip()
        reason = reason.replace("reason: ", "")
        out.append('<tr><td class="nid">%s</td><td class="msg">%s</td></tr>'
                   % (html.escape(_readable(nid)), html.escape(reason[:400])))
    out.append("</tbody></table>")
    return "".join(out)


def _render(**k):
    layer_rows = []
    for name in k["order"]:
        d = k["layers"].get(name)
        if not d:
            continue
        p, f, e = d["passed"], d["failed"], d["error"]
        s, x = d["skipped"], d["xfailed"]
        n = p + f + e + s + x + d["xpassed"]
        eff = p + f + e
        r = "%.1f%%" % (p / eff * 100) if eff else "—"
        layer_rows.append(
            "<tr><td><b>%s</b><br><span class='sub'>%s</span></td>"
            "<td class='num'>%d</td><td class='num ok'>%d</td>"
            "<td class='num %s'>%d</td><td class='num %s'>%d</td>"
            "<td class='num mute'>%d</td><td class='num'>%s</td>"
            "<td class='barcell'><div class='bar'>%s</div></td></tr>"
            % (html.escape(name), html.escape(k["desc"].get(name, "")),
               n, p,
               "bad" if f + e else "mute", f + e,
               "warn" if x else "mute", x,
               s, r, _bar(p, f, e, s, x)))

    return TEMPLATE % {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "verdict": html.escape(k["verdict"]),
        "vclass": k["vclass"],
        "vwhy": html.escape(k["vwhy"]),
        "rate": "%.1f" % k["rate"],
        "total": k["total"],
        "passed": k["passed"],
        "failed": k["failed"] + k["error"],
        "xfailed": k["xfailed"],
        "skipped": k["skipped"],
        "duration": k["duration"],
        "env": html.escape(k["env_name"]),
        "engine": html.escape(str(k["engine"])),
        "marks": html.escape(str(k["marks"])),
        "python": platform.python_version(),
        "os": html.escape(platform.system() + " " + platform.release()),
        "bar": _bar(k["passed"], k["failed"], k["error"],
                    k["skipped"], k["xfailed"]),
        "layers": "".join(layer_rows),
        "fails": _fail_list(k["rows"]),
        "known": _known_list(k["rows"]),
        "effective": k["effective"],
    }


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>测试总结报告</title>
<style>
:root{--bg:#f4f6fa;--card:#fff;--ink:#141922;--soft:#4a5568;--mute:#8792a6;
--line:#dbe1ec;--ok:#20674a;--okbg:#e2f0e9;--bad:#a63823;--badbg:#f8e6e2;
--warn:#8f6212;--warnbg:#f7eddb;--accent:#22406b;}
@media(prefers-color-scheme:dark){:root{--bg:#0f1219;--card:#171b24;--ink:#e7eaf1;
--soft:#b6bfd0;--mute:#8792a6;--line:#2b3240;--ok:#61b892;--okbg:#152a22;
--bad:#e08872;--badbg:#2e1b16;--warn:#d0a559;--warnbg:#2b2213;--accent:#8fb2e2;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);line-height:1.7;
font-family:-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;}
.wrap{max-width:960px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:24px;margin:0 0 4px}
.when{color:var(--mute);font-size:13px;margin:0 0 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:22px 24px;margin:0 0 20px}
.verdict{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.badge{font-size:20px;font-weight:600;padding:8px 18px;border-radius:8px}
.badge.ok{background:var(--okbg);color:var(--ok)}
.badge.bad{background:var(--badbg);color:var(--bad)}
.badge.warn{background:var(--warnbg);color:var(--warn)}
.why{color:var(--soft);font-size:15px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));
gap:1px;background:var(--line);border:1px solid var(--line);
border-radius:8px;overflow:hidden;margin:20px 0 0}
.stat{background:var(--card);padding:14px 16px}
.stat .v{font-size:24px;font-weight:600;font-variant-numeric:tabular-nums;
display:block;line-height:1.2}
.stat .l{font-size:12.5px;color:var(--mute)}
.v.ok{color:var(--ok)}.v.bad{color:var(--bad)}.v.warn{color:var(--warn)}
.bar{display:flex;height:9px;border-radius:5px;overflow:hidden;background:var(--line)}
.bar i{display:block;height:100%%}
.bar i.ok{background:var(--ok)}.bar i.bad{background:var(--bad)}
.bar i.warn{background:var(--warn)}.bar i.mute{background:var(--mute);opacity:.45}
.bigbar{margin:18px 0 0}
h2{font-size:16px;margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid var(--line)}
table{width:100%%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:11px;letter-spacing:.08em;color:var(--mute);
font-weight:500;padding:8px 10px;border-bottom:1px solid var(--line);text-transform:uppercase}
td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}.mute{color:var(--mute)}
.sub{font-size:12px;color:var(--mute);font-weight:400}
.barcell{width:130px}
.nid{font-family:ui-monospace,Consolas,monospace;font-size:12px;word-break:break-all}
.msg{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--soft);
word-break:break-word}
.none{color:var(--mute);font-size:14px;margin:0}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;
font-size:13.5px}
.meta div span{color:var(--mute);display:block;font-size:12px}
.foot{color:var(--mute);font-size:13px;margin:28px 0 0;line-height:1.9}
.foot code{background:var(--bg);padding:2px 6px;border-radius:4px;
font-family:ui-monospace,Consolas,monospace}
</style></head><body><div class="wrap">

<h1>测试总结报告</h1>
<p class="when">生成时间 %(time)s ｜ 本文件每次执行自动覆盖，数字始终和最后一次执行一致</p>

<div class="card">
  <div class="verdict">
    <span class="badge %(vclass)s">%(verdict)s</span>
    <span class="why">%(vwhy)s</span>
  </div>
  <div class="stats">
    <div class="stat"><span class="v">%(total)d</span><span class="l">用例总数</span></div>
    <div class="stat"><span class="v ok">%(passed)d</span><span class="l">通过</span></div>
    <div class="stat"><span class="v bad">%(failed)d</span><span class="l">失败/异常</span></div>
    <div class="stat"><span class="v warn">%(xfailed)d</span><span class="l">已知缺陷</span></div>
    <div class="stat"><span class="v mute">%(skipped)d</span><span class="l">跳过</span></div>
    <div class="stat"><span class="v">%(rate)s%%</span><span class="l">通过率</span></div>
    <div class="stat"><span class="v">%(duration)s s</span><span class="l">耗时</span></div>
  </div>
  <div class="bar bigbar">%(bar)s</div>
  <p class="foot">通过率 = 通过 ÷ (通过+失败+异常) = %(passed)d ÷ %(effective)d。
  「跳过」和「已知缺陷」不计入分母 —— 环境不可用被跳过的用例既不算通过也不算失败，
  算进去只会让数字无端难看。</p>
</div>

<div class="card">
  <h2>分层结果</h2>
  <table><thead><tr><th>层</th><th class="num">总数</th><th class="num">通过</th>
  <th class="num">失败</th><th class="num">已知缺陷</th><th class="num">跳过</th>
  <th class="num">通过率</th><th></th></tr></thead>
  <tbody>%(layers)s</tbody></table>
</div>

<div class="card">
  <h2>失败清单</h2>
  %(fails)s
</div>

<div class="card">
  <h2>已知缺陷（登记在案，不阻断发布）</h2>
  <p class="foot" style="margin:0 0 14px">断言是真的，缺陷也是真的，只是被测系统我们改不了，
  所以登记后标为 xfail。对方修好会变成 XPASS 提醒摘掉登记 ——
  缺陷是被跟踪的，不是被放过的。</p>
  %(known)s
</div>

<div class="card">
  <h2>执行环境</h2>
  <div class="meta">
    <div><span>环境</span>%(env)s</div>
    <div><span>浏览器内核</span>%(engine)s</div>
    <div><span>筛选条件</span>%(marks)s</div>
    <div><span>Python</span>%(python)s</div>
    <div><span>操作系统</span>%(os)s</div>
  </div>
  <p class="foot">要看每一条用例的执行明细、失败截图和日志，打开
  <code>reports/report.html</code>。那份是给开发查问题用的，这份是结论。</p>
</div>

</div></body></html>
"""
