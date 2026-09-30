# -*- coding: utf-8 -*-
"""
命令行工具入口

【来源】原 17_测试/main.py 的能力，精简后保留。
       测试执行部分已交给 pytest，这里只保留 pytest 做不了的事。

用法：
    python -m tools.cli explore              爬站生成站点地图
    python -m tools.cli explore --gen        爬站并生成巡检用例
    python -m tools.cli gen                  从已有站点地图生成用例
    python -m tools.cli sitemap              查看站点地图
    python -m tools.cli baseline list        查看视觉基线
    python -m tools.cli baseline clear       清空全部基线
    python -m tools.cli accounts             查看账号池状态
    python -m tools.cli cleanup              查看待清理的测试数据
    python -m tools.cli doctor               环境自检

★ 为什么保留命令行而不全交给 pytest ★
    pytest 的职责是「执行用例」。
    爬站、生成用例、管理基线、查台账，这些是「运维类操作」，
    不该混在测试执行里。职责分离。
"""

import argparse
import sys
from pathlib import Path

from config.settings import get_config, load_rules, ROOT


# ---------------------------------------------------------------
# 输出辅助
# ---------------------------------------------------------------
def title(text):
    print()
    print("=" * 66)
    print("  " + text)
    print("=" * 66)


def table(headers, rows):
    if not rows:
        print("  （无数据）")
        return
    data = [[str(c) if c is not None else "" for c in r] for r in rows]

    def dlen(t):
        return sum(2 if ord(c) > 0x2E80 else 1 for c in str(t))

    widths = [max([dlen(headers[i])] + [dlen(r[i]) for r in data])
              for i in range(len(headers))]

    def pad(t, w):
        return str(t) + " " * max(0, w - dlen(t))

    print("  " + "  ".join(pad(headers[i], widths[i])
                           for i in range(len(headers))))
    # 分隔线长度要正好等于数据行：列宽之和 + 列间的两个空格 ×(列数-1)
    print("  " + "-" * (sum(widths) + 2 * (len(widths) - 1)))
    for r in data:
        print("  " + "  ".join(pad(r[i], widths[i]) for i in range(len(headers))))


# ---------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------
def cmd_explore(args):
    from tools.explorer import SiteExplorer

    cfg = get_config(args.site, args.env)
    title("站点探索  站点=%s" % cfg.tag)

    def progress(done, total, text):
        sys.stdout.write("\r  进度 %d/%d  %s" % (done, total, text.ljust(60)[:60]))
        sys.stdout.flush()

    explorer = SiteExplorer(cfg)
    start = [args.url] if args.url else None
    sm = explorer.explore(start, progress=progress)
    print()

    path = sm.save(args.out)
    print("\n  站点地图已保存: %s" % path)
    table(["项目", "数量"],
          [["页面", len(sm.nodes)],
           ["表单", len(sm.all_forms())],
           ["接口", len(sm.all_apis())]])

    if args.gen:
        return _do_gen(cfg, sm)
    print("\n  下一步：python -m tools.cli gen   生成巡检用例")
    return 0


def _do_gen(cfg, sitemap):
    from tools.case_generator import CaseGenerator

    gen = CaseGenerator(cfg)
    cases = gen.generate(sitemap)
    info = gen.save(cases)

    print("\n  巡检用例已生成: %s" % info["path"])
    table(["类型", "数量"], [[k, len(v)] for k, v in cases.items()])
    print("\n  下一步：pytest -m crawl   执行巡检用例")
    return 0


def cmd_gen(args):
    from tools.sitemap import Sitemap, default_path

    cfg = get_config(args.site, args.env)
    path = args.sitemap or default_path(cfg.tag)
    if not Path(path).exists():
        print("  站点地图不存在: %s" % path)
        print("  请先执行: python -m tools.cli explore")
        return 2
    return _do_gen(cfg, Sitemap.load(path))


def cmd_sitemap(args):
    from tools.sitemap import Sitemap, default_path

    cfg = get_config(args.site, args.env)
    path = args.path or default_path(cfg.tag)
    if not Path(path).exists():
        print("  站点地图不存在，请先执行 explore")
        return 2
    sm = Sitemap.load(path)
    title("站点地图  %s  共 %d 页" % (sm.root_url, len(sm.nodes)))
    print(sm.tree_text())
    return 0


def cmd_baseline(args):
    from common.baseline import BaselineStore

    cfg = get_config(args.site, args.env)
    store = BaselineStore(cfg)

    if args.action == "list":
        title("视觉基线  站点=%s" % cfg.tag)
        rows = [[r["case"], r["images"], r["data"]] for r in store.list_all()]
        table(["用例", "图片基线", "数据基线"], rows)
        print("\n  更新基线：pytest --update-baseline")
        return 0

    if args.action == "clear":
        # 这里原来还有一个 prune 子命令，帮助里写的是「清理失效基线」，
        # 实际执行的是 store.prune([])，也就是保留名单为空 —— 把基线全删了。
        # 名字说的是精准清理，行为是全清，这种命令迟早会误伤。
        # CLI 层根本不知道哪些 case_id 还活着，做不到真正的 prune，
        # 所以直接去掉，只留一个语义诚实的 clear。
        # BaselineStore.prune(keep) 本身是对的，留着给代码里调用。
        import shutil
        shutil.rmtree(store.dir, ignore_errors=True)
        print("  已清空全部基线，下次运行会重新建立")
        return 0
    return 0


def cmd_accounts(args):
    from common.account_pool import AccountPool

    cfg = get_config(args.site, args.env)
    pool = AccountPool(cfg)

    if args.release:
        if pool.state_path.exists():
            pool.state_path.unlink()
        print("  已强制释放全部账号占用")
        return 0

    title("账号池  站点=%s" % cfg.tag)
    if not pool.accounts:
        print("  未配置账号。请在 站点 site.yaml 的 accounts 段添加。")
        return 0
    table(["账号", "角色", "状态", "起始时间"],
          [[r["username"], r["role"], r["status"], r["since"]]
           for r in pool.status()])
    return 0


def cmd_cleanup(args):
    from common.cleanup import CleanupRegistry

    cfg = get_config(args.site, args.env)
    pending = CleanupRegistry.pending_ledgers(cfg)

    title("待清理的测试数据")
    if not pending:
        print("  没有遗留数据")
        return 0
    table(["台账文件", "批次", "待处理"],
          [[Path(p["path"]).name, p["run_id"], p["pending"]] for p in pending])
    print("\n  自动清理只在测试运行时生效，历史遗留需按台账人工处理")
    return 0


def cmd_ai(args):
    from tools import ai_case_gen
    return ai_case_gen.main([a for a in (args.req, args.out) if a])


def cmd_doctor(args):
    title("环境自检")
    rows = []

    for name, mod in [("pytest", "pytest"), ("playwright", "playwright"),
                      ("requests", "requests"), ("PyYAML", "yaml"),
                      ("Faker", "faker"), ("Pillow", "PIL"),
                      ("allure-pytest", "allure_commons")]:
        try:
            __import__(mod)
            rows.append([name, "已安装", ""])
        except ImportError:
            note = "视觉比对将不可用" if name == "Pillow" else ""
            rows.append([name, "缺失", note])

    cfg = get_config(args.site, args.env)
    rows.append(["站点", cfg.tag, cfg.base_url])
    rows.append(["账号数", len(cfg.get("accounts", []) or []), ""])

    from tools.sitemap import default_path
    sm_path = default_path(cfg.tag)
    rows.append(["站点地图", "存在" if Path(sm_path).exists() else "无",
                 str(sm_path.name)])

    crawl = Path(ROOT) / "data" / "crawl_cases.yaml"
    rows.append(["巡检用例", "存在" if crawl.exists() else "无", ""])

    table(["检查项", "状态", "说明"], rows)
    return 0


# ---------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="tools.cli",
        description="自动化测试项目 - 运维工具（测试执行请用 pytest）")
    p.add_argument("--site", help="被测系统（sites/ 下的文件夹名），默认读 config/defaults.yaml 的 default_site")
    p.add_argument("--env", help="环境名 test / prod，默认 test")
    sub = p.add_subparsers(dest="cmd")

    e = sub.add_parser("explore", help="爬站生成站点地图")
    e.add_argument("--url", help="起始地址，不传则用配置里的 base_url")
    e.add_argument("--out", help="站点地图输出路径")
    e.add_argument("--gen", action="store_true", help="探索后立即生成巡检用例")
    e.set_defaults(func=cmd_explore)

    g = sub.add_parser("gen", help="从站点地图生成巡检用例")
    g.add_argument("--sitemap", help="站点地图路径")
    g.set_defaults(func=cmd_gen)

    s = sub.add_parser("sitemap", help="查看站点地图")
    s.add_argument("--path", help="站点地图路径")
    s.set_defaults(func=cmd_sitemap)

    b = sub.add_parser("baseline", help="视觉基线管理")
    b.add_argument("action", choices=["list", "clear"])
    b.set_defaults(func=cmd_baseline)

    a = sub.add_parser("accounts", help="账号池状态")
    a.add_argument("--release", action="store_true", help="强制释放全部占用")
    a.set_defaults(func=cmd_accounts)

    c = sub.add_parser("cleanup", help="查看待清理的测试数据")
    c.set_defaults(func=cmd_cleanup)

    i = sub.add_parser("ai", help="AI 按需求生成用例草稿（需人工审核后才执行）")
    i.add_argument("req", nargs="?", help="需求文档，默认 data/wallet_requirement.md")
    i.add_argument("out", nargs="?", help="草稿输出，默认 data/ai_cases_wallet.yaml")
    i.set_defaults(func=cmd_ai)

    d = sub.add_parser("doctor", help="环境自检")
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv=None):
    # 本文件的输出全是中文。不先把控制台切到 UTF-8，
    # 在英文区系统或输出被重定向时，第一个 print 就会 UnicodeEncodeError 崩掉。
    from common.logger import use_utf8_console
    use_utf8_console()

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n  已中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())
